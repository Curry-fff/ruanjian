# -*- coding: utf-8 -*-
"""答案判定与 ``Grade.txt`` 生成。

判定方式：**以题目文件为准**，把每道题解析成表达式树后用 ``Fraction`` 精确求值，
再和学生交上来的答案比大小。这样做的好处是：

* 不必假设答案文件一定正确（老师给的题也能批改）；
* 比较的是**数值**而不是字符串，``7/6``、``1'1/6``、``14/12`` 都算对；
* 答案文件里写不出规范格式时不会被判成“程序崩溃”，只算这道题错。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Sequence

from .fraction_utils import NumberFormatError, parse_number
from .parser import ParseError, parse_exercise_line, strip_numbering

__all__ = [
    "EXERCISE_FILENAME",
    "ANSWER_FILENAME",
    "GRADE_FILENAME",
    "GradeError",
    "GradeResult",
    "read_lines",
    "grade",
    "grade_files",
    "write_grade_file",
]

EXERCISE_FILENAME = "Exercises.txt"
ANSWER_FILENAME = "Answers.txt"
GRADE_FILENAME = "Grade.txt"


class GradeError(RuntimeError):
    """题目文件 / 答案文件无法批改（文件缺失、行数不足、题目写错等）。"""


@dataclass
class GradeResult:
    """批改结果。"""

    correct: List[int] = field(default_factory=list)
    wrong: List[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.correct) + len(self.wrong)

    def format(self) -> str:
        """按作业要求的格式输出统计结果。"""
        return (
            f"Correct: {len(self.correct)} ({_join(self.correct)})\n"
            f"Wrong: {len(self.wrong)} ({_join(self.wrong)})\n"
        )


def _join(values: Sequence[int]) -> str:
    return ", ".join(str(value) for value in values)


def read_lines(path) -> List[str]:
    """读入文本文件的非空行（自动兼容 UTF-8 与 GBK）。"""
    file = Path(path)
    if not file.is_file():
        raise GradeError(f"找不到文件：{file}")
    data = file.read_bytes()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - 两种编码都失败的情况极少见
        raise GradeError(f"无法识别文件编码（请另存为 UTF-8）：{file}")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _clean_answer(text: str) -> Optional[Fraction]:
    """把一个答案行变成分数；格式不对返回 ``None``（记为该题错误）。"""
    cleaned = strip_numbering(text).strip()
    cleaned = cleaned.strip("=").strip()
    try:
        return parse_number(cleaned)
    except NumberFormatError:
        return None


def grade(exercises: Sequence[str], answers: Sequence[str]) -> GradeResult:
    """批改：``exercises`` 与 ``answers`` 是已去掉空行的行列表。"""
    if len(answers) < len(exercises):
        raise GradeError(
            f"答案文件只有 {len(answers)} 行，题目文件有 {len(exercises)} 行，两者对不上"
        )

    result = GradeResult()
    for index, line in enumerate(exercises, start=1):
        try:
            expected = parse_exercise_line(line).evaluate()
        except ParseError as error:
            raise GradeError(f"第 {index} 题无法解析：{error}") from error
        except ZeroDivisionError as error:
            raise GradeError(f"第 {index} 题出现了除以 0：{line!r}") from error
        if _clean_answer(answers[index - 1]) == expected:
            result.correct.append(index)
        else:
            result.wrong.append(index)
    return result


def grade_files(exercise_path, answer_path) -> GradeResult:
    """读文件并批改。"""
    return grade(read_lines(exercise_path), read_lines(answer_path))


def write_grade_file(result: GradeResult, out_dir=".") -> Path:
    """把统计结果写入 ``Grade.txt``，返回文件路径。"""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / GRADE_FILENAME
    path.write_text(result.format(), encoding="utf-8", newline="\n")
    return path
