# -*- coding: utf-8 -*-
"""题目生成器：在作业约束下随机造题，并保证同一次运行内不重复。

约束与实现手段
--------------

======================  ==========================================================
作业约束                实现手段
======================  ==========================================================
数值范围               叶子（自然数、真分数的分子分母）都 < ``r``
计算过程不出现负数      构造 ``e1 − e2`` 时按数值大小摆放左右孩子，保证 ``e1 ≥ e2``
除法的结果是真分数      构造 ``e1 ÷ e2`` 时要求 ``0 < e1 < e2``，否则换一组孩子
运算符不超过 3 个        自底向上定深构造，深度即运算符个数
同一次运行不重复        用规范键查重（见 ``expression.Expr.canonical_key``）
======================  ==========================================================

“自底向上定深构造 + 就地交换”这套做法比“先随机生成再整体检查”高效得多：
减法与除法节点自己就能把左右孩子摆对位置，几乎不需要整题重来，
因此在很小的 ``r``（题目空间本来就很小）下也不会退化成一味空转。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Set

from .expression import ADD, DIV, MUL, SUB, Binary, Expr, Leaf, OPERATORS, SYMBOLS
from .fraction_utils import format_number

__all__ = [
    "Problem",
    "GenerationConfig",
    "GenerationResult",
    "generate",
    "generate_problems",
]

#: 每个内部节点最多重新抽几组孩子
_NODE_TRIES = 12
#: 至少尝试多少次（题目空间很小时才会用上）
_MIN_ATTEMPTS = 3000
#: 每题平均尝试次数上限
_ATTEMPTS_PER_PROBLEM = 200
#: 连续这么多次没能造出新题，就认为题目空间已被穷尽
_STALL_LIMIT = 3000
#: 抽取运算符的权重：加减多一点，乘除少一点，题目更像小学课本
_OPERATOR_WEIGHTS = (3, 3, 2, 2)


class _BuildError(RuntimeError):
    """当前约束下这个形状造不出来（只有除法的严格约束会触发）。"""


def _is_zero_leaf(expr: Expr) -> bool:
    """判断节点是不是一个“字面量的 0”。"""
    return expr.is_leaf and expr.evaluate() == 0


@dataclass(frozen=True)
class Problem:
    """一道题目：一棵表达式树，外加若干派生文本。"""

    expr: Expr

    @property
    def value(self) -> Fraction:
        return self.expr.evaluate()

    @property
    def op_count(self) -> int:
        return self.expr.op_count

    def exercise_text(self, symbols: Optional[Dict[str, str]] = None, with_equals: bool = True) -> str:
        """题目文本，例如 ``1/6 + 1/8 = ``。"""
        text = self.expr.to_text(symbols or SYMBOLS)
        return f"{text} = " if with_equals else text

    def answer_text(self) -> str:
        """答案文本，例如 ``7/24``、``2'3/8``。"""
        return format_number(self.value)

    def canonical_key(self) -> str:
        return self.expr.canonical_key()


@dataclass
class GenerationConfig:
    """生成参数。"""

    count: int
    value_range: int
    max_ops: int = 3
    min_ops: int = 1
    #: 叶子取真分数的概率（范围内的分母不存在时自动失效）
    fraction_ratio: float = 0.35
    #: 叶子取 0 的概率（略微压一压，避免满屏 ``0 + 0``）
    zero_ratio: float = 0.10
    #: 是否避免 ``0 + x``、``x × 0`` 这类“白给”的形状（r == 1 时范围内只有 0，自动关闭）
    avoid_trivial_zero: bool = True
    #: 是否要求每一步的中间结果也 < value_range
    strict_range: bool = False
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("题目个数必须大于 0")
        if self.value_range < 1:
            raise ValueError("数值范围 r 必须是不小于 1 的自然数")
        if not 1 <= self.min_ops <= self.max_ops <= 3:
            raise ValueError("运算符个数必须在 1~3 之间（作业要求不超过 3 个）")


@dataclass
class GenerationResult:
    """生成结果：题目列表 + 一些用于提示用户的信息。"""

    problems: List[Problem] = field(default_factory=list)
    attempts: int = 0
    #: True 表示题目空间已穷尽，没能凑够 count 道（例如 -r 1 时最多 3 道题）
    exhausted: bool = False

    def __len__(self) -> int:
        return len(self.problems)


class _Builder:
    """按约束自底向上构造表达式。"""

    def __init__(self, config: GenerationConfig, rng: random.Random):
        self._config = config
        self._rng = rng
        self._positive_naturals: Sequence[Fraction] = [Fraction(n) for n in range(1, config.value_range)]
        self._denominators: Sequence[int] = list(range(2, config.value_range))
        # r == 1 时范围内只有 0，此时不能再挑剔，否则一道题都造不出来；
        # r 很小（2、3）时题目空间本来就窄，也不挑剔，免得凑不够道数。
        self._avoid_trivial_zero = config.avoid_trivial_zero and config.value_range >= 4

    @property
    def has_fraction(self) -> bool:
        """范围内是否存在真分数（分母要 ≥ 2 且 < r）。"""
        return bool(self._denominators)

    def leaf(self) -> Leaf:
        """随机造一个范围内的数：自然数或真分数。"""
        rng = self._rng
        if self.has_fraction and rng.random() < self._config.fraction_ratio:
            denominator = rng.choice(self._denominators)
            return Leaf(Fraction(rng.randrange(1, denominator), denominator))
        if self._positive_naturals and rng.random() < self._config.zero_ratio:
            return Leaf(Fraction(0))
        if not self._positive_naturals:  # r == 1，范围内只有 0
            return Leaf(Fraction(0))
        return Leaf(rng.choice(self._positive_naturals))

    def build(self, op_count: int) -> Expr:
        """造一个恰好含 ``op_count`` 个运算符的表达式。"""
        if op_count <= 0:
            return self.leaf()
        for _ in range(_NODE_TRIES):
            left_ops = self._rng.randint(0, op_count - 1)
            right_ops = op_count - 1 - left_ops
            try:
                left = self.build(left_ops)
                right = self.build(right_ops)
            except _BuildError:
                continue
            operator = self._rng.choices(OPERATORS, weights=_OPERATOR_WEIGHTS)[0]
            combined = self._combine(operator, left, right)
            if combined is not None:
                return combined
        raise _BuildError

    def _combine(self, operator: str, left: Expr, right: Expr) -> Optional[Binary]:
        """把两个孩子按运算符拼起来；不满足约束时返回 ``None`` 表示需要重抽。"""
        left_value, right_value = left.evaluate(), right.evaluate()

        if operator == ADD:
            if self._avoid_trivial_zero and (_is_zero_leaf(left) or _is_zero_leaf(right)):
                return None  # 0 + x 属于“白给”，换个形状重来
            if self._config.strict_range and left_value + right_value >= self._config.value_range:
                return None
            return Binary(ADD, left, right)

        if operator == MUL:
            if self._avoid_trivial_zero and (_is_zero_leaf(left) or _is_zero_leaf(right)):
                return None  # x × 0 同理
            if self._config.strict_range and left_value * right_value >= self._config.value_range:
                return None
            return Binary(MUL, left, right)

        if operator == SUB:
            if self._avoid_trivial_zero and left_value == 0 and right_value == 0:
                return None  # 0 − 0 同样是废话
            # 保证 e1 ≥ e2：谁的数值大谁当被减数，等价于把两个孩子对调
            if left_value >= right_value:
                return Binary(SUB, left, right)
            if right_value >= left_value:
                return Binary(SUB, right, left)
            return None  # pragma: no cover - Fraction 一定可比

        if operator == DIV:
            # 要求结果是真分数：0 < 被除数 < 除数
            if left_value <= 0 or right_value <= 0 or left_value == right_value:
                return None
            if left_value < right_value:
                return Binary(DIV, left, right)
            return Binary(DIV, right, left)

        raise ValueError(f"未知运算符：{operator!r}")  # pragma: no cover


def generate(config: GenerationConfig) -> GenerationResult:
    """按配置生成题目，同一次调用内不出现等价题目。"""
    rng = random.Random(config.seed)
    builder = _Builder(config, rng)

    problems: List[Problem] = []
    seen: Set[str] = set()
    attempts = 0
    stalled = 0
    max_attempts = max(_MIN_ATTEMPTS, config.count * _ATTEMPTS_PER_PROBLEM)

    while len(problems) < config.count and attempts < max_attempts and stalled < _STALL_LIMIT:
        attempts += 1
        target = rng.randint(config.min_ops, config.max_ops)
        try:
            expr = builder.build(target)
        except _BuildError:
            stalled += 1
            continue
        key = expr.canonical_key()
        if key in seen:
            stalled += 1
            continue
        seen.add(key)
        problems.append(Problem(expr))
        stalled = 0

    return GenerationResult(
        problems=problems,
        attempts=attempts,
        exhausted=len(problems) < config.count,
    )


def generate_problems(count: int, value_range: int, **kwargs) -> GenerationResult:
    """:func:`generate` 的便捷写法。"""
    return generate(GenerationConfig(count=count, value_range=value_range, **kwargs))
