# -*- coding: utf-8 -*-
"""题目文本解析的容错能力（批改别人交上来的文件时很关键）。"""

import unittest
from fractions import Fraction

from arithmetic.parser import ParseError, parse_exercise_line, parse_expression, strip_numbering


class TestStripNumbering(unittest.TestCase):
    def test_common_prefixes(self):
        cases = {
            "1. 1 + 2 =": "1 + 2 =",
            "12、1 + 2 =": "1 + 2 =",
            "(3) 1 + 2 =": "1 + 2 =",
            "（4）1 + 2 =": "1 + 2 =",
            "5）1 + 2 =": "1 + 2 =",
            "6: 1 + 2 =": "1 + 2 =",
            "1 + 2 =": "1 + 2 =",  # 没有题号时原样返回
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(strip_numbering(source), expected)


class TestParseExerciseLine(unittest.TestCase):
    def test_trailing_equals_is_ignored(self):
        self.assertEqual(parse_exercise_line("1 + 2 = ").evaluate(), Fraction(3))
        self.assertEqual(parse_exercise_line("1 + 2").evaluate(), Fraction(3))
        self.assertEqual(parse_exercise_line("1 + 2 = = =").evaluate(), Fraction(3))

    def test_numbered_lines(self):
        self.assertEqual(parse_exercise_line("7. 3/5 + 1/2 =").evaluate(), Fraction(11, 10))
        self.assertEqual(parse_exercise_line("（7）3/5 + 1/2 =").evaluate(), Fraction(11, 10))

    def test_operator_spellings_are_equivalent(self):
        expected = Fraction(1, 6)
        for source in ("1/2 - 1/3", "1/2 − 1/3", "1/2 – 1/3"):
            with self.subTest(source=source):
                self.assertEqual(parse_expression(source).evaluate(), expected)

    def test_full_width_parentheses_and_times_signs(self):
        self.assertEqual(parse_expression("（1 + 2）× 3").evaluate(), Fraction(9))
        self.assertEqual(parse_expression("(1 + 2) * 3").evaluate(), Fraction(9))
        self.assertEqual(parse_expression("(1 + 2) x 3").evaluate(), Fraction(9))

    def test_mixed_number_token(self):
        self.assertEqual(parse_expression("2'3/8 ÷ 1/4").evaluate(), Fraction(19, 2))

    def test_bad_lines_raise(self):
        for source in ("", "1 +", "(1 + 2", "1 + 2)", "1 @ 2", "1 + 2 3"):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_exercise_line(source)

    def test_division_by_zero_parses_but_fails_on_evaluate(self):
        """解析只看结构，除以 0 要到求值时才暴露——判分模块必须接住它。"""
        with self.assertRaises(ZeroDivisionError):
            parse_expression("1 ÷ 0").evaluate()


if __name__ == "__main__":
    unittest.main()
