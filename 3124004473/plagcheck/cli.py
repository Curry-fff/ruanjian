# -*- coding: utf-8 -*-
"""命令行入口。

用法（与作业要求完全一致，三个参数都是绝对路径）::

    python main.py <原文文件> <抄袭版论文文件> <答案文件>

    python main.py C:\\tests\\orig.txt C:\\tests\\orig_add.txt C:\\tests\\ans.txt

退出码约定见 :class:`plagcheck.exceptions.PlagCheckError`。

设计要点：**标准输出默认保持安静**。结果只写进答案文件，标准错误
只在出错或 ``--verbose`` 时输出。这样无论评测方怎样捕获本程序的
输出，都不会被无关内容干扰。
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence

from .engine import PlagiarismChecker
from .exceptions import ArgumentError, PlagCheckError
from .textio import write_answer_file

__all__ = ["build_parser", "main"]

PROGRAM_NAME = "main.py"

#: 兜底退出码：未预期的异常一律以 1 退出，绝不把 traceback 抛到使用者脸上。
EXIT_UNEXPECTED_ERROR = 1

_USAGE_EXAMPLE = r"""示例:
  python main.py C:\tests\orig.txt C:\tests\orig_add.txt C:\tests\ans.txt"""


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="论文查重：比对原文与抄袭版论文，把重复率写入答案文件。",
        epilog=_USAGE_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("original_path", metavar="原文文件", help="论文原文的文件绝对路径")
    parser.add_argument("copy_path", metavar="抄袭版论文文件", help="抄袭版论文的文件绝对路径")
    parser.add_argument("answer_path", metavar="答案文件", help="输出重复率的答案文件绝对路径")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="把分项得分与耗时打印到标准错误输出，便于排查",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """程序主流程。

    参数:
        argv: 命令行参数序列（不含程序名）。``None`` 表示取 ``sys.argv[1:]``。

    返回:
        进程退出码。
    """
    _make_streams_failure_proof()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        _require_non_empty(args.original_path, "原文文件")
        _require_non_empty(args.copy_path, "抄袭版论文文件")
        _require_non_empty(args.answer_path, "答案文件")

        checker = PlagiarismChecker()
        result = checker.compare_files(args.original_path, args.copy_path)
        write_answer_file(args.answer_path, result.duplication)

        if args.verbose:
            print(result.summary(), file=sys.stderr)
    except PlagCheckError as error:
        print(f"{PROGRAM_NAME}: 错误：{error.message}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # pylint: disable=broad-exception-caught
        # 兜底：任何未预期的异常都必须变成"带诊断信息的退出码"，而不是
        # 把 traceback 抛给评测方（作业的扣分项之一是"发生异常退出"）。
        print(
            f"{PROGRAM_NAME}: 未预期的错误：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED_ERROR

    return 0


def _make_streams_failure_proof() -> None:
    """保证向标准输出/标准错误写中文时永远不会抛 ``UnicodeEncodeError``。

    在英文版 Windows 上，控制台编码可能是 cp437，此时 ``print("错误：…")``
    会直接抛异常。异常发生在错误处理路径内部，会把"有诊断信息的退出"
    退化成"崩溃退出"，正好踩中作业的扣分项。把 ``errors`` 放宽为
    ``replace`` 后，最坏情况只是把个别汉字显示成问号。

    测试中把流替换成 ``io.StringIO`` 或 pytest 的捕获对象时会缺
    ``reconfigure`` 或类型不符，因此这里先用 ``isinstance`` 收敛作用
    范围；``ValueError`` 覆盖流已关闭的场景。
    """
    for stream in (sys.stdout, sys.stderr):
        if not isinstance(stream, io.TextIOWrapper):
            continue
        try:
            stream.reconfigure(errors="replace")
        except ValueError:
            continue


def _require_non_empty(value: str, label: str) -> None:
    """拒绝空字符串参数。

    ``argparse`` 只检查参数"有没有给"，不检查"给了什么"。评测脚本若
    用 ``""`` 占位，会一路走到 ``os.path.abspath("")`` 才出错，报错信息
    会指向当前工作目录，非常难排查，因此在这里提前拦截。
    """
    if not value or not value.strip():
        raise ArgumentError(f"{label} 的路径不能为空字符串")
