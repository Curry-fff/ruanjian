# -*- coding: utf-8 -*-
"""命令行入口：参数解析、文件读写、给用户看的提示。

命令行契约（与作业要求一一对应）::

    Myapp.py -n 10 -r 10                      生成 10 道 10 以内的题目
    Myapp.py -n 10000 -r 100                  生成一万道题目
    Myapp.py -e Exercises.txt -a Answers.txt  批改并写出 Grade.txt

约定：

* 生成的文件（``Exercises.txt`` / ``Answers.txt`` / ``Grade.txt``）默认写到
  **执行程序的当前目录**，可用 ``--out-dir`` 改变；
* ``-r`` 必须给定，缺失时报错并打印完整帮助信息（作业要求）；
* 参数错误统一以退出码 2 结束，运行期错误（如文件读不了）以退出码 1 结束。
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, Sequence

from .expression import ASCII_SYMBOLS, SYMBOLS
from .generator import GenerationConfig, generate
from .grader import (
    ANSWER_FILENAME,
    EXERCISE_FILENAME,
    GRADE_FILENAME,
    GradeError,
    grade_files,
    write_grade_file,
)

__all__ = ["build_parser", "main"]

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


class _HelpfulParser(argparse.ArgumentParser):
    """参数出错时先给出错误原因，再把完整帮助信息打出来。"""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE_ERROR, f"\n参数错误：{message}\n\n{self.format_help()}")


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} 不是整数") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} 必须是大于 0 的整数")
    return value


def _operator_count(text: str) -> int:
    value = _positive_int(text)
    if value > 3:
        raise argparse.ArgumentTypeError("运算符个数不能超过 3 个（作业要求）")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = _HelpfulParser(
        prog="Myapp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="小学四则运算题目生成 / 批改程序（结对项目）",
        epilog=textwrap.dedent(
            """\
            示例：
              python Myapp.py -n 10 -r 10                        生成 10 道 10 以内的题目
              python Myapp.py -n 10000 -r 100 --seed 2024        生成一万道题目（可复现）
              python Myapp.py -e Exercises.txt -a Answers.txt    批改两个文件并写出 Grade.txt

            说明：
              * -r 控制的是题目中出现的数值范围，取值范围是 [1, r)，例如 -r 10 表示 10 以内；
              * 生成结果固定写入当前目录的 Exercises.txt 与 Answers.txt；
              * 批改结果固定写入当前目录的 Grade.txt。
            """
        ),
    )
    parser.add_argument("-n", "--count", type=_positive_int, metavar="N", help="生成题目的个数")
    parser.add_argument(
        "-r",
        "--range",
        dest="value_range",
        type=_positive_int,
        metavar="R",
        help="题目中数值（自然数、真分数、真分数分母）的范围 [1, R)；生成模式下必须给定",
    )
    parser.add_argument("-e", "--exercise", metavar="FILE", help="待批改的题目文件")
    parser.add_argument("-a", "--answer", metavar="FILE", help="待批改的答案文件")
    parser.add_argument(
        "--max-ops",
        type=_operator_count,
        default=3,
        metavar="K",
        help="每道题最多包含的运算符个数，默认 3（作业要求不超过 3）",
    )
    parser.add_argument(
        "--strict-range",
        action="store_true",
        help="更严的数值范围：要求每一步中间结果也小于 R",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="用 + - * / 输出运算符（默认为作业说明里的 + - x 除号写法）",
    )
    parser.add_argument("--seed", type=int, default=None, metavar="S", help="随机种子，便于复现同一批题目")
    parser.add_argument("--out-dir", default=".", metavar="DIR", help="输出目录，默认当前目录")
    return parser


def _write_lines(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")


def _run_generate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.count is None:
        parser.error("缺少 -n 参数：请用 -n <题目个数> 指定要生成多少道题")
    if args.value_range is None:
        parser.error("缺少 -r 参数：-r 控制题目中数值的范围（如 -r 10 表示 10 以内），必须给定")

    config = GenerationConfig(
        count=args.count,
        value_range=args.value_range,
        max_ops=args.max_ops,
        strict_range=args.strict_range,
        seed=args.seed,
    )
    result = generate(config)

    symbols = ASCII_SYMBOLS if args.ascii else SYMBOLS
    out_dir = Path(args.out_dir)
    exercise_path = out_dir / EXERCISE_FILENAME
    answer_path = out_dir / ANSWER_FILENAME
    _write_lines(exercise_path, [problem.exercise_text(symbols) for problem in result.problems])
    _write_lines(answer_path, [problem.answer_text() for problem in result.problems])

    print(f"已生成 {len(result.problems)} 道题目（数值范围 {args.value_range} 以内，最多 {args.max_ops} 个运算符）")
    print(f"题目文件：{exercise_path}")
    print(f"答案文件：{answer_path}")

    if result.exhausted:
        print(
            f"注意：在 -r {args.value_range} 的范围内，去重后最多只能造出 {len(result.problems)} 道题"
            f"（已尝试 {result.attempts} 次），因此实际生成 {len(result.problems)} 道。"
            f"如需更多题目，请把 -r 调大。",
            file=sys.stderr,
        )
    return EXIT_OK


def _run_grade(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if not args.exercise or not args.answer:
        parser.error(
            "批改模式需要同时给出题目文件和答案文件，例如：Myapp.exe -e Exercises.txt -a Answers.txt"
        )
    if args.count is not None or args.value_range is not None:
        print("提示：批改模式下 -n / -r 会被忽略。", file=sys.stderr)

    try:
        result = grade_files(args.exercise, args.answer)
        grade_path = write_grade_file(result, args.out_dir)
    except GradeError as error:
        print(f"错误：{error}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    print(result.format(), end="")
    print(f"统计结果已写入：{grade_path}")
    return EXIT_OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    # 中文 Windows 的管道默认是 GBK，统一按 UTF-8 输出并兜底，避免打印不出来就崩掉
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - 极老的解释器
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.exercise or args.answer:
        return _run_grade(parser, args)
    return _run_generate(parser, args)
