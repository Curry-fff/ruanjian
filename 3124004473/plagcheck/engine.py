# -*- coding: utf-8 -*-
"""查重引擎：把各度量融合成一个 0.00 ~ 1.00 的重复率。

调用关系::

    cli.main
      └── PlagiarismChecker.compare_files
            ├── textio.read_text_file        读入两篇论文
            ├── normalize.normalize          抹平书写差异
            ├── tokenize.ngram_frequencies   生成 1/2/3-gram 指纹
            ├── similarity.*                 计算五路信号
            └── SimilarityWeights            加权融合

融合公式::

    duplication = Σ_k w_k · s_k  /  Σ_k w_k

其中 ``k`` 遍历本次实际计算出的信号。之所以写成"除以权重之和"而不是
直接加权求和，是因为顺序敏感信号在超长文本上会被跳过（见
:data:`MAX_SEQUENCE_CHARS`），此时必须在剩余信号上重新归一化权重，
否则分数会凭空掉一截。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .normalize import normalize
from .similarity import cosine, coverage, sequence_ratio
from .textio import read_text_file
from .tokenize import ngram_frequencies

__all__ = [
    "MAX_SEQUENCE_CHARS",
    "DuplicationResult",
    "PlagiarismChecker",
    "SimilarityWeights",
]

#: 启用顺序敏感度量（:func:`plagcheck.similarity.sequence_ratio`）的文本长度上限。
#:
#: ``SequenceMatcher`` 的最坏时间复杂度是输入长度的乘积，对一篇几万字的
#: 论文直接调用会让单次比对轻易突破 5 秒时限。因此超过该阈值时程序会
#: 主动放弃这一路信号，并把它的权重按比例分摊给 n-gram 信号——这一步在
#: 长文本上几乎不损失精度，因为 n-gram 覆盖率在大样本下本身就很稳。
MAX_SEQUENCE_CHARS: int = 20_000

#: 参与计算的 n-gram 窗口长度。
#:
#: ``1`` 并非"退化情形"，而是**字符级覆盖率**——对本题的字符级增删改
#: 语料来说，它是最稳的一路信号（见 :class:`SimilarityWeights`）。
UNIGRAM: int = 1
BIGRAM: int = 2
TRIGRAM: int = 3


@dataclass(frozen=True)
class SimilarityWeights:
    """五路信号的融合权重。

    默认权重不是拍脑袋定的，而是在**真实语料 + 合成变体**上做敏感性
    分析后选定的（详见 ``scripts/calibrate.py`` 与博客的"准确度标定"
    一节）：以 ``orig.txt`` 为原文，对 ``增 / 删 / 乱序`` 三类共 7 份
    变体（标注相似度 0.80）计算平均绝对误差，在各权重组合中，
    本组取值位于误差最优平台（MAE ≈ 0.056）中央，且都是便于沟通的
    整数比例，避免过拟合到少数样本。

    各权重取值的理由：

    * ``sequence_ratio`` = 0.30：唯一顺序敏感的信号，最接近人"这段
      是不是抄的"的直觉，对增删改都稳定，因此给最高权重；
    * ``unigram_coverage`` = 0.25：字符级内容保留率。本题语料是
      **字符级**增删改，字符级覆盖率对它最不敏感；而且它天然免疫
      局部乱序（乱序不改变字符的多重集），是 ``dis_*`` 变体的主力信号；
    * ``bigram_coverage`` = 0.25：局部指纹。改动一个字只破坏 2 个窗口，
      因此即使逐句改写也能保持较高命中；
    * ``trigram_coverage`` = 0.10：对"连续照抄"极敏感，用来拉开
      "整段复制"与"改写后重述"的差距；权重压低是因为它对乱序过于敏感；
    * ``bigram_cosine`` = 0.10：引入对称性与篇幅均衡，避免"抄袭版比
      原文长得多"时分数虚高。
    """

    sequence_ratio: float = 0.30
    unigram_coverage: float = 0.25
    bigram_coverage: float = 0.25
    trigram_coverage: float = 0.10
    bigram_cosine: float = 0.10

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if value < 0.0:
                raise ValueError("权重不能为负数：%s=%r" % (name, value))
        if sum(self.as_dict().values()) <= 0.0:
            raise ValueError("权重之和必须大于 0")

    def as_dict(self) -> dict:
        """返回 ``{信号名: 权重}``，键名与 :attr:`DuplicationResult.components` 对齐。"""
        return {
            "sequence_ratio": self.sequence_ratio,
            "unigram_coverage": self.unigram_coverage,
            "bigram_coverage": self.bigram_coverage,
            "trigram_coverage": self.trigram_coverage,
            "bigram_cosine": self.bigram_cosine,
        }


@dataclass
class DuplicationResult:
    """一次比对的完整结果。

    属性:
        duplication: 最终重复率，取值 ``[0.0, 1.0]``。
        components: 各路信号各自的得分，便于解释"为什么是这个分数"。
        weights: 实际生效的权重（跳过信号后已重新归一化）。
        original_characters: 原文归一化后的字符数。
        copy_characters: 抄袭版归一化后的字符数。
        elapsed_seconds: 整个比对的墙上时间。
        sequence_evaluated: 顺序敏感信号是否真的被计算了。
    """

    duplication: float
    components: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)
    original_characters: int = 0
    copy_characters: int = 0
    elapsed_seconds: float = 0.0
    sequence_evaluated: bool = False

    def summary(self) -> str:
        """生成人类可读的分项报告，供 ``--verbose`` 打印到标准错误输出。"""
        lines = [
            "重复率: %.2f" % self.duplication,
            "原文归一化字符数: %d" % self.original_characters,
            "抄袭版归一化字符数: %d" % self.copy_characters,
            "顺序敏感信号已启用: %s" % ("是" if self.sequence_evaluated else "否（文本过长）"),
            "耗时: %.3f 秒" % self.elapsed_seconds,
            "分项得分:",
        ]
        for name in sorted(self.components):
            lines.append(
                "  %-18s 得分 %.4f  权重 %.2f"
                % (name, self.components[name], self.weights.get(name, 0.0))
            )
        return "\n".join(lines)


class PlagiarismChecker:
    """论文查重器。

    参数:
        weights: 融合权重，默认 :class:`SimilarityWeights`。
        max_sequence_chars: 启用顺序敏感信号的长度上限。
        keep_punctuation: 归一化时是否保留标点，默认 ``False``。

    无状态、可复用：同一个实例可以连续比对多组论文。
    """

    def __init__(
        self,
        weights: SimilarityWeights | None = None,
        max_sequence_chars: int = MAX_SEQUENCE_CHARS,
        keep_punctuation: bool = False,
    ) -> None:
        self.weights = weights if weights is not None else SimilarityWeights()
        self.max_sequence_chars = max_sequence_chars
        self.keep_punctuation = keep_punctuation

    # -- 对外接口 ---------------------------------------------------------

    def compare_files(self, original_path: str, copy_path: str) -> DuplicationResult:
        """读取两个文件并给出重复率。

        参数:
            original_path: 论文原文文件的路径。
            copy_path: 抄袭版论文文件的路径。

        异常:
            InputPathError / InputReadError / EmptyDocumentError:
                见 :mod:`plagcheck.textio`。
        """
        started = time.perf_counter()
        original_text = read_text_file(original_path)
        copy_text = read_text_file(copy_path)
        result = self.compare_texts(original_text, copy_text)
        result.elapsed_seconds = time.perf_counter() - started
        return result

    def compare_texts(self, original_text: str, copy_text: str) -> DuplicationResult:
        """对两段已经读入内存的文本给出重复率。

        约定：若任一篇在归一化后没有任何内容字符（例如整篇都是标点，
        或本身就是空串），重复率记为 ``0.00``。这是"无法比对"而非
        "输入非法"，因此不抛异常。
        """
        started = time.perf_counter()

        original = normalize(original_text, keep_punctuation=self.keep_punctuation)
        copy = normalize(copy_text, keep_punctuation=self.keep_punctuation)

        if not original or not copy:
            return DuplicationResult(
                duplication=0.0,
                components={},
                weights={},
                original_characters=len(original),
                copy_characters=len(copy),
                elapsed_seconds=time.perf_counter() - started,
            )

        components = self._compute_components(original, copy)
        sequence_evaluated = "sequence_ratio" in components
        duplication, effective_weights = self._fuse(components)

        return DuplicationResult(
            duplication=duplication,
            components=components,
            weights=effective_weights,
            original_characters=len(original),
            copy_characters=len(copy),
            elapsed_seconds=time.perf_counter() - started,
            sequence_evaluated=sequence_evaluated,
        )

    # -- 内部实现 ---------------------------------------------------------

    def _compute_components(self, original: str, copy: str) -> dict:
        """计算本次比对实际启用的各路信号。"""
        original_unigrams = ngram_frequencies(original, UNIGRAM)
        copy_unigrams = ngram_frequencies(copy, UNIGRAM)
        original_bigrams = ngram_frequencies(original, BIGRAM)
        copy_bigrams = ngram_frequencies(copy, BIGRAM)
        original_trigrams = ngram_frequencies(original, TRIGRAM)
        copy_trigrams = ngram_frequencies(copy, TRIGRAM)

        components = {
            "unigram_coverage": coverage(original_unigrams, copy_unigrams),
            "bigram_coverage": coverage(original_bigrams, copy_bigrams),
            "trigram_coverage": coverage(original_trigrams, copy_trigrams),
            "bigram_cosine": cosine(original_bigrams, copy_bigrams),
        }

        if self._sequence_signal_affordable(original, copy):
            components["sequence_ratio"] = sequence_ratio(original, copy)

        return components

    def _sequence_signal_affordable(self, original: str, copy: str) -> bool:
        """判断顺序敏感信号是否在时限内算得完。

        用 ``max`` 而不是 ``min``：``SequenceMatcher`` 的开销由**长**的
        那一侧主导，只要有一篇超长就必须放弃。
        """
        return max(len(original), len(copy)) <= self.max_sequence_chars

    def _fuse(self, components: dict) -> tuple:
        """按权重融合各路信号，返回 ``(重复率, 实际生效的权重)``。"""
        configured = self.weights.as_dict()
        weight_total = sum(configured.get(name, 0.0) for name in components)
        if weight_total <= 0.0:
            # 理论上不可达：SimilarityWeights 保证权重之和为正，
            # 且 components 至少含一个有权重的信号。留作防御。
            return 0.0, {}

        effective = {
            name: configured.get(name, 0.0) / weight_total for name in components
        }
        fused = sum(effective[name] * value for name, value in components.items())

        # 夹紧，杜绝浮点误差把结果推到 [0, 1] 之外。
        return min(1.0, max(0.0, fused)), effective
