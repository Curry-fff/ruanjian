# -*- coding: utf-8 -*-
"""数值 ↔ 文本 的转换工具。

作业约定的数值写法：

* 自然数：``0``、``1``、``2`` …
* 真分数：``3/5``（五分之三）
* 带分数：``2'3/8``（二又八分之三）

本模块是整个程序里**唯一**负责数值文本转换的地方：生成题目时要写出这些
文本，判分时又要读回这些文本，两条链路共用同一份实现，格式才不会漂移。
"""

from __future__ import annotations

import re
from fractions import Fraction

__all__ = ["NumberFormatError", "format_number", "parse_number"]

#: 允许的撇号写法：英文撇号、排版撇号、中文撇号、反引号
_APOSTROPHES = "'’´`′"

_MIXED_RE = re.compile(rf"^(\d+)[{_APOSTROPHES}](\d+)/(\d+)$")
_FRACTION_RE = re.compile(r"^(\d+)/(\d+)$")
_INTEGER_RE = re.compile(r"^[+-]?\d+$")


class NumberFormatError(ValueError):
    """数值文本不符合约定格式。"""


def format_number(value) -> str:
    """把 ``Fraction`` / ``int`` 格式化成题目要求的写法。

    >>> format_number(Fraction(0))
    '0'
    >>> format_number(Fraction(3, 5))
    '3/5'
    >>> format_number(Fraction(19, 8))
    "2'3/8"
    """
    fraction = value if isinstance(value, Fraction) else Fraction(value)

    sign = "-" if fraction < 0 else ""
    fraction = abs(fraction)

    if fraction.denominator == 1:
        return f"{sign}{fraction.numerator}"
    if fraction.numerator < fraction.denominator:  # 真分数
        return f"{sign}{fraction.numerator}/{fraction.denominator}"

    # 假分数写成带分数：19/8 -> 2'3/8
    whole, rest = divmod(fraction.numerator, fraction.denominator)
    return f"{sign}{whole}'{rest}/{fraction.denominator}"


def parse_number(text) -> Fraction:
    """把一段文本解析成 ``Fraction``，非法输入抛 :class:`NumberFormatError`。

    为了批改别人写的答案文件，这里比生成时更宽容：
    假分数（``7/6``）、内嵌空格（``2 ' 3 / 8``）、几种撇号都接受，
    约分与否不影响结果（``2/4`` 与 ``1/2`` 相等）。
    """
    raw = str(text).strip().replace(" ", "").replace("\u3000", "")
    if not raw:
        raise NumberFormatError("空的数值")

    if _INTEGER_RE.match(raw):
        return Fraction(int(raw))

    matched = _FRACTION_RE.match(raw)
    if matched:
        numerator, denominator = int(matched.group(1)), int(matched.group(2))
        if denominator == 0:
            raise NumberFormatError(f"分母不能为 0：{text!r}")
        return Fraction(numerator, denominator)

    matched = _MIXED_RE.match(raw)
    if matched:
        whole, numerator, denominator = (int(group) for group in matched.groups())
        if denominator == 0:
            raise NumberFormatError(f"分母不能为 0：{text!r}")
        if numerator >= denominator:
            raise NumberFormatError(f"带分数的小数部分必须是真分数：{text!r}")
        return Fraction(whole * denominator + numerator, denominator)

    raise NumberFormatError(f"无法识别的数值：{text!r}")
