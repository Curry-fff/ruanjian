#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""性能分析脚本：用 cProfile 找出查重流程的热点函数。

对应作业要求「使用性能分析工具找出代码中的性能瓶颈并进行改进」。
Python 生态里对应的工具是标准库自带的 :mod:`cProfile`（等价于 VS 的
性能分析器 / JProfiler），它按函数统计**调用次数、独占时间、累计时间**，
``tottime`` 就是"消耗最大的函数"。

用法::

    # 在真实语料上分析
    python scripts/profile_run.py

    # 指定语料规模（默认同时跑真实语料与放大 10 倍的合成语料）
    python scripts/profile_run.py --repeat 20

    # 仅打印报告，不画图
    python scripts/profile_run.py --no-chart

输出:
    docs/profile/compare_files.prof   cProfile 原始数据（可用 pstats 复看）
    docs/profile/profile_report.txt   文本报告（tottime / cumtime 两个榜单）
    docs/profile/profile_chart.png    性能分析图，可直接放进博客
"""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import pstats
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PACKAGE_ROOT)

from plagcheck import PlagiarismChecker  # noqa: E402
from plagcheck.textio import read_text_file  # noqa: E402

DATA_DIR = os.path.join(PACKAGE_ROOT, "tests", "data")
OUTPUT_DIR = os.path.join(PACKAGE_ROOT, "docs", "profile")

#: 性能分析图里展示的函数数量。
TOP_N = 12

#: 匹配 Windows 绝对路径，并单独捕获尾部的 ``:行号(函数名)``。
_ABSOLUTE_PATH = re.compile(r"([A-Za-z]:\\[^\s:]+)(:\d+\([^)]*\))?")


def load_corpus(repeat: int):
    """载入真实语料，并按 ``repeat`` 倍放大以获得稳定的测量规模。

    放大而不是造随机文本，是为了让热点分布与真实负载一致：真实的
    ``orig_add.txt`` 是字符级插入版，放大后 n-gram 分布仍然贴近真实。
    """
    original = read_text_file(os.path.join(DATA_DIR, "orig.txt"))
    copy = read_text_file(os.path.join(DATA_DIR, "orig_add.txt"))
    return original * repeat, copy * repeat


def run_workload(checker, original, copy, rounds: int = 3) -> float:
    """重复跑若干轮，返回平均单轮耗时（秒）。"""
    best = float("inf")
    for _ in range(rounds):
        started = time.perf_counter()
        checker.compare_texts(original, copy)
        best = min(best, time.perf_counter() - started)
    return best


def collect_stats(original, copy, repeat: int):
    """用 cProfile 采集一次完整比对的分析数据。"""
    profiler = cProfile.Profile()
    checker = PlagiarismChecker()
    profiler.enable()
    checker.compare_texts(original, copy)
    profiler.disable()
    return profiler


def _shorten_paths(text: str) -> str:
    """把报告里的绝对路径改写成不含本机目录结构的短路径。

    为什么必须做这一步：``cProfile`` / ``pstats`` 打印的是代码对象的
    ``co_filename``，也就是**本机的绝对路径**。如果原样写进仓库，就会把
    开发者的目录结构（用户名、盘符、项目所在文件夹名）一起提交上去——
    既泄露本地环境，也毫无信息价值（读者只关心是哪个文件的哪个函数）。

    规则：
        * 项目内的文件 → 相对 ``PACKAGE_ROOT`` 的路径，如
          ``plagcheck/similarity.py``；
        * 其它文件（标准库、第三方库）→ 只保留文件名，如
          ``collections/__init__.py``。

    末尾的 ``:行号(函数名)`` 会被完整保留。
    """
    def _replace(match):
        path, suffix = match.group(1), match.group(2) or ""
        if path.startswith(PACKAGE_ROOT):
            shown = os.path.relpath(path, PACKAGE_ROOT).replace("\\", "/")
        else:
            shown = os.path.basename(path)
        return shown + suffix

    return _ABSOLUTE_PATH.sub(_replace, text)


def format_report(profiler, limit: int = TOP_N) -> str:
    """生成"独占时间 / 累计时间"两份榜单（路径已脱敏）。"""
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.sort_stats("tottime").print_stats(limit)
    stats.sort_stats("cumulative").print_stats(limit)
    return _shorten_paths(buffer.getvalue())


def render_chart(profiler, target: str, limit: int = TOP_N) -> bool:
    """把 tottime 榜单画成横向柱状图，供博客截图使用。

    仅使用项目内"函数名"的条目，过滤掉 ``{built-in method ...}`` 之类
    噪音；matplotlib 不可用时安静跳过（它是分析工具，不是运行时依赖）。
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("未安装 matplotlib，跳过绘图（不影响分析结果）")
        return False

    # matplotlib 自带的 DejaVu 字体没有汉字字形，不配置就会把标题画成一串
    # 方框并刷屏 UserWarning。这里按可用性挑选一款系统自带的 CJK 字体。
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "SimSun", "DejaVu Sans"):
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False

    stats = pstats.Stats(profiler)
    rows = []
    for (filename, lineno, funcname), (_cc, _nc, tottime, _cumtime, _callers) in stats.stats.items():
        if "plagcheck" not in filename.replace("\\", "/"):
            continue
        rows.append((tottime, "%s:%d" % (os.path.basename(filename), lineno), funcname))
    rows.sort(reverse=True)
    rows = rows[:limit]

    if not rows:
        print("没有采集到项目内的函数样本，跳过绘图")
        return False

    labels = ["%s\n%s" % (name, location) for _t, location, name in rows][::-1]
    values = [value for value, _location, _name in rows][::-1]

    figure, axes = plt.subplots(figsize=(11, 6.5))
    bars = axes.barh(range(len(values)), values, color="#3b7dd8")
    axes.set_yticks(range(len(values)))
    axes.set_yticklabels(labels, fontsize=8)
    axes.set_xlabel("tottime (秒)  —— 函数自身消耗的 CPU 时间", fontsize=10)
    axes.set_title("论文查重程序性能分析：消耗最大的函数（cProfile / tottime）", fontsize=12)
    axes.grid(axis="x", linestyle=":", alpha=0.5)

    total = sum(values) or 1.0
    for bar, value in zip(bars, values):
        axes.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            " %.3fs (%.1f%%)" % (value, value / total * 100),
            va="center",
            fontsize=8,
        )
    axes.set_xlim(0, max(values) * 1.22)
    figure.tight_layout()
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="用 cProfile 分析查重程序的性能瓶颈")
    parser.add_argument("--repeat", type=int, default=10, help="语料放大倍数（默认 10）")
    parser.add_argument("--rounds", type=int, default=3, help="计时轮数（默认 3）")
    parser.add_argument("--label", default=None, help="产物文件名后缀，默认用放大倍数")
    parser.add_argument("--no-chart", action="store_true", help="不生成性能分析图")
    args = parser.parse_args(argv)

    label = args.label or ("%dx" % args.repeat)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    original, copy = load_corpus(args.repeat)
    checker = PlagiarismChecker()

    print("语料规模：原文 %d 字符，抄袭版 %d 字符（放大 %d 倍）" % (len(original), len(copy), args.repeat))

    baseline = run_workload(checker, original, copy, args.rounds)
    print("平均单轮耗时：%.3f 秒" % baseline)

    profiler = collect_stats(original, copy, args.repeat)
    profile_path = os.path.join(OUTPUT_DIR, "compare_files_%s.prof" % label)
    profiler.dump_stats(profile_path)

    report = format_report(profiler)
    report_path = os.path.join(OUTPUT_DIR, "profile_report_%s.txt" % label)
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("语料规模：原文 %d 字符，抄袭版 %d 字符（放大 %d 倍）\n" % (len(original), len(copy), args.repeat))
        handle.write("平均单轮耗时：%.4f 秒\n\n" % baseline)
        handle.write(report)
    print(report)

    if not args.no_chart:
        chart_path = os.path.join(OUTPUT_DIR, "profile_chart_%s.png" % label)
        if render_chart(profiler, chart_path):
            print("已生成性能分析图：%s" % chart_path)

    print("原始数据：%s" % profile_path)
    print("文本报告：%s" % report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
