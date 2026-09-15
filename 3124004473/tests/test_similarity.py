# -*- coding: utf-8 -*-
"""相似度度量单元测试。

测试函数：:func:`plagcheck.similarity.coverage`、``cosine``、``jaccard``、
``sequence_ratio``。

构造测试数据的思路：四种度量都是"数学定义"，所以用**极小的手算样本**
（一两个键的词频字典、两三个字符的字符串）把公式逐项验证，比用真实
语料更容易定位错误。另外专门覆盖三类边界：空输入（分母为 0）、
完全不相交、完全一致；并统一断言输出恒落在 ``[0, 1]`` 内。
"""

from __future__ import annotations

import pytest

from plagcheck.similarity import cosine, coverage, jaccard, sequence_ratio


class TestCoverage:
    """含词频的覆盖率（主指标）。"""

    def test_identical_mappings_score_one(self):
        """完全一致 → 1.0。"""
        assert coverage({"ab": 3, "bc": 2}, {"ab": 3, "bc": 2}) == 1.0

    def test_disjoint_mappings_score_zero(self):
        """毫无交集 → 0.0。"""
        assert coverage({"ab": 1}, {"xy": 1}) == 0.0

    def test_empty_target_scores_zero(self):
        """分母为 0 的边界必须返回 0.0，而不是抛 ZeroDivisionError。"""
        assert coverage({"ab": 1}, {}) == 0.0
        assert coverage({}, {}) == 0.0

    def test_empty_reference_scores_zero(self):
        """原文为空时抄袭版无从覆盖。"""
        assert coverage({}, {"ab": 1}) == 0.0

    def test_repeated_target_gram_caps_at_reference_count(self):
        """min() 语义：抄袭版把某段重复 5 次，原文只有 2 次，只能算 2 次。"""
        # min(2, 5) / 5 = 0.4
        assert coverage({"ab": 2}, {"ab": 5}) == pytest.approx(0.4)

    def test_partial_overlap(self):
        """一半内容来自原文 → 0.5。"""
        assert coverage({"ab": 1}, {"ab": 1, "xy": 1}) == pytest.approx(0.5)

    def test_target_subset_of_reference_scores_one(self):
        """抄袭版是原文的真子集（摘抄式抄袭）→ 1.0。"""
        assert coverage({"ab": 1, "bc": 1, "cd": 1}, {"ab": 1, "bc": 1}) == 1.0

    def test_is_asymmetric(self):
        """参数顺序必须影响结果，这正是"以抄袭版为分母"的定义。"""
        original = {"ab": 1, "bc": 1, "cd": 1}
        copy = {"ab": 1}
        assert coverage(original, copy) == 1.0
        assert coverage(copy, original) == pytest.approx(1 / 3)


class TestCosine:
    """词频向量余弦相似度。"""

    def test_identical_mappings_score_one(self):
        """同向向量夹角为 0，余弦为 1。"""
        assert cosine({"ab": 3, "bc": 2}, {"ab": 3, "bc": 2}) == pytest.approx(1.0)

    def test_orthogonal_mappings_score_zero(self):
        """没有共同维度 → 0。"""
        assert cosine({"ab": 1}, {"xy": 1}) == 0.0

    def test_empty_input_scores_zero(self):
        """零向量的余弦没有定义，约定记 0.0。"""
        assert cosine({}, {}) == 0.0
        assert cosine({}, {"ab": 1}) == 0.0
        assert cosine({"ab": 1}, {}) == 0.0

    def test_proportional_vectors_score_one(self):
        """仅倍数不同（文本长度不同但用词比例一致）→ 1.0。"""
        assert cosine({"ab": 1, "bc": 1}, {"ab": 4, "bc": 4}) == pytest.approx(1.0)

    def test_half_overlap_on_one_axis(self):
        """手算校验：cos = 1/(√1·√2) = 0.7071。"""
        assert cosine({"ab": 1}, {"ab": 1, "xy": 1}) == pytest.approx(0.70710678, rel=1e-6)

    def test_is_symmetric(self):
        """余弦是对称的，交换参数结果不变。"""
        left = {"ab": 2, "bc": 1}
        right = {"ab": 1, "cd": 5}
        assert cosine(left, right) == pytest.approx(cosine(right, left))

    def test_never_exceeds_one(self):
        """浮点误差不得把结果推过 1.0。"""
        frequencies = {"a" * 20: 10 ** 6, "b": 1}
        assert cosine(frequencies, frequencies) <= 1.0


class TestJaccard:
    """多重集 Jaccard 系数（用于报告，不参与融合）。"""

    def test_identical_mappings_score_one(self):
        assert jaccard({"ab": 2}, {"ab": 2}) == 1.0

    def test_disjoint_mappings_score_zero(self):
        assert jaccard({"ab": 1}, {"xy": 1}) == 0.0

    def test_both_empty_scores_zero(self):
        assert jaccard({}, {}) == 0.0

    def test_multiset_semantics(self):
        """Σmin/Σmax：(1+1)/(1+4) = 0.4。"""
        assert jaccard({"ab": 1, "bc": 1}, {"ab": 1, "bc": 4}) == pytest.approx(0.4)


class TestSequenceRatio:
    """顺序敏感的序列匹配率。"""

    def test_identical_text_scores_one(self):
        assert sequence_ratio("今天是星期天", "今天是星期天") == 1.0

    def test_completely_different_text_scores_zero(self):
        assert sequence_ratio("abcd", "wxyz") == 0.0

    def test_empty_input_scores_zero(self):
        assert sequence_ratio("", "abc") == 0.0
        assert sequence_ratio("abc", "") == 0.0
        assert sequence_ratio("", "") == 0.0

    def test_short_sample_from_assignment(self):
        """"今天…" 两句话的顺序相似度可以被人工估计在 0.7 附近。"""
        ratio = sequence_ratio(
            "今天是星期天天气晴今天晚上我要去看电影",
            "今天是周天天气晴朗我晚上要去看电影",
        )
        assert 0.6 < ratio < 0.9

    def test_detects_reordering_that_bag_of_ngrams_cannot(self):
        """顺序被完全打乱时，序列度量必须显著低于 1.0。"""
        original = "甲乙丙丁戊己庚辛壬癸"
        shuffled = "癸壬辛庚己戊丁丙乙甲"
        assert sequence_ratio(original, shuffled) < 0.5

    def test_single_substitution_loses_little(self):
        """只改一个字，相似度应当保持在很高的水平。"""
        ratio = sequence_ratio("今天天气非常晴朗", "今天天气非常晴郎")
        assert ratio > 0.8

    def test_insertion_is_penalised_less_than_replacement(self):
        """插入一段新文字，比重写同样长度的原文扣分更少。

        ``base`` 共 14 字。插入 "万里无云" 后原文的 14 个字被完整保留
        （只是被隔开），而把 "晴朗适合" 整段换成 "阴雨连绵" 时，
        原文有 4 个字被彻底替换掉——后者的相似度理应更低。
        """
        base = "今天天气非常晴朗适合出门散步"
        inserted = base[:6] + "万里无云" + base[6:]
        rewritten = base[:6] + "阴雨连绵" + base[10:]
        assert sequence_ratio(base, inserted) > sequence_ratio(base, rewritten)


@pytest.mark.parametrize(
    "metric",
    [coverage, cosine, jaccard],
)
def test_frequency_metrics_stay_within_unit_interval(metric):
    """所有词频度量的输出都必须落在 [0, 1]。"""
    samples = [
        ({"a": 1}, {"a": 1}),
        ({"a": 1}, {"b": 1}),
        ({"a": 5, "b": 3}, {"a": 1, "c": 9}),
        ({}, {"a": 1}),
        ({}, {}),
        ({"a": 1000}, {"a": 1}),
    ]
    for left, right in samples:
        value = metric(left, right)
        assert 0.0 <= value <= 1.0
