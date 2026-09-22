# -*- coding: utf-8 -*-
"""题目文本解析。

``Exercises.txt`` 里的每一行长这样（行尾的等号与空格都允许、编号可有可无）：

    ``3/5 + 1'1/2 = ``
    ``1. 2 × (3 + 1) =``
    ``(2) 6 ÷ 8 =``

本模块用教科书式的递归下降法把它还原成表达式树，优点是：

* 不依赖 ``eval``，输入的式子不可能执行任意代码；
* 拿到的是**结构**（树），批改时才能顺便检查括号与优先级；
* 对写法宽容：全角括号、几种减号/乘号/除号、各种编号前缀都能吃下。

分词时有个刻意的约定：**分数与带分数必须连写**（``3/5``、``2'3/8``），
带空格的 ``2 / 3`` 则当作除法 ``2 ÷ 3``——这与作业说明里“运算符前后加空格”
的书写规范一致。两者数值相同，因此即使对方写混了，判分结果也不会出错。
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .expression import ADD, DIV, MUL, SUB, Binary, Expr, Leaf
from .fraction_utils import NumberFormatError, parse_number

__all__ = ["ParseError", "strip_numbering", "tokenize", "parse_expression", "parse_exercise_line"]

_APOSTROPHES = "'’´`′"

#: 题号前缀："(1) "、"（1）"、"1. "、"1、"、"1) "、"1：" 等
_NUMBERING_RE = re.compile(
    r"^\s*(?:\(\s*\d+\s*\)|（\s*\d+\s*）)\s*"
    r"|^\s*\d+\s*[.、．,，:：)）]\s*"
)

_TOKEN_RE = re.compile(
    rf"""
      (?P<space>\s+)
    | (?P<mixed>\d+[{_APOSTROPHES}]\d+/\d+)
    | (?P<fraction>\d+/\d+)
    | (?P<integer>\d+)
    | (?P<operator>[+\-−–—×xX*·÷/])
    | (?P<lparen>[（(])
    | (?P<rparen>[）)])
    | (?P<other>.)
    """,
    re.VERBOSE,
)

_OPERATOR_MAP = {
    "+": ADD,
    "-": SUB,
    SUB: SUB,
    "–": SUB,
    "—": SUB,
    "*": MUL,
    MUL: MUL,
    "x": MUL,
    "X": MUL,
    "·": MUL,
    "/": DIV,
    DIV: DIV,
}

_NUMBER_KINDS = frozenset({"mixed", "fraction", "integer"})


class ParseError(ValueError):
    """题目文本无法解析。"""


def strip_numbering(line: str) -> str:
    """去掉行首的题号前缀，例如 ``"1. 1 + 2 ="`` → ``"1 + 2 ="``。"""
    return _NUMBERING_RE.sub("", line, count=1)


def tokenize(text: str) -> List[Tuple[str, str]]:
    """把文本切成 ``(类别, 原文)`` 序列；等号及其之后的内容直接丢弃。"""
    tokens: List[Tuple[str, str]] = []
    position = 0
    length = len(text)
    while position < length:
        if text[position] == "=":
            break  # 等号后面不再有有效内容
        matched = _TOKEN_RE.match(text, position)
        if matched is None:  # pragma: no cover - _TOKEN_RE 的 other 分支总能命中
            raise ParseError(f"无法识别的字符 {text[position]!r}（位置 {position}）")
        kind = matched.lastgroup
        value = matched.group()
        position = matched.end()
        if kind == "space":
            continue
        if kind == "other":
            raise ParseError(f"无法识别的字符 {value!r}：{text!r}")
        tokens.append((kind, value))
    return tokens


class _Parser:
    """递归下降解析器：``expr -> term (('+'|'-') term)*``，``term -> factor (('×'|'÷') factor)*``。"""

    def __init__(self, tokens: List[Tuple[str, str]], source: str):
        self._tokens = tokens
        self._source = source
        self._index = 0

    def parse(self) -> Expr:
        if not self._tokens:
            raise ParseError(f"空题目：{self._source!r}")
        expression = self._parse_expression()
        if self._index != len(self._tokens):
            rest = " ".join(value for _, value in self._tokens[self._index:])
            raise ParseError(f"题目里有多余的内容：{rest!r}（{self._source!r}）")
        return expression

    def _peek(self):
        if self._index < len(self._tokens):
            return self._tokens[self._index]
        return None

    def _parse_expression(self) -> Expr:
        node = self._parse_term()
        while True:
            token = self._peek()
            if token is None or token[0] != "operator" or _OPERATOR_MAP[token[1]] not in (ADD, SUB):
                return node
            self._index += 1
            node = Binary(_OPERATOR_MAP[token[1]], node, self._parse_term())

    def _parse_term(self) -> Expr:
        node = self._parse_factor()
        while True:
            token = self._peek()
            if token is None or token[0] != "operator" or _OPERATOR_MAP[token[1]] not in (MUL, DIV):
                return node
            self._index += 1
            node = Binary(_OPERATOR_MAP[token[1]], node, self._parse_factor())

    def _parse_factor(self) -> Expr:
        token = self._peek()
        if token is None:
            raise ParseError(f"题目在运算符后意外结束：{self._source!r}")
        kind, value = token
        self._index += 1
        if kind in _NUMBER_KINDS:
            try:
                return Leaf(parse_number(value))
            except NumberFormatError as error:
                raise ParseError(f"{error}（{self._source!r}）") from error
        if kind == "lparen":
            node = self._parse_expression()
            closing = self._peek()
            if closing is None or closing[0] != "rparen":
                raise ParseError(f"括号不匹配：{self._source!r}")
            self._index += 1
            return node
        raise ParseError(f"这里不该出现 {value!r}：{self._source!r}")


def parse_expression(text: str) -> Expr:
    """解析一段算术表达式文本（不含题号，等号可有可无）。"""
    return _Parser(tokenize(text), text).parse()


def parse_exercise_line(line: str) -> Expr:
    """解析 ``Exercises.txt`` 中的一整行，自动去掉题号前缀。"""
    return parse_expression(strip_numbering(line))
