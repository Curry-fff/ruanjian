# -*- coding: utf-8 -*-
"""生成器测试：作业里 1~8 条约束都要逐条钉住。

这些用例不是“跑一遍看看有没有报错”，而是把生成结果**重新解析、逐节点检查**，
所以任何一条约束被破坏都会被抓住。
"""

import time
import unittest
from fractions import Fraction
from typing import Iterator

from arithmetic.expression import ADD, DIV, MUL, SUB, Binary, Expr, Leaf
from arithmetic.generator import GenerationConfig, generate
from arithmetic.parser import parse_expression

RANGES = (2, 3, 5, 10, 20, 100)
SEEDS = range(6)


def walk(expr: Expr) -> Iterator[Expr]:
    """深度优先遍历表达式树的全部节点。"""
    yield expr
    if isinstance(expr, Binary):
        yield from walk(expr.left)
        yield from walk(expr.right)


class _ConstraintAssertions(unittest.TestCase):
    """共用的约束断言：把生成结果拆开、逐节点核对。"""

    def assert_problem_is_legal(self, problem, value_range: int, strict_range: bool = False) -> None:
        expr = problem.expr

        # 约束 5：运算符个数不超过 3 个，且至少有一个（不然不成其为四则运算题）
        self.assertGreaterEqual(expr.op_count, 1)
        self.assertLessEqual(expr.op_count, 3)

        for node in walk(expr):
            if isinstance(node, Leaf):
                # 约束 2：自然数、真分数及其分母都在 [0, r) 内
                self.assertGreaterEqual(node.number, 0)
                self.assertLess(node.number, value_range)
                self.assertLess(node.number.denominator, value_range)
                if node.number.denominator > 1:
                    self.assertLess(node.number.numerator, node.number.denominator)
                continue

            left_value, right_value = node.left.evaluate(), node.right.evaluate()
            if node.op == SUB:
                # 约束 3：计算过程不出现负数 → e1 ≥ e2
                self.assertGreaterEqual(left_value, right_value)
                self.assertGreaterEqual(left_value - right_value, 0)
            elif node.op == DIV:
                # 约束 4：除法的结果是真分数 → 0 < e1 < e2
                self.assertGreater(left_value, 0)
                self.assertLess(left_value, right_value)
                self.assertLess(node.evaluate(), 1)
            if strict_range:
                self.assertLess(node.evaluate(), value_range)

        # 打印出来的文本必须能被解析回同一道题（值一致）
        reparsed = parse_expression(problem.exercise_text())
        self.assertEqual(reparsed.evaluate(), problem.value)

class GeneratorConstraintTest(_ConstraintAssertions):
    """作业约束 1~8：范围、无负数、除法为真分数、运算符个数、查重、万道规模。"""

    def test_constraints_hold_for_many_ranges_and_seeds(self):
        for value_range in RANGES:
            for seed in SEEDS:
                with self.subTest(value_range=value_range, seed=seed):
                    result = generate(
                        GenerationConfig(count=25, value_range=value_range, seed=seed)
                    )
                    self.assertTrue(result.problems, "一道题都没生成出来")
                    for problem in result.problems:
                        self.assert_problem_is_legal(problem, value_range)

    def test_no_duplicates_in_one_run(self):
        """约束 6：同一次运行内任何两道题都不等价。"""
        for value_range in RANGES:
            with self.subTest(value_range=value_range):
                result = generate(GenerationConfig(count=200, value_range=value_range, seed=2024))
                keys = [problem.canonical_key() for problem in result.problems]
                self.assertEqual(len(keys), len(set(keys)))

    def test_no_duplicates_for_ten_thousand_problems(self):
        """约束 8（支持一万道题）+ 约束 6：一万道题仍然互不重复。"""
        started = time.perf_counter()
        result = generate(GenerationConfig(count=10000, value_range=100, seed=1))
        elapsed = time.perf_counter() - started

        self.assertEqual(len(result.problems), 10000)
        keys = {problem.canonical_key() for problem in result.problems}
        self.assertEqual(len(keys), 10000)
        self.assertLess(elapsed, 20.0, f"生成一万道题耗时 {elapsed:.2f}s，超出预期")

    def test_no_reverse_pairs_like_23_plus_45(self):
        """反向口令（交换律等价）不能被当成两道不同的题。"""
        result = generate(GenerationConfig(count=300, value_range=12, seed=5))
        keys = [problem.canonical_key() for problem in result.problems]
        self.assertEqual(len(keys), len(set(keys)))

    def test_strict_range_limits_intermediate_results(self):
        result = generate(
            GenerationConfig(count=80, value_range=10, strict_range=True, seed=11)
        )
        self.assertTrue(result.problems)
        for problem in result.problems:
            self.assert_problem_is_legal(problem, 10, strict_range=True)

    def test_all_answers_are_parseable_and_match(self):
        result = generate(GenerationConfig(count=200, value_range=15, seed=3))
        for problem in result.problems:
            # 答案文本必须能被解析回同一个数值（生成与判分共用一套格式）
            from arithmetic.fraction_utils import parse_number

            self.assertEqual(parse_number(problem.answer_text()), problem.value)

    def test_answers_never_negative(self):
        result = generate(GenerationConfig(count=300, value_range=10, seed=9))
        for problem in result.problems:
            self.assertGreaterEqual(problem.value, 0)


class GeneratorEdgeCaseTest(_ConstraintAssertions):
    def test_r_equals_one_generates_what_it_can_then_stops(self):
        """-r 1 时范围内只有 0，能造的题有限；此时必须“尽力而为 + 及时收手”，不能死循环。"""
        started = time.perf_counter()
        result = generate(GenerationConfig(count=10000, value_range=1, seed=0))
        elapsed = time.perf_counter() - started

        self.assertTrue(result.exhausted)
        self.assertGreater(len(result.problems), 0)
        self.assertLess(result.attempts, 20000, "题目空间已穷尽却还在空转")

        texts = {problem.exercise_text(with_equals=False) for problem in result.problems}
        # 一个运算符的题目只能是这三种（除法在只有 0 的范围内不可能成立）
        self.assertTrue({"0 + 0", "0 − 0", "0 × 0"} <= texts)
        for problem in result.problems:
            self.assertEqual(problem.value, 0)
            for node in walk(problem.expr):
                if isinstance(node, Leaf):
                    self.assertEqual(node.number, 0)
        self.assertLess(elapsed, 10.0)

    def test_r_equals_two_finds_enough_problems(self):
        """-r 2 的题目空间不大，但 10 道题仍然凑得出来，且不重复。"""
        result = generate(GenerationConfig(count=10, value_range=2, seed=0))
        self.assertEqual(len(result.problems), 10)
        self.assertFalse(result.exhausted)
        for problem in result.problems:
            self.assert_problem_is_legal(problem, 2)
        keys = [problem.canonical_key() for problem in result.problems]
        self.assertEqual(len(keys), len(set(keys)))

    def test_tiny_range_reports_exhaustion_instead_of_looping(self):
        """r 很小时题目空间会被穷尽，生成器要如实报告而不是无限重试。"""
        result = generate(GenerationConfig(count=100000, value_range=3, seed=0))
        self.assertTrue(result.exhausted)
        self.assertGreater(len(result.problems), 1000)
        for problem in result.problems[:200]:
            self.assert_problem_is_legal(problem, 3)

    def test_no_division_when_range_has_no_fraction(self):
        """范围里没有真分数（r ≤ 2）时，除法不可能得到真分数，所以一道除法题都不该出现。"""
        for value_range in (1, 2):
            with self.subTest(value_range=value_range):
                result = generate(GenerationConfig(count=20, value_range=value_range, seed=1))
                for problem in result.problems:
                    for node in walk(problem.expr):
                        self.assertNotEqual(getattr(node, "op", None), DIV)

    def test_max_ops_is_respected(self):
        for max_ops in (1, 2, 3):
            with self.subTest(max_ops=max_ops):
                result = generate(GenerationConfig(count=60, value_range=20, max_ops=max_ops, seed=2))
                for problem in result.problems:
                    self.assertLessEqual(problem.op_count, max_ops)

    def test_same_seed_gives_same_problems(self):
        first = generate(GenerationConfig(count=30, value_range=10, seed=42))
        second = generate(GenerationConfig(count=30, value_range=10, seed=42))
        self.assertEqual(
            [p.exercise_text() for p in first.problems],
            [p.exercise_text() for p in second.problems],
        )

    def test_invalid_config_rejected(self):
        for kwargs in (
            {"count": 0, "value_range": 10},
            {"count": 10, "value_range": 0},
            {"count": 10, "value_range": 10, "max_ops": 4},
            {"count": 10, "value_range": 10, "min_ops": 0},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                GenerationConfig(**kwargs)

    def test_zero_is_not_used_to_produce_pointless_problems(self):
        """质量护栏：r ≥ 2 时不出现 ``0 + x`` / ``x × 0`` 这种白给的形状。"""
        result = generate(GenerationConfig(count=300, value_range=10, seed=8))
        trivial = 0
        for problem in result.problems:
            for node in walk(problem.expr):
                if isinstance(node, Binary) and node.op in (ADD, MUL):
                    for child in (node.left, node.right):
                        if isinstance(child, Leaf) and child.number == 0:
                            trivial += 1
        self.assertEqual(trivial, 0)

    def test_negative_fraction_leaves_never_appear(self):
        result = generate(GenerationConfig(count=100, value_range=50, seed=6))
        for problem in result.problems:
            for node in walk(problem.expr):
                if isinstance(node, Leaf):
                    self.assertGreaterEqual(node.number, Fraction(0))


if __name__ == "__main__":
    unittest.main()
