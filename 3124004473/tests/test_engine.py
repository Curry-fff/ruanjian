# -*- coding: utf-8 -*-
"""查重引擎单元测试。

测试函数：:class:`plagcheck.engine.PlagiarismChecker`、
:class:`plagcheck.engine.SimilarityWeights`、
:class:`plagcheck.engine.DuplicationResult`。

构造测试数据的思路：引擎输出的是一个"分数"，分数本身没有绝对正确值，
所以测试策略是**验证它必须满足的性质**，而不是比对魔法数字：

1. 端点性质——完全相同必须得 1.00，完全无关必须接近 0.00；
2. 单调性——破坏越多，分数越低。这是"查重"这个词的全部意义所在，
   也是唯一能跨语料验证的强断言；
3. 不变性——标点、空白、全角半角的改写不得影响分数；
4. 边界与防御——空文本、超长文本、非法权重。

另外用作业题目给出的样例钉一个回归值，防止后续重构悄悄改变量纲。
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError

import pytest

from plagcheck.engine import (
    MAX_SEQUENCE_CHARS,
    DuplicationResult,
    PlagiarismChecker,
    SimilarityWeights,
)

#: 作业题目给出的样例原文与抄袭版。
SAMPLE_ORIGINAL = "今天是星期天，天气晴，今天晚上我要去看电影。"
SAMPLE_COPY = "今天是周天，天气晴朗，我晚上要去看电影。"

#: 一段结构完整、长度接近真实段落的测试文章。
BASE = (
    "深度学习在自然语言处理领域取得了显著进展。"
    "本文提出了一种基于注意力机制的文本相似度计算方法。"
    "该方法首先对输入文本进行分词与向量化表示，"
    "然后通过多层自注意力网络捕捉词语之间的长距离依赖关系，"
    "最后使用余弦相似度度量两段文本的语义接近程度。"
    "实验结果表明，该方法在多个公开数据集上均优于传统方法。"
)

#: 轻度抄袭：只替换两个汉字。
LIGHT_PLAGIARISM = BASE.replace("显著进展", "明显进展")

#: 中度抄袭：中间两句被改写成完全不同的内容。
MEDIUM_PLAGIARISM = (
    BASE[: BASE.index("该方法首先")]
    + "我们设计了一套完全不同的流程来处理这类问题。"
    + "该流程依靠统计频次而不依赖任何神经网络结构。"
    + BASE[BASE.index("最后使用") :]
)

#: 重度抄袭：只保留首句，其余全部是新内容。
HEAVY_PLAGIARISM = BASE[: BASE.index("本文提出")] + (
    "操作系统课程讨论了进程调度与内存管理的基本策略。"
    "编译器前端需要完成词法分析与语法分析两个阶段。"
    "计算机网络中的可靠传输依赖滑动窗口与超时重传机制。"
)


class TestEndpoints:
    """端点性质：分数必须落在 [0, 1]，且端点行为可预测。"""

    def test_identical_text_scores_exactly_one(self):
        """逐字相同的两篇论文重复率必须是 1.00。"""
        result = PlagiarismChecker().compare_texts(BASE, BASE)
        assert result.duplication == pytest.approx(1.0)

    def test_unrelated_text_scores_near_zero(self):
        """两篇毫无关系的文章必须接近 0.00。"""
        result = PlagiarismChecker().compare_texts(
            "深度学习在自然语言处理领域取得了显著进展。",
            "操作系统课程讨论了进程调度与内存管理的基本策略。",
        )
        assert result.duplication < 0.1

    def test_score_always_within_unit_interval(self):
        """任何输入组合都不得越界。"""
        checker = PlagiarismChecker()
        pairs = [
            (BASE, BASE),
            (BASE, LIGHT_PLAGIARISM),
            (BASE, MEDIUM_PLAGIARISM),
            (BASE, HEAVY_PLAGIARISM),
            ("a", "b"),
            ("今天", "今天今天今天今天"),
        ]
        for original, copy in pairs:
            score = checker.compare_texts(original, copy).duplication
            assert 0.0 <= score <= 1.0

    def test_assignment_sample_regression(self):
        """作业样例的回归值：0.71。

        样例只有 19 / 17 个字，改动密度很高（替换 4 处、删除 3 字），
        0.71 落在"明显改写但仍能看出同源"这一档，符合人的直觉。这个
        数字本身没有标准答案，但它必须稳定——一旦重构让它漂移，说明
        某路信号的量纲被改动了。
        """
        result = PlagiarismChecker().compare_texts(SAMPLE_ORIGINAL, SAMPLE_COPY)
        assert result.duplication == pytest.approx(0.71, abs=0.02)

    def test_real_corpus_regression(self, data_dir):
        """真实语料的回归值：0.79。

        ``tests/data`` 里是课程下发的语料：``orig.txt``（余华《活着》
        前言与第一章，8493 个有效字符）与 ``orig_add.txt``（在其上做
        字符级随机插入，净增 20.8%）。

        语料命名中的 "0.8" 与算法给出的 0.79 高度吻合——这是本算法
        **准确度**最有力的一条外部证据，也是回归防线。
        """
        result = PlagiarismChecker().compare_files(
            os.path.join(data_dir, "orig.txt"),
            os.path.join(data_dir, "orig_add.txt"),
        )
        assert result.duplication == pytest.approx(0.79, abs=0.02)
        # 插入型抄袭保留了原文的全部字符，字符级覆盖率应当接近 0.83。
        assert result.components["unigram_coverage"] == pytest.approx(0.828, abs=0.01)


class TestMonotonicity:
    """单调性：损坏越严重，分数越低。这是查重器的核心可用性。"""

    def test_score_decreases_as_plagiarism_gets_heavier(self):
        checker = PlagiarismChecker()
        light = checker.compare_texts(BASE, LIGHT_PLAGIARISM).duplication
        medium = checker.compare_texts(BASE, MEDIUM_PLAGIARISM).duplication
        heavy = checker.compare_texts(BASE, HEAVY_PLAGIARISM).duplication

        assert light > medium > heavy
        assert light > 0.9, "只改两个字应当几乎满分"

    def test_deletion_lowers_score_proportionally(self):
        """删除得越多，分数越低。"""
        checker = PlagiarismChecker()
        kept = [len(BASE) // 4, len(BASE) // 2, len(BASE)]
        scores = [
            checker.compare_texts(BASE[:size], BASE).duplication for size in kept
        ]
        assert scores[0] < scores[1] <= scores[2]

    def test_duplicated_whole_document_halves_multiset_coverage(self):
        """把原文整篇复制两遍，覆盖率减半——这是刻意的多重集语义。

        ``coverage`` 用 ``Σ min(tf_原文, tf_抄袭)``：原文对每段内容只
        "供得上"一次，抄袭版把它放了两遍，多出来的一半无法在原文中找
        到对应物。这条性质保证"复制粘贴凑字数"不会拉高重复率。

        注意 ``unigram_coverage`` 同样减半（字符多重集也被复制了一份），
        而 ``bigram_cosine`` 几乎不变——它只看方向、不看长度。三路信号
        对同一个退化输入给出三种解读，正是设置多信号的目的。
        """
        doubled = BASE + BASE
        result = PlagiarismChecker().compare_texts(BASE, doubled)
        assert result.components["bigram_coverage"] == pytest.approx(0.5, abs=0.02)
        assert result.components["unigram_coverage"] == pytest.approx(0.5, abs=0.02)
        assert result.components["bigram_cosine"] == pytest.approx(1.0, abs=0.01)


class TestInvariance:
    """不变性：无意义的书写差异不得影响分数。"""

    @pytest.mark.parametrize(
        "rewritten",
        [
            BASE.replace("。", "．"),
            BASE.replace("，", "；"),
            BASE.replace("。", "\n"),
            "  " + BASE + "  \n\n",
            BASE.replace("本文", "本文 "),
        ],
    )
    def test_punctuation_and_whitespace_do_not_change_score(self, rewritten):
        """换了标点、加了空白，重复率必须一模一样。"""
        checker = PlagiarismChecker()
        baseline = checker.compare_texts(BASE, BASE).duplication
        assert checker.compare_texts(BASE, rewritten).duplication == baseline

    def test_fullwidth_digits_are_folded(self):
        """全角数字与半角数字视为同一内容。"""
        checker = PlagiarismChecker()
        assert checker.compare_texts("实验准确率 95%", "实验准确率 ９５％").duplication == (
            pytest.approx(1.0)
        )

    def test_keep_punctuation_switch_changes_result(self):
        """打开保留标点后，标点差异才会影响分数——开关必须真的生效。"""
        strict = PlagiarismChecker(keep_punctuation=False)
        loose = PlagiarismChecker(keep_punctuation=True)
        noisy = BASE.replace("。", "！")
        assert strict.compare_texts(BASE, noisy).duplication == pytest.approx(1.0)
        assert loose.compare_texts(BASE, noisy).duplication < 1.0


class TestEmptyAndBoundaryInputs:
    """边界输入：空文本与只有标点的文本。"""

    def test_empty_copy_scores_zero(self):
        """抄袭版为空（归一化后无内容）→ 约定 0.00，不抛异常。"""
        result = PlagiarismChecker().compare_texts(BASE, "")
        assert result.duplication == 0.0
        assert result.components == {}

    def test_empty_original_scores_zero(self):
        """原文为空 → 0.00。"""
        assert PlagiarismChecker().compare_texts("", BASE).duplication == 0.0

    def test_punctuation_only_texts_score_zero(self):
        """整篇都是标点，属于"无法比对"，记 0.00 而不是报错。"""
        result = PlagiarismChecker().compare_texts("，。！？", "……——")
        assert result.duplication == 0.0

    def test_single_character_documents(self):
        """极端最小输入不得抛异常。"""
        assert PlagiarismChecker().compare_texts("甲", "甲").duplication == pytest.approx(1.0)
        assert PlagiarismChecker().compare_texts("甲", "乙").duplication < 0.5

    def test_result_reports_character_counts(self):
        """结果要报告归一化后的字符数，便于解释分数来源。"""
        result = PlagiarismChecker().compare_texts(SAMPLE_ORIGINAL, SAMPLE_COPY)
        assert result.original_characters == len(SAMPLE_ORIGINAL) - 3
        assert result.copy_characters == len(SAMPLE_COPY) - 3


class TestAdaptiveSequenceSignal:
    """超长文本的自适应降级与权重重归一化。"""

    def test_sequence_signal_is_skipped_for_long_text(self):
        """文本超过阈值时跳过顺序信号，避免突破 5 秒时限。"""
        checker = PlagiarismChecker(max_sequence_chars=64)
        long_text = BASE * 20
        result = checker.compare_texts(long_text, long_text)
        assert result.sequence_evaluated is False
        assert "sequence_ratio" not in result.components

    def test_weights_are_renormalised_after_skipping(self):
        """跳过信号后，剩余权重必须重新归一化到 1.0。

        否则分数会凭空掉一截，"长文本天生低分"会变成系统性偏差。
        """
        checker = PlagiarismChecker(max_sequence_chars=64)
        result = checker.compare_texts(BASE * 20, BASE * 20)
        assert sum(result.weights.values()) == pytest.approx(1.0)
        assert result.duplication == pytest.approx(1.0)

    def test_sequence_signal_is_used_for_short_text(self):
        """短文本必须启用顺序信号。"""
        result = PlagiarismChecker().compare_texts(BASE, BASE)
        assert result.sequence_evaluated is True
        assert sum(result.weights.values()) == pytest.approx(1.0)

    def test_default_threshold_is_documented_value(self):
        """默认阈值是一个有出处的常数，不是随手写的魔法数。"""
        assert MAX_SEQUENCE_CHARS == 20_000
        assert PlagiarismChecker().max_sequence_chars == MAX_SEQUENCE_CHARS


class TestSimilarityWeights:
    """权重对象自身的校验。"""

    def test_default_weights_sum_to_one(self):
        assert sum(SimilarityWeights().as_dict().values()) == pytest.approx(1.0)

    def test_negative_weight_is_rejected(self):
        """负权重会让分数失去意义，必须在构造时就拒绝。"""
        with pytest.raises(ValueError):
            SimilarityWeights(sequence_ratio=-0.1)

    def test_all_zero_weights_are_rejected(self):
        """全零权重会让分母为 0，必须拒绝。"""
        with pytest.raises(ValueError):
            SimilarityWeights(
                sequence_ratio=0.0,
                unigram_coverage=0.0,
                bigram_coverage=0.0,
                trigram_coverage=0.0,
                bigram_cosine=0.0,
            )

    def test_custom_weights_change_result(self):
        """自定义权重必须真的影响输出，而不是被静默忽略。"""
        coverage_only = SimilarityWeights(
            sequence_ratio=0.0,
            unigram_coverage=0.0,
            bigram_coverage=1.0,
            trigram_coverage=0.0,
            bigram_cosine=0.0,
        )
        checker = PlagiarismChecker(weights=coverage_only)
        result = checker.compare_texts(BASE, LIGHT_PLAGIARISM)
        assert result.duplication == pytest.approx(result.components["bigram_coverage"])

    def test_weights_are_immutable(self):
        """权重对象是只读的，防止运行期被意外改写。"""
        weights = SimilarityWeights()
        with pytest.raises(FrozenInstanceError):
            weights.sequence_ratio = 0.9


class TestResultObject:
    """结果对象的可读性输出。"""

    def test_summary_contains_key_information(self):
        """``--verbose`` 依赖 summary()，关键信息一个都不能少。"""
        result = PlagiarismChecker().compare_texts(SAMPLE_ORIGINAL, SAMPLE_COPY)
        summary = result.summary()
        assert "重复率" in summary
        assert "bigram_coverage" in summary
        assert "sequence_ratio" in summary

    def test_summary_reports_skipped_signal(self):
        """长文本的降级情况必须在报告里明说，不能悄悄发生。"""
        result = PlagiarismChecker(max_sequence_chars=8).compare_texts(BASE, BASE)
        assert "否（文本过长）" in result.summary()

    def test_elapsed_seconds_is_positive(self):
        assert PlagiarismChecker().compare_texts(BASE, BASE).elapsed_seconds > 0.0

    def test_result_is_a_dataclass_instance(self):
        assert isinstance(PlagiarismChecker().compare_texts(BASE, BASE), DuplicationResult)


class TestCompareFiles:
    """文件级接口。"""

    def test_compare_files_reads_and_scores(self, write_file):
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="orig_add.txt")
        result = PlagiarismChecker().compare_files(original, copy)
        assert result.duplication == pytest.approx(0.71, abs=0.02)

    def test_compare_files_handles_mixed_encodings(self, write_file):
        """原文 GBK、抄袭版 UTF-8 也必须能正确比对。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt", encoding="gbk")
        copy = write_file(SAMPLE_COPY, name="copy.txt", encoding="utf-8")
        mixed = PlagiarismChecker().compare_files(original, copy)
        same = PlagiarismChecker().compare_texts(SAMPLE_ORIGINAL, SAMPLE_COPY)
        assert mixed.duplication == pytest.approx(same.duplication)

    def test_compare_files_propagates_input_errors(self, tmp_path):
        """文件层异常要原样向上传递，不能被引擎吞掉。"""
        from plagcheck.exceptions import InputPathError

        with pytest.raises(InputPathError):
            PlagiarismChecker().compare_files(str(tmp_path / "missing.txt"), str(tmp_path))
