# -*- coding: utf-8 -*-
"""算术表达式树：精确求值、按约定打印、以及用于查重的规范形式。

设计要点
--------

1. 节点只有两种：:class:`Leaf`（自然数或分数）与 :class:`Binary`（+ − × ÷）。
   对应文法 ``e = n | e1 + e2 | e1 − e2 | e1 × e2 | e1 ÷ e2 | (e)``。
2. :meth:`Expr.evaluate` 全程使用 ``fractions.Fraction``，没有浮点误差，
   所以 ``1/6 + 1/8`` 一定是 ``7/24``。
3. :meth:`Expr.to_text` 按“最小括号”规则打印：只在语法确实需要的地方加括号，
   打印结果再解析回来仍是同一棵树（可逆），见 ``tests/test_expression.py``。
4. :meth:`Expr.canonical_key` 给出“交换律等价类”的规范形式，用于查重：
   仅对 ``+`` / ``×`` 的两个子节点按规范键排序（树的形状、左结合关系都不变），
   于是 ——

   * ``23 + 45`` 与 ``45 + 23`` 判为重复；
   * ``3 + (2 + 1)`` 与 ``1 + 2 + 3``（即 ``(1+2)+3``）判为重复；
   * ``1 + 2 + 3``（``(1+2)+3``）与 ``3 + 2 + 1``（``(3+2)+1``）**不**重复。

   最后一条正是作业说明里举的反例：只交换某个节点的左右孩子，无法把
   ``(1+2)+3`` 变成 ``(3+2)+1``（后者要先把 ``3+2`` 缩成一个整体才行），
   因此规范形式只做“节点内交换”，不做结合律展平。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Optional, Tuple

from .fraction_utils import format_number

__all__ = [
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "OPERATORS",
    "SYMBOLS",
    "ASCII_SYMBOLS",
    "PRECEDENCE",
    "COMMUTATIVE",
    "Expr",
    "Leaf",
    "Binary",
    "make",
]

ADD = "+"
SUB = "−"  # U+2212 MINUS SIGN，与作业说明里的减号一致
MUL = "×"  # U+00D7
DIV = "÷"  # U+00F7

OPERATORS: Tuple[str, ...] = (ADD, SUB, MUL, DIV)

#: 默认输出用的运算符（作业说明里的写法）
SYMBOLS: Dict[str, str] = {ADD: "+", SUB: SUB, MUL: MUL, DIV: DIV}
#: ``--ascii`` 时使用的运算符，方便喂给只认 ASCII 的脚本
ASCII_SYMBOLS: Dict[str, str] = {ADD: "+", SUB: "-", MUL: "*", DIV: "/"}

PRECEDENCE: Dict[str, int] = {ADD: 1, SUB: 1, MUL: 2, DIV: 2}
#: 满足交换律的运算符，查重时可以交换左右孩子
COMMUTATIVE = frozenset({ADD, MUL})
#: 规范键里用 ASCII 记运算符，避免不同符号集产生不同的键
_OPERATOR_CODES: Dict[str, str] = {ADD: "+", SUB: "-", MUL: "*", DIV: "/"}


class Expr:
    """表达式节点基类。"""

    __slots__ = ()

    def evaluate(self) -> Fraction:
        """精确求值。"""
        raise NotImplementedError

    @property
    def op_count(self) -> int:
        """该子表达式包含的运算符个数。"""
        raise NotImplementedError

    @property
    def is_leaf(self) -> bool:
        return self.op_count == 0

    def to_text(self, symbols: Optional[Dict[str, str]] = None) -> str:
        """打印成题目文本（不含等号）。"""
        return self._render(0, False, symbols or SYMBOLS)

    def canonical_key(self) -> str:
        """交换律等价类的规范键（用于查重）。"""
        raise NotImplementedError

    def _render(self, parent_precedence: int, is_right: bool, symbols: Dict[str, str]) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class Leaf(Expr):
    """叶子节点：一个自然数或一个分数。"""

    number: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.number, Fraction):
            object.__setattr__(self, "number", Fraction(self.number))

    def evaluate(self) -> Fraction:
        return self.number

    @property
    def op_count(self) -> int:
        return 0

    def canonical_key(self) -> str:
        return format_number(self.number)

    def _render(self, parent_precedence: int, is_right: bool, symbols: Dict[str, str]) -> str:
        return format_number(self.number)


@dataclass(frozen=True)
class Binary(Expr):
    """内部节点：``left op right``。"""

    op: str
    left: Expr
    right: Expr

    def __post_init__(self) -> None:
        if self.op not in PRECEDENCE:
            raise ValueError(f"未知运算符：{self.op!r}")

    def evaluate(self) -> Fraction:
        left, right = self.left.evaluate(), self.right.evaluate()
        if self.op == ADD:
            return left + right
        if self.op == SUB:
            return left - right
        if self.op == MUL:
            return left * right
        return left / right  # DIV

    @property
    def op_count(self) -> int:
        return 1 + self.left.op_count + self.right.op_count

    def canonical_key(self) -> str:
        left, right = self.left.canonical_key(), self.right.canonical_key()
        if self.op in COMMUTATIVE and right < left:
            left, right = right, left
        code = _OPERATOR_CODES[self.op]
        return f"{code}[{left},{right}]"

    def _render(self, parent_precedence: int, is_right: bool, symbols: Dict[str, str]) -> str:
        precedence = PRECEDENCE[self.op]
        text = (
            f"{self.left._render(precedence, False, symbols)}"
            f" {symbols[self.op]} "
            f"{self.right._render(precedence, True, symbols)}"
        )
        if _needs_parentheses(precedence, parent_precedence, is_right):
            return f"({text})"
        return text


def _needs_parentheses(precedence: int, parent_precedence: int, is_right: bool) -> bool:
    """判断当前节点相对父节点是否需要括号。

    规则（四则运算均为左结合）：

    * 优先级低于父节点 —— 必须加括号：``(1 + 2) × 3``；
    * 优先级高于父节点 —— 不用加：``1 + 2 × 3``；
    * 优先级相同且自己是父节点的左孩子 —— 不用加：``(1 + 2) + 3`` 写成 ``1 + 2 + 3``；
    * 优先级相同且自己是父节点的右孩子 —— 必须加：``1 − (2 − 3)``、``6 ÷ (2 ÷ 3)``，
      否则左结合会把括号里的运算提前算掉。
    """
    if precedence < parent_precedence:
        return True
    return precedence == parent_precedence and is_right


def make(op: str, left: Expr, right: Expr) -> Binary:
    """构造内部节点的语法糖。"""
    return Binary(op, left, right)
