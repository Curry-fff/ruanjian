# -*- coding: utf-8 -*-
"""判分模块测试：Grade.txt 的格式与“按数值判定”的宽容度。"""

import unittest
from fractions import Fraction

from arithmetic.grader import GradeError, GradeResult, grade, grade_files, write_grade_file
from tests._helpers import workspace_tempdir


class TestGrade(unittest.TestCase):
    def test_all_correct(self):
        result = grade(["1 + 2 = ", "3/5 + 1/2 = ", "1/6 + 1/8 = "], ["3", "1'1/10", "7/24"])
        self.assertEqual(result.correct, [1, 2, 3])
        self.assertEqual(result.wrong, [])
        self.assertEqual(result.total, 3)

    def test_all_wrong(self):
        result = grade(["1 + 2 = ", "1 − 1 = "], ["4", "2"])
        self.assertEqual(result.correct, [])
        self.assertEqual(result.wrong, [1, 2])

    def test_mixed_matches_required_format(self):
        # 对应作业里的样例：Correct: 5 (1, 3, 5, 7, 9) / Wrong: 5 (2, 4, 6, 8, 10)
        exercises = [f"{index} + 0 = " for index in range(1, 11)]
        answers = [str(index) if index % 2 else "999" for index in range(1, 11)]
        result = grade(exercises, answers)
        self.assertEqual(
            result.format(),
            "Correct: 5 (1, 3, 5, 7, 9)\nWrong: 5 (2, 4, 6, 8, 10)\n",
        )

    def test_zero_counts_are_printed(self):
        result = grade(["1 + 1 = "], ["2"])
        self.assertEqual(result.format(), "Correct: 1 (1)\nWrong: 0 ()\n")

    def test_answer_compared_by_value_not_text(self):
        """2/4 与 1/2、7/6 与 1'1/6、14/12 与 7/6 都应判对。"""
        result = grade(["1 ÷ 2 = ", "7 ÷ 6 = "], ["2/4", "1'1/6"])
        self.assertEqual(result.correct, [1, 2])

    def test_answer_with_numbering_or_equals_is_tolerated(self):
        result = grade(["1 + 2 = "], ["1. =3"])
        self.assertEqual(result.correct, [1])

    def test_unparseable_answer_counts_as_wrong(self):
        result = grade(["1 + 2 = "], ["三"])
        self.assertEqual(result.wrong, [1])

    def test_exercise_lines_may_be_numbered(self):
        result = grade(["1. 1 + 2 = ", "（2）4 ÷ 8 = "], ["3", "1/2"])
        self.assertEqual(result.correct, [1, 2])

    def test_too_few_answers_raises(self):
        with self.assertRaises(GradeError):
            grade(["1 + 1 = ", "1 + 2 = "], ["2"])

    def test_malformed_exercise_raises(self):
        with self.assertRaises(GradeError):
            grade(["1 + + 2 = "], ["3"])

    def test_division_by_zero_in_exercise_raises_grade_error(self):
        with self.assertRaises(GradeError):
            grade(["1 ÷ 0 = "], ["1"])


class TestGradeFiles(unittest.TestCase):
    def test_end_to_end_with_files(self):
        with workspace_tempdir() as base:
            (base / "Exercises.txt").write_text(
                "1/6 + 1/8 = \n3/5 + 1/2 = \n5 − 2 = \n", encoding="utf-8"
            )
            (base / "Answers.txt").write_text("7/24\n1'1/10\n4\n", encoding="utf-8")

            result = grade_files(base / "Exercises.txt", base / "Answers.txt")
            self.assertEqual(result.correct, [1, 2])
            self.assertEqual(result.wrong, [3])

            path = write_grade_file(result, base)
            self.assertEqual(path.name, "Grade.txt")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "Correct: 2 (1, 2)\nWrong: 1 (3)\n",
            )

    def test_gbk_files_are_readable(self):
        """同学在 Windows 上可能存成 GBK，读取时要兼容。"""
        with workspace_tempdir() as base:
            (base / "Exercises.txt").write_bytes("1 ÷ 2 = \n".encode("gbk"))
            (base / "Answers.txt").write_bytes("1/2\n".encode("gbk"))
            result = grade_files(base / "Exercises.txt", base / "Answers.txt")
            self.assertEqual(result.correct, [1])

    def test_missing_file_raises(self):
        with self.assertRaises(GradeError):
            grade_files("不存在的题目文件.txt", "不存在的答案文件.txt")

    def test_blank_lines_are_skipped(self):
        with workspace_tempdir() as base:
            (base / "Exercises.txt").write_text("1 + 2 = \n\n\n4 ÷ 8 = \n", encoding="utf-8")
            (base / "Answers.txt").write_text("3\n1/2\n", encoding="utf-8")
            result = grade_files(base / "Exercises.txt", base / "Answers.txt")
            self.assertEqual(result.correct, [1, 2])


class TestGradeResultFormat(unittest.TestCase):
    def test_default_is_empty(self):
        self.assertEqual(GradeResult().format(), "Correct: 0 ()\nWrong: 0 ()\n")


if __name__ == "__main__":
    unittest.main()
