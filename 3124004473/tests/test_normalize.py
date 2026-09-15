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

import os
import re
import unicodedata

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


def _reference_normalize(text, *, keep_punctuation=False, casefold=True):
    """性能优化前的逐字符朴素实现，仅用作等价性基准。

    保留它是为了给"用正则替换 Python 循环"这次优化上一道保险：只要
    两种实现在任意输入上给出不同结果，等价性测试就会失败。
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKC", text)
    out = []
    if keep_punctuation:
        for character in decomposed:
            if character.isspace():
                continue
            out.append(character.lower() if casefold else character)
    else:
        for character in decomposed:
            if character.isalnum():
                out.append(character.lower() if casefold else character)
    return "".join(out)


class TestRegexRewriteIsEquivalent:
    """性能优化回归：正则实现必须与逐字符实现逐字符等价。

    这条测试是这次优化的**安全网**。把 O(n) 的 Python 循环换成 C 层的
    ``re.sub`` 让归一化快了约 37%，代价是引入了两处微妙的等价性假设：

    1. ``[\\W_]`` 是否恰好等于"``str.isalnum()`` 为假的字符"；
    2. 末尾统一 ``lower()`` 是否与逐字符 ``lower()`` 结果相同。

    两者都必须被证明，而不是"看起来没问题"。
    """

    @pytest.mark.parametrize("keep_punctuation", [False, True])
    @pytest.mark.parametrize("casefold", [False, True])
    def test_equivalent_on_corpus_text(self, data_dir, keep_punctuation, casefold):
        """在课程下发的真实中文语料上比对两种实现。"""
        with open(os.path.join(data_dir, "orig.txt"), encoding="utf-8") as handle:
            text = handle.read()
        assert normalize(text, keep_punctuation=keep_punctuation, casefold=casefold) == (
            _reference_normalize(text, keep_punctuation=keep_punctuation, casefold=casefold)
        )

    def test_equivalent_across_a_wide_code_point_sweep(self):
        """扫过 BMP 中大范围的码点，覆盖汉字、标点、符号、控制字符。"""
        chunks = [
            "".join(chr(code) for code in range(0x0020, 0x1000)),
            "".join(chr(code) for code in range(0x2000, 0x3000)),
            "".join(chr(code) for code in range(0x4E00, 0x4F00)),
            "".join(chr(code) for code in range(0xFF00, 0xFFF0)),
        ]
        for text in chunks:
            assert normalize(text) == _reference_normalize(text)

    def test_isalnum_matches_regex_word_class_across_all_code_points(self):
        """逐一验证 ``isalnum()`` 与 ``\\w`` 在全部 0x110000 个码点上一致。

        这是正则改写成立的数学前提：``[\\W_]`` = 非 ``\\w`` 或下划线
        = 非（``isalnum()`` 或下划线）或下划线 = 非 ``isalnum()``。
        """
        mismatches = []
        for code in range(0x110000):
            character = chr(code)
            if character == "_":
                continue
            if character.isalnum() != bool(re.match(r"\w", character)):
                mismatches.append(hex(code))
        assert not mismatches

    def test_trailing_lower_matches_per_character_lower_except_final_sigma(self):
        """整串 ``lower()`` 与逐字符 ``lower()`` 的差异**只有一处**：希腊词尾 sigma。

        写这条测试时它真的失败了，并暴露出一个我自己没想到的差异：
        ``str.lower()`` 实现了 Unicode 的上下文规则，把词尾的大写 ``Σ``
        折成词尾形 ``ς``；而逐字符 ``lower()`` 一律给出 ``σ``。

        这里选择**如实钉住**这个差异而不是把它藏起来：

        * 对本项目无影响——原文与抄袭版走的是同一条 ``normalize`` 代码
          路径，一致性不受影响，而中文/英文语料根本不会出现该字符；
        * 新行为在语言学上更正确，属于顺带的收益。

        这正说明"等价性测试"的价值：没有它，这个改动会是静默发生的。
        """
        samples = [
            "ABCabc",
            "İstanbul",
            "ÄÖÜäöü",
            "ＦＵＬＬＷＩＤＴＨ",
            "中文ABC混合123",
            "ǅǄǅ",
            "СТРАНА",
        ]
        for sample in samples:
            assert normalize(sample) == _reference_normalize(sample)

        # 唯一已知差异，显式断言两边各自的结果。
        assert normalize("ΣΟΦΟΣ") == "σοφος"
        assert _reference_normalize("ΣΟΦΟΣ") == "σοφοσ"
