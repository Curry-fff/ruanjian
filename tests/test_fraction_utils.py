# -*- coding: utf-8 -*-
"""数值格式的解析与格式化测试。"""

import unittest
from fractions import Fraction

from arithmetic.fraction_utils import NumberFormatError, format_number, parse_number


class TestFormatNumber(unittest.TestCase):
    def test_natural_numbers(self):
        self.assertEqual(format_number(Fraction(0)), "0")
        self.assertEqual(format_number(Fraction(7)), "7")
        self.assertEqual(format_number(Fraction(10000)), "10000")

    def test_proper_fraction(self):
        self.assertEqual(format_number(Fraction(3, 5)), "3/5")
        self.assertEqual(format_number(Fraction(7, 24)), "7/24")

    def test_mixed_number(self):
        self.assertEqual(format_number(Fraction(19, 8)), "2'3/8")
        self.assertEqual(format_number(Fraction(3, 2)), "1'1/2")

    def test_negative(self):
        self.assertEqual(format_number(Fraction(-3, 5)), "-3/5")


class TestParseNumber(unittest.TestCase):
    def test_round_trip(self):
        for fraction in (Fraction(0), Fraction(9), Fraction(3, 5), Fraction(7, 24), Fraction(19, 8)):
            self.assertEqual(parse_number(format_number(fraction)), fraction)

    def test_tolerates_spaces_and_apostrophes(self):
        self.assertEqual(parse_number(" 2 ’ 3 / 8 "), Fraction(19, 8))
        self.assertEqual(parse_number("2`3/8"), Fraction(19, 8))

    def test_accepts_unreduced_and_improper_fractions(self):
        self.assertEqual(parse_number("2/4"), Fraction(1, 2))
        self.assertEqual(parse_number("7/6"), Fraction(7, 6))

    def test_rejects_bad_input(self):
        for text in ("", "abc", "3/0", "2'5/3", "1/", "1..2"):
            with self.subTest(text=text), self.assertRaises(NumberFormatError):
                parse_number(text)


if __name__ == "__main__":
    unittest.main()
