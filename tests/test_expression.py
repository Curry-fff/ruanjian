# -*- coding: utf-8 -*-
"""表达式树：求值、括号打印、以及作业里那几条查重规则。"""

import unittest
from fractions import Fraction

from arithmetic.expression import ADD, Binary, Leaf, PRECEDENCE
from arithmetic.parser import parse_expression


class TestEvaluate(unittest.TestCase):
    def test_exact_fraction_arithmetic(self):
        # 作业说明里的例子：1/6 + 1/8 = 7/24
        self.assertEqual(parse_expression("1/6 + 1/8").evaluate(), Fraction(7, 24))

    def test_mixed_number_and_parentheses(self):
        self.assertEqual(parse_expression("2'3/8 + 1/8").evaluate(), Fraction(5, 2))
        self.assertEqual(parse_expression("(1 + 2) × 3").evaluate(), Fraction(9))
        self.assertEqual(parse_expression("2 + 3 × 4").evaluate(), Fraction(14))

    def test_division_is_exact(self):
        self.assertEqual(parse_expression("1 ÷ 3").evaluate(), Fraction(1, 3))
        self.assertEqual(parse_expression("1/2 ÷ 1/3").evaluate(), Fraction(3, 2))


class TestPrinting(unittest.TestCase):
    """打印规则：只在语法需要的地方加括号。"""

    CASES = {
        "1 + 2": "1 + 2",
        "1 + 2 × 3": "1 + 2 × 3",
        "(1 + 2) × 3": "(1 + 2) × 3",
        "(1 + 2) + 3": "1 + 2 + 3",  # 左结合，无需括号
        "1 + (2 + 3)": "1 + (2 + 3)",  # 右孩子同优先级，必须保留
        "1 − (2 − 3)": "1 − (2 − 3)",
        "1 − 2 − 3": "1 − 2 − 3",
        "(1 − 2) − 3": "1 − 2 − 3",
        "6 ÷ (2 ÷ 3)": "6 ÷ (2 ÷ 3)",
        "6 ÷ 2 ÷ 3": "6 ÷ 2 ÷ 3",
        "(6 ÷ 2) × 3": "6 ÷ 2 × 3",
        "6 × (2 ÷ 3)": "6 × (2 ÷ 3)",
        "1 + 2 - 3": "1 + 2 − 3",  # 减号统一打印成 −
        "1 * 2 / 3": "1 × 2 ÷ 3",
    }

    def test_minimal_parentheses(self):
        for source, expected in self.CASES.items():
            with self.subTest(source=source):
                self.assertEqual(parse_expression(source).to_text(), expected)

    def test_print_then_parse_is_stable(self):
        """打印出来的式子再解析回来，值与规范键都不变（说明括号不多不少）。"""
        for source in self.CASES:
            with self.subTest(source=source):
                expression = parse_expression(source)
                again = parse_expression(expression.to_text())
                self.assertEqual(again.evaluate(), expression.evaluate())
                self.assertEqual(again.canonical_key(), expression.canonical_key())


class TestCanonicalKey(unittest.TestCase):
    """作业说明里点到名的四组例子。"""

    def test_commutative_duplicates(self):
        self.assertEqual(
            parse_expression("23 + 45").canonical_key(),
            parse_expression("45 + 23").canonical_key(),
        )
        self.assertEqual(
            parse_expression("6 × 8").canonical_key(),
            parse_expression("8 × 6").canonical_key(),
        )

    def test_associative_duplicate(self):
        """3+(2+1) 与 1+2+3 重复（都能靠交换左右孩子变成同一棵树）。"""
        self.assertEqual(
            parse_expression("3 + (2 + 1)").canonical_key(),
            parse_expression("1 + 2 + 3").canonical_key(),
        )
        self.assertEqual(
            parse_expression("(1 + 2) + 3").canonical_key(),
            parse_expression("3 + (2 + 1)").canonical_key(),
        )

    def test_not_duplicate(self):
        """1+2+3 与 3+2+1 不重复：光靠交换孩子无法把 (1+2)+3 变成 (3+2)+1。"""
        self.assertNotEqual(
            parse_expression("1 + 2 + 3").canonical_key(),
            parse_expression("3 + 2 + 1").canonical_key(),
        )

    def test_non_commutative_operators(self):
        self.assertNotEqual(
            parse_expression("2 − 1").canonical_key(),
            parse_expression("1 − 2").canonical_key(),
        )
        self.assertNotEqual(
            parse_expression("6 ÷ 3").canonical_key(),
            parse_expression("3 ÷ 6").canonical_key(),
        )

    def test_equivalent_but_differently_written_numbers(self):
        self.assertEqual(
            parse_expression("1/2 + 1/3").canonical_key(),
            parse_expression("2/4 + 2/6").canonical_key(),
        )


class TestNodes(unittest.TestCase):
    def test_op_count(self):
        self.assertEqual(parse_expression("3").op_count, 0)
        self.assertEqual(parse_expression("3 + 1 ÷ 2").op_count, 2)
        self.assertEqual(parse_expression("(1 + 2) × (3 − 4 ÷ 5)").op_count, 4)

    def test_leaf_and_binary_basics(self):
        leaf = Leaf(Fraction(3, 4))
        self.assertTrue(leaf.is_leaf)
        self.assertEqual(leaf.to_text(), "3/4")
        node = Binary(ADD, leaf, Leaf(Fraction(1)))
        self.assertEqual(node.evaluate(), Fraction(7, 4))
        self.assertFalse(node.is_leaf)
        self.assertIn(ADD, PRECEDENCE)

    def test_unknown_operator_rejected(self):
        with self.assertRaises(ValueError):
            Binary("%", Leaf(Fraction(1)), Leaf(Fraction(1)))


if __name__ == "__main__":
    unittest.main()
