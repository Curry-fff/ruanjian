# -*- coding: utf-8 -*-
"""命令行端到端测试：真的把 ``Myapp.py`` 当程序跑起来，检查退出码与产出文件。

这些用例模拟“老师按作业要求敲命令”的场景，因此用 ``subprocess`` 起独立进程，
只通过退出码、stdout/stderr 和生成的文件来判断行为。
"""

import subprocess
import sys
import time
import unittest
from fractions import Fraction
from pathlib import Path

from arithmetic.fraction_utils import parse_number
from arithmetic.parser import parse_exercise_line
from tests._helpers import workspace_tempdir

ROOT = Path(__file__).resolve().parents[1]
MYAPP = ROOT / "Myapp.py"


def run_app(*args, cwd):
    """在指定目录下运行 Myapp.py，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(MYAPP), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def read_lines(path: Path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class GenerateModeTest(unittest.TestCase):
    def test_generates_files_in_current_directory(self):
        with workspace_tempdir() as base:
            completed = run_app("-n", "10", "-r", "10", "--seed", "1", cwd=base)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            exercises = read_lines(base / "Exercises.txt")
            answers = read_lines(base / "Answers.txt")

            self.assertEqual(len(exercises), 10)
            self.assertEqual(len(answers), 10)
            for line in exercises:
                self.assertTrue(line.endswith("="), line)
                parse_exercise_line(line)  # 每一行都必须能解析
            for answer in answers:
                parse_number(answer)

    def test_answers_match_the_exercises(self):
        """程序自己生成的答案，交给自己的判分模块必须全对（闭环自检）。"""
        with workspace_tempdir() as base:
            run_app("-n", "50", "-r", "12", "--seed", "5", cwd=base)
            completed = run_app("-e", "Exercises.txt", "-a", "Answers.txt", cwd=base)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            grade_text = (base / "Grade.txt").read_text(encoding="utf-8")
            self.assertEqual(grade_text.splitlines()[0], "Correct: 50 (" + ", ".join(map(str, range(1, 51))) + ")")
            self.assertEqual(grade_text.splitlines()[1], "Wrong: 0 ()")

    def test_ten_thousand_problems_via_cli(self):
        """作业约束 8：一次生成一万道题。"""
        with workspace_tempdir() as base:
            started = time.perf_counter()
            completed = run_app("-n", "10000", "-r", "100", "--seed", "2024", cwd=base)
            elapsed = time.perf_counter() - started

            self.assertEqual(completed.returncode, 0, completed.stderr)
            exercises = read_lines(base / "Exercises.txt")
            answers = read_lines(base / "Answers.txt")
            self.assertEqual(len(exercises), 10000)
            self.assertEqual(len(answers), 10000)
            self.assertEqual(len(set(exercises)), 10000)
            self.assertLess(elapsed, 60.0, f"命令行生成一万道题用了 {elapsed:.1f}s")

    def test_ascii_mode(self):
        with workspace_tempdir() as base:
            run_app("-n", "20", "-r", "10", "--ascii", "--seed", "3", cwd=base)
            text = (base / "Exercises.txt").read_text(encoding="utf-8")
            self.assertNotIn("×", text)
            self.assertNotIn("÷", text)
            self.assertNotIn("−", text)

    def test_out_dir_option(self):
        with workspace_tempdir() as base:
            nested = base / "out"
            completed = run_app("-n", "5", "-r", "8", "--out-dir", str(nested), cwd=base)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((nested / "Exercises.txt").is_file())
            self.assertTrue((nested / "Answers.txt").is_file())

    def test_seed_makes_output_reproducible(self):
        with workspace_tempdir() as base:
            run_app("-n", "10", "-r", "20", "--seed", "99", cwd=base)
            first = (base / "Exercises.txt").read_text(encoding="utf-8")
            run_app("-n", "10", "-r", "20", "--seed", "99", cwd=base)
            second = (base / "Exercises.txt").read_text(encoding="utf-8")
            self.assertEqual(first, second)


class UsageErrorTest(unittest.TestCase):
    """参数不合法时要“报错 + 给出帮助信息”（作业要求）。"""

    def _assert_usage_error(self, *args):
        with workspace_tempdir() as directory:
            completed = run_app(*args, cwd=directory)
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            self.assertIn("参数错误", completed.stderr)
            self.assertIn("usage", completed.stderr)
            self.assertIn("-r", completed.stderr)
            return completed

    def test_missing_r(self):
        completed = self._assert_usage_error("-n", "10")
        self.assertIn("缺少 -r 参数", completed.stderr)

    def test_missing_n(self):
        self._assert_usage_error()

    def test_r_must_be_positive(self):
        self._assert_usage_error("-n", "10", "-r", "0")

    def test_n_must_be_positive(self):
        self._assert_usage_error("-n", "0", "-r", "10")

    def test_max_ops_cannot_exceed_three(self):
        completed = self._assert_usage_error("-n", "10", "-r", "10", "--max-ops", "4")
        self.assertIn("运算符个数不能超过 3", completed.stderr)

    def test_exercise_without_answer(self):
        with workspace_tempdir() as directory:
            completed = run_app("-e", "Exercises.txt", cwd=directory)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("同时给出题目文件和答案文件", completed.stderr)

    def test_help_is_available(self):
        with workspace_tempdir() as directory:
            completed = run_app("-h", cwd=directory)
            self.assertEqual(completed.returncode, 0)
            for flag in ("-n", "-r", "-e", "-a"):
                self.assertIn(flag, completed.stdout)


class GradeModeTest(unittest.TestCase):
    def test_grades_wrong_answers_with_indexes(self):
        with workspace_tempdir() as base:
            run_app("-n", "10", "-r", "10", "--seed", "7", cwd=base)

            answers = read_lines(base / "Answers.txt")
            answers[2] = "999999"  # 第 3 题写错（数值上不可能对：r=10 时结果远小于它）
            answers[7] = "不是数"   # 第 8 题写成非法格式，同样记错
            (base / "Answers.txt").write_text("\n".join(answers) + "\n", encoding="utf-8")

            completed = run_app("-e", "Exercises.txt", "-a", "Answers.txt", cwd=base)
            self.assertEqual(completed.returncode, 0, completed.stderr)

            grade_text = (base / "Grade.txt").read_text(encoding="utf-8")
            self.assertIn("Correct: 8 (1, 2, 4, 5, 6, 7, 9, 10)", grade_text)
            self.assertIn("Wrong: 2 (3, 8)", grade_text)

    def test_missing_input_file_reports_error(self):
        with workspace_tempdir() as base:
            (base / "Answers.txt").write_text("3\n", encoding="utf-8")
            completed = run_app("-e", "Exercises.txt", "-a", "Answers.txt", cwd=base)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("找不到文件", completed.stderr)

    def test_grades_handwritten_fraction_answers(self):
        """手写的答案只要数值对就算对：带分数、未约分、假分数都接受。"""
        with workspace_tempdir() as base:
            (base / "Exercises.txt").write_text(
                "1/6 + 1/8 = \n1 ÷ 2 = \n3 ÷ 2 = \n", encoding="utf-8"
            )
            (base / "Answers.txt").write_text("7/24\n2/4\n1'1/2\n", encoding="utf-8")
            completed = run_app("-e", "Exercises.txt", "-a", "Answers.txt", cwd=base)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                (base / "Grade.txt").read_text(encoding="utf-8"),
                "Correct: 3 (1, 2, 3)\nWrong: 0 ()\n",
            )

    def test_self_check_on_generated_fraction_problem(self):
        """闭环抽查：程序生成的题目里必然有分数题，自己批自己要对。"""
        with workspace_tempdir() as base:
            run_app("-n", "200", "-r", "30", "--seed", "123", cwd=base)
            text = (base / "Exercises.txt").read_text(encoding="utf-8")
            self.assertRegex(text, r"\d+/\d+")

            answers = [
                parse_exercise_line(line).evaluate()
                for line in read_lines(base / "Exercises.txt")
            ]
            self.assertTrue(all(isinstance(answer, Fraction) for answer in answers))


if __name__ == "__main__":
    unittest.main()
