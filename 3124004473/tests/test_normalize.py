# -*- coding: utf-8 -*-
"""归一化单元测试。

测试函数：:func:`plagcheck.normalize.normalize` 与
:func:`plagcheck.normalize.is_effectively_empty`。

构造测试数据的思路：归一化的目的是"抹平无意义的书写差异"，因此
每个用例都构造一对**应当被视为等价**的文本，断言它们归一化后
逐字符相同；再补充若干"不应被过度抹平"的反向用例（大小写、
标点保留开关、不同汉字），防止把归一化写成"什么都删"。
"""

from __future__ import annotations

import pytest

from plagcheck.normalize import is_effectively_empty, normalize


class TestNormalizeBasics:
    """基本行为：空输入、纯文本、字符保留范围。"""

    def test_empty_string_returns_empty_string(self):
        """空串是最小输入，必须返回空串而不是 None。"""
        assert normalize("") == ""

    def test_chinese_characters_are_preserved(self):
        """汉字必须全部保留，一个都不能删。"""
        assert normalize("今天是星期天") == "今天是星期天"

    def test_ascii_letters_are_lowercased(self):
        """默认折叠大小写，Python 与 python 视为同一内容。"""
        assert normalize("PyThOn") == "python"

    def test_casefold_can_be_disabled(self):
        """关掉折叠开关后必须原样保留大小写。"""
        assert normalize("PyThOn", casefold=False) == "PyThOn"


class TestNormalizeNoiseRemoval:
    """差异抹平：标点、空白、全角半角、换行。"""

    def test_punctuation_is_dropped_by_default(self):
        """标点差异是最常见的伪装手段，默认必须被抹平。"""
        assert normalize("今天，天气晴。") == "今天天气晴"

    @pytest.mark.parametrize(
        "noisy",
        [
            "今天是星期天，天气晴，今天晚上我要去看电影。",
            "今天是星期天 天气晴 今天晚上我要去看电影",
            "今天是星期天\n\n天气晴\r\n今天晚上我要去看电影",
            "【今天是星期天】天气晴！今天晚上我要去看电影？",
            "今天是星期天…天气晴——今天晚上我要去看电影~",
        ],
    )
    def test_writing_variants_collapse_to_the_same_text(self, noisy):
        """同一句话的多种标点/空白写法，归一化后必须完全一致。"""
        assert normalize(noisy) == "今天是星期天天气晴今天晚上我要去看电影"

    def test_fullwidth_characters_are_folded_to_halfwidth(self):
        """NFKC 兼容分解：全角字母数字要变成半角。"""
        assert normalize("ＡＢＣ１２３") == "abc123"

    def test_whitespace_only_text_becomes_empty(self):
        """只有空白与标点的文本，归一化后为空。"""
        assert normalize(" \t\r\n，。！？") == ""
        assert is_effectively_empty(normalize(" \t\r\n，。！？"))

    def test_keep_punctuation_switch_preserves_punctuation(self):
        """打开保留开关时，标点要留下，但空白仍然被丢弃。

        注意 NFKC 只把"兼容形式"折成常规形式：全角逗号 ``，`` 会变成
        半角 ``,``，而句号 ``。`` 本身就是规范形式，NFKC 不会把它
        改成 ``.``。这里如实断言这一细节。
        """
        assert normalize("今天，天气晴。", keep_punctuation=True) == "今天,天气晴。"
        assert normalize("a b\tc", keep_punctuation=True) == "abc"

    def test_keep_punctuation_still_drops_whitespace_only(self):
        """保留标点模式下，纯空白输入依然归一化为空串。"""
        assert normalize("   \n\t ", keep_punctuation=True) == ""


class TestNormalizeProperties:
    """性质测试：幂等性、非负性、不抛异常。"""

    def test_idempotent(self):
        """归一化两次与一次结果相同——这是"稳定指纹"的前提。"""
        once = normalize("今天，ＡＢＣ天气晴！")
        assert normalize(once) == once

    def test_output_never_longer_than_input(self):
        """归一化只会删字符或等长替换，绝不会变长。"""
        for text in ["今天是星期天", "ＡＢＣ", "a b c", "……", "x" * 1000]:
            assert len(normalize(text)) <= len(text)

    def test_never_raises_on_arbitrary_unicode(self):
        """面对各种怪异字符都必须返回字符串，绝不抛异常。"""
        weird = "".join(chr(code) for code in range(0x20, 0x300))
        assert isinstance(normalize(weird), str)

    def test_emoji_and_symbols_are_dropped(self):
        """表情与符号不承载论文内容，默认丢弃。"""
        assert normalize("论文😀很好👍") == "论文很好"


class TestIsEffectivelyEmpty:
    """空白检测辅助函数。"""

    @pytest.mark.parametrize("value", ["", " ", "，。", "\n\t"])
    def test_true_cases(self, value):
        """这些输入都没有可比对内容。"""
        assert is_effectively_empty(normalize(value)) is True

    @pytest.mark.parametrize("value", ["a", "汉", "0"])
    def test_false_cases(self, value):
        """哪怕只有一个内容字符，也不算空。"""
        assert is_effectively_empty(normalize(value)) is False
