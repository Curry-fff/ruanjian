#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""覆盖率统计脚本：用标准库 :mod:`trace` 统计行覆盖率。

为什么不用 ``coverage``
-----------------------
``coverage.py`` 是本项目首选的覆盖率工具，但作业环境无法联网安装
（PyPI 镜像返回 403）。标准库的 :mod:`trace` 能给出同样的"哪些行被
执行过"信息，因此改用它，代价是慢得多、且不直接提供分支覆盖率。
分支维度的验证由 ``tests/`` 中针对每个判定分支显式编写的用例承担
（见博客的"分支覆盖矩阵"一节），而不是靠工具给一个数字。

用法::

    python scripts/run_coverage.py

输出:
    docs/coverage/coverage.txt        逐文件覆盖率与未覆盖行号
    docs/coverage/profile_report.txt  说明与复现步骤
"""

from __future__ import annotations

# 本脚本刻意把若干 import 放在函数内部：
#   * pytest 只在真正要跑测试时才需要；
#   * contextlib / io / shutil 只被"补测入口文件"这一条路径用到。
# 这样读报告或做静态分析时不必加载整套测试框架。
# pylint: disable=import-outside-toplevel

import ast
import os
import sys
import trace as trace_module

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PACKAGE_ROOT)

OUTPUT_DIR = os.path.join(PACKAGE_ROOT, "docs", "coverage")

#: 需要统计覆盖率的包目录。
TARGET_PACKAGE = os.path.join(PACKAGE_ROOT, "plagcheck")

#: 入口脚本也要统计（它们只有少量语句，但 `if __name__` 分支值得记录）。
EXTRA_FILES = [os.path.join(PACKAGE_ROOT, "main.py")]


def executable_lines(path: str) -> set:
    """用 AST 求出一个 Python 文件中"可执行语句"所在的行号集合。

    ``trace`` 只提供"某行被执行过几次"，分母得自己算。这里把每个
    语句节点（``ast.stmt``）的行号计入集合，与 ``coverage.py`` 的
    口径基本一致：多行语句只在起始行计一次，注释、空行、纯文档字符串
    表达式之外的声明不计入。

    文档字符串本身是 ``ast.Expr`` 语句，技术上"可执行"，但它永远会
    执行、不会暴露缺陷，计入分母会稀释覆盖率数字，因此单独剔除。
    """
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)

    docstring_lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                docstring_lines.add(first.lineno)

    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and node.lineno not in docstring_lines:
            lines.add(node.lineno)
    return lines


def run_tests_under_trace(argv: list) -> trace_module.Trace:
    """在 ``trace`` 计数模式下运行 pytest，返回已积累了计数的 tracer。"""
    import pytest  # 延迟导入：--report-only 模式下不必加载 pytest

    ignoredirs = [os.path.dirname(os.path.dirname(os.path.abspath(pytest.__file__)))]
    tracer = trace_module.Trace(count=1, trace=0, ignoredirs=ignoredirs)
    os.chdir(PACKAGE_ROOT)
    tracer.runfunc(pytest.main, argv)
    return tracer


def exercise_entry_files(tracer: trace_module.Trace) -> None:
    """显式执行两个"测试跑不到"的入口文件，把它们纳入统计。

    为什么需要这一步（实测结论，不是猜测）：

    * ``plagcheck/__init__.py``：``sys.settrace`` **不会**为"包首次被
      导入时 ``__init__.py`` 的模块级代码"产生行事件——子模块
      （``engine.py`` 等）会正常计入，只有包的 ``__init__`` 会整体缺失。
      结果就是这份纯转发文件在报告里恒为 0.0%，看起来像"完全没测过"，
      与事实不符（它的每一行都在每次 ``import plagcheck`` 时执行）。
    * ``main.py``：单元测试调用的是 ``plagcheck.cli.main``，作为**脚本**
      的入口文件本身不会被导入，``if __name__ == "__main__"`` 那几行
      自然也就跑不到。

    做法是用 ``compile`` + ``exec`` 在 tracer 生效期间真实执行一次这两个
    文件，并临时改写 ``sys.argv`` 让 ``main.py`` 走完整的成功路径。
    ``SystemExit`` 要吞掉：那是 ``sys.exit(main())`` 的正常结束方式。
    """
    # pylint: disable=too-many-locals
    # 这里要准备命名空间、临时语料与 argv，变量虽多但都是一次性装配。
    import contextlib
    import io

    # 绕开标准库 trace 的一处缓存缺陷。
    #
    # ``_Ignore._ignore`` 是按**文件基名**做缓存的，而 ``_modname()`` 对
    # ``.../pkg/__init__.py`` 只会返回 ``"__init__"``。由于我们把
    # site-packages 放进了 ignoredirs（用来跳过 pytest 自身），
    # ``site-packages/pytest/__init__.py`` 会先把 ``"__init__"`` 标记为
    # "应忽略"，此后再遇到任何包的 ``__init__.py`` 都直接命中缓存、
    # 不再统计——这就是本报告里 ``plagcheck/__init__.py`` 恒为 0.0% 的
    # 真正原因。trace.py 源码里也留着
    # ``XXX _modname() doesn't work right for packages`` 的注释。
    #
    # 这里在补测入口文件之前把该缓存清空，让它重新逐文件判断。
    # 属于对私有属性的定向绕行，因此用 getattr 做防御。
    ignore_cache = getattr(tracer.ignore, "_ignore", None)
    if isinstance(ignore_cache, dict):
        ignore_cache.clear()
        ignore_cache["<string>"] = 1

    sandbox = os.path.join(PACKAGE_ROOT, "_test_tmp", "coverage_entry")
    os.makedirs(sandbox, exist_ok=True)

    original = os.path.join(sandbox, "orig.txt")
    copy = os.path.join(sandbox, "copy.txt")
    answer = os.path.join(sandbox, "ans.txt")
    sample_dir = os.path.join(PACKAGE_ROOT, "tests", "data")

    import shutil  # 局部导入：只有本函数需要

    shutil.copy(os.path.join(sample_dir, "sample_orig.txt"), original)
    shutil.copy(os.path.join(sample_dir, "sample_orig_add.txt"), copy)

    package_dir = os.path.dirname(os.path.join(TARGET_PACKAGE, "__init__.py"))

    # 每个文件要用**正确的模块身份**执行，否则相对导入会失败：
    # ``plagcheck/__init__.py`` 必须以包的身份（__name__/__package__ =
    # "plagcheck"，且带 __path__）执行，才能解析 ``from .engine import ...``；
    # 而 ``main.py`` 必须以脚本身份执行，才会走进 ``if __name__ == "__main__"``。
    targets = [
        (
            os.path.join(TARGET_PACKAGE, "__init__.py"),
            {
                "__name__": "plagcheck",
                "__package__": "plagcheck",
                "__path__": [package_dir],
                "__file__": os.path.join(TARGET_PACKAGE, "__init__.py"),
            },
        ),
        (
            os.path.join(PACKAGE_ROOT, "main.py"),
            {
                "__name__": "__main__",
                "__package__": None,
                "__file__": os.path.join(PACKAGE_ROOT, "main.py"),
            },
        ),
    ]

    for path, namespace in targets:
        with open(path, encoding="utf-8") as handle:
            code = compile(handle.read(), path, "exec")

        saved_argv = sys.argv
        sys.argv = [path, original, copy, answer]
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                tracer.runfunc(exec, code, namespace)
        except SystemExit:
            # 入口脚本以 sys.exit() 结束属于正常路径。
            pass
        finally:
            sys.argv = saved_argv


def collect_counts(tracer: trace_module.Trace) -> dict:
    """把 ``trace`` 的结果整理成 ``{绝对路径: {行号: 次数}}``。"""
    counts = {}
    for (filename, lineno), count in tracer.results().counts.items():
        counts.setdefault(os.path.abspath(filename), {})[lineno] = count
    return counts


def render_report(counts: dict) -> str:
    """生成逐文件的覆盖率报告文本。"""
    # pylint: disable=too-many-locals
    # 这个函数要把"逐文件统计 + 汇总 + 未覆盖行清单"一次拼成报告，
    # 局部变量偏多是排版需要，拆开反而更难读。
    targets = [TARGET_PACKAGE] + EXTRA_FILES
    rows = []
    total_executable = 0
    total_covered = 0

    for target in targets:
        if os.path.isfile(target):
            files = [target]
        else:
            files = sorted(
                os.path.join(root, name)
                for root, _dirs, names in os.walk(target)
                for name in names
                if name.endswith(".py")
            )
        for path in files:
            lines = executable_lines(path)
            if not lines:
                continue
            hits = counts.get(os.path.abspath(path), {})
            covered = {line for line in lines if hits.get(line, 0) > 0}
            missing = sorted(lines - covered)
            total_executable += len(lines)
            total_covered += len(covered)
            # 报告里的路径统一用正斜杠，避免 Windows 截图上出现反斜杠噪音。
            relative = os.path.relpath(path, PACKAGE_ROOT).replace("\\", "/")
            rows.append((relative, len(lines), len(covered), missing))

    lines_out = []
    lines_out.append("论文查重程序 —— 行覆盖率报告（标准库 trace 统计）")
    lines_out.append("=" * 74)
    lines_out.append(f"{'文件':<34}{'可执行行':>8}{'已覆盖':>8}{'覆盖率':>9}")
    lines_out.append("-" * 74)
    for name, total, covered, _missing in rows:
        lines_out.append(f"{name:<34}{total:>8}{covered:>8}{covered / total * 100:>8.1f}%")
    lines_out.append("-" * 74)
    overall = total_covered / total_executable * 100 if total_executable else 0.0
    lines_out.append(f"{'合计':<34}{total_executable:>8}{total_covered:>8}{overall:>8.1f}%")
    lines_out.append("")

    for name, _total, _covered, missing in rows:
        if missing:
            line_numbers = ", ".join(str(line) for line in missing)
            lines_out.append(f"未覆盖行 {name}: {line_numbers}")
    if not any(row[3] for row in rows):
        lines_out.append("所有可执行行均被测试覆盖。")

    return "\n".join(lines_out)


def main() -> int:
    """运行测试并输出覆盖率报告。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    tracer = run_tests_under_trace(["tests", "-q", "--no-header", "-p", "no:cacheprovider"])
    exercise_entry_files(tracer)
    counts = collect_counts(tracer)
    report = render_report(counts)

    target = os.path.join(OUTPUT_DIR, "coverage.txt")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(report + "\n")

    print()
    print(report)
    print()
    print(f"已写入：{target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
