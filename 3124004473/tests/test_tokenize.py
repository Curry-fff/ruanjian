# -*- coding: utf-8 -*-
"""n-gram 切分与词频统计单元测试。

测试函数：:func:`plagcheck.tokenize.ngram_frequencies` 与
:func:`plagcheck.tokenize.total_frequency`。

构造测试数据的思路：n-gram 是一段纯粹的"下标算术"，所以用例必须
把窗口边界逐个钉死——空串、恰好等于窗口长度、比窗口短一个字符、
全是同一个字符（验证计数而非去重）。这些边界正是白盒测试中最容易
写出差一错误的地方。
"""

from __future__ import annotations

import pytest

from plagcheck.tokenize import ngram_frequencies, total_frequency


class TestNgramFrequencies:
    """切分与计数。"""

    def test_empty_text_yields_empty_mapping(self):
        """空文本没有任何窗口，返回空字典。"""
        assert ngram_frequencies("", 2) == {}

    def test_single_characters_are_counted(self):
        """n=1 退化为逐字符计数。"""
        assert ngram_frequencies("aba", 1) == {"a": 2, "b": 1}

    def test_bigrams_of_short_text(self):
        """长度为 3 的文本恰好产生 2 个 bigram。"""
        assert ngram_frequencies("abc", 2) == {"ab": 1, "bc": 1}

    def test_text_shorter_than_window_becomes_one_token(self):
        """文本比窗口短时，整段自成一个 n-gram，而不是返回空字典。

        这是刻意的边界约定：否则"只有两个字"的短文本会被判成 0% 重合。
        """
        assert ngram_frequencies("a", 2) == {"a": 1}
        assert ngram_frequencies("ab", 3) == {"ab": 1}

    def test_text_equal_to_window_length(self):
        """文本长度恰好等于窗口长度：只有一个窗口。"""
        assert ngram_frequencies("ab", 2) == {"ab": 1}
        assert ngram_frequencies("abc", 3) == {"abc": 1}

    def test_repeated_window_is_counted_not_deduplicated(self):
        """重复出现的窗口要按次数累加，不能去重。"""
        assert ngram_frequencies("aaaa", 2) == {"aa": 3}
        assert ngram_frequencies("ababab", 2) == {"ab": 3, "ba": 2}

    def test_window_count_formula_holds(self):
        """窗口总数必须等于 len(text) - n + 1，逐个 n 值验证。"""
        text = "今天天气很好啊"
        for n in range(1, 6):
            frequencies = ngram_frequencies(text, n)
            assert total_frequency(frequencies) == len(text) - n + 1

    def test_chinese_text_does_not_need_a_dictionary(self):
        """纯中文长句按字符切分，窗口内容可人工核对。

        "今天是星期天" 共 6 个字符，相邻两两成对得到 5 个 bigram：
        今天 / 天是 / 是星 / 星期 / 期天，各出现一次。
        """
        frequencies = ngram_frequencies("今天是星期天", 2)
        assert frequencies == {"今天": 1, "天是": 1, "是星": 1, "星期": 1, "期天": 1}
        assert total_frequency(frequencies) == 5

    def test_overlapping_chinese_window_is_counted_twice(self):
        """跨句重复的窗口要累加："…星期天，今天…" 里 "今天" 出现两次。"""
        frequencies = ngram_frequencies("今天是星期天今天", 2)
        assert frequencies["今天"] == 2

    @pytest.mark.parametrize("bad_n", [0, -1, -100])
    def test_non_positive_window_raises_value_error(self, bad_n):
        """窗口长度非法时必须立刻报错，而不是静默返回错误结果。"""
        with pytest.raises(ValueError):
            ngram_frequencies("abc", bad_n)

    def test_returns_plain_dict_like_mapping(self):
        """返回值要支持标准字典操作，方便下游公式直接使用。"""
        frequencies = ngram_frequencies("abc", 2)
        assert frequencies.get("ab") == 1
        assert frequencies.get("zz") is None
        assert set(frequencies) == {"ab", "bc"}


class TestTotalFrequency:
    """总词数统计。"""

    def test_counts_duplicates(self):
        """总词数是"含重复计数"的，不是不同 n-gram 的个数。"""
        assert total_frequency({"a": 2, "b": 3}) == 5

    def test_empty_mapping_is_zero(self):
        """空字典总数为 0，这是 coverage 分母为 0 的来源。"""
        assert total_frequency({}) == 0
