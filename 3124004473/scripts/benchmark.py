#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""性能基准脚本：分阶段实测耗时，并给出优化前后的对照。

为什么除了 :mod:`cProfile` 还需要它
------------------------------------
``cProfile`` 对**每次 Python 函数调用**都要做一次插桩，因此会严重
高估"调用次数极多、单次极廉价"的函数。性能优化第一版就踩了这个坑：
在放大 10 倍的语料上，``cProfile`` 把 64% 的时间算在 ``normalize`` 头上
（因为里面有 18.7 万次 ``lower()``、22.8 万次 ``isalnum()`` 调用），
而**直接分阶段计时**显示，在真实语料规模上真正的瓶颈是顺序敏感信号，
它占了 95.6% 的运行时间。两者结论完全不同，必须以后者为准。

本脚本因此不使用任何插桩，只用 ``time.perf_counter`` 包围每一段
真实执行路径。

用法::

    python scripts/benchmark.py
    python scripts/benchmark.py --no-chart

输出:
    docs/profile/benchmark.txt        分阶段耗时与前后对照表
    docs/profile/benchmark_chart.png  各阶段耗时占比柱状图
"""

from __future__ import annotations

# 本脚本把 matplotlib 的导入放在函数内部：它是"画图"这一可选步骤才需要的
# 依赖，做纯计时的用户不该被迫加载整套绘图库。
# pylint: disable=import-outside-toplevel

import argparse
import gc
import os
import sys
import time
from difflib import SequenceMatcher

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PACKAGE_ROOT)

from plagcheck import PlagiarismChecker  # noqa: E402
from plagcheck.normalize import normalize  # noqa: E402
from plagcheck.similarity import cosine, coverage, lcs_length, sequence_ratio  # noqa: E402
from plagcheck.textio import read_text_file  # noqa: E402
from plagcheck.tokenize import ngram_frequencies  # noqa: E402

DATA_DIR = os.path.join(PACKAGE_ROOT, "tests", "data")
OUTPUT_DIR = os.path.join(PACKAGE_ROOT, "docs", "profile")

#: 分阶段计时前的热身轮数，避免把解释器的首次执行开销算进结果。
WARMUP_ROUNDS = 2

#: 每个测量点重复的次数，取最小值以抑制系统抖动。
MEASURE_ROUNDS = 5


def measure(func, rounds: int = MEASURE_ROUNDS) -> float:
    """重复执行 ``func`` 并返回最快一次的耗时。"""
    best = float("inf")
    for _ in range(rounds):
        started = time.perf_counter()
        func()
        best = min(best, time.perf_counter() - started)
    return best


def stage_breakdown(original: str, copy: str) -> dict:
    """逐阶段计时，返回 ``{阶段名: 秒}``。

    顺序与 :meth:`plagcheck.engine.PlagiarismChecker.compare_texts` 的
    真实执行顺序一致，因此各阶段耗时可加。
    """
    stages = {}

    stages["归一化 normalize"] = measure(
        lambda: (normalize(original), normalize(copy))
    )

    normalized_original = normalize(original)
    normalized_copy = normalize(copy)

    def build_ngrams():
        for size in (1, 2, 3):
            ngram_frequencies(normalized_original, size)
            ngram_frequencies(normalized_copy, size)

    stages["n-gram 词频统计"] = measure(build_ngrams)

    original_grams = {n: ngram_frequencies(normalized_original, n) for n in (1, 2, 3)}
    copy_grams = {n: ngram_frequencies(normalized_copy, n) for n in (1, 2, 3)}

    def compute_metrics():
        for size in (1, 2, 3):
            coverage(original_grams[size], copy_grams[size])
        cosine(original_grams[2], copy_grams[2])

    stages["覆盖率与余弦"] = measure(compute_metrics)

    uses_sequence = max(len(normalized_original), len(normalized_copy)) <= 50_000
    if uses_sequence:
        stages["顺序相似度 sequence_ratio"] = measure(
            lambda: sequence_ratio(normalized_original, normalized_copy)
        )
    else:
        stages["顺序相似度 sequence_ratio"] = 0.0

    stages["端到端 compare_texts"] = measure(
        lambda: PlagiarismChecker().compare_texts(original, copy)
    )
    return stages


def sequence_signal_comparison(original: str, copy: str) -> list:
    """对比旧实现（difflib）与新实现（位并行 LCS）在顺序信号上的表现。

    返回 ``[(规模说明, 字符数, difflib 秒, LCS 秒, 两者结果是否一致)]``。
    """
    rows = []
    normalized_original = normalize(original)
    normalized_copy = normalize(copy)

    for repeat in (1, 2, 4):
        left = normalized_original * repeat
        right = normalized_copy * repeat

        def run_difflib():
            matcher = SequenceMatcher(None, left, right, autojunk=False)
            return sum(block.size for block in matcher.get_matching_blocks())

        elapsed_difflib = measure(run_difflib, rounds=1 if repeat > 2 else 3)
        elapsed_lcs = measure(lambda: lcs_length(left, right), rounds=3)

        difflib_total = 2 * run_difflib() / (len(left) + len(right))
        lcs_total = 2 * lcs_length(left, right) / (len(left) + len(right))
        rows.append(
            (
                "%d 倍语料" % repeat,
                len(left),
                elapsed_difflib,
                elapsed_lcs,
                abs(difflib_total - lcs_total) < 1e-12,
            )
        )
    return rows


def render_chart(stages: dict, target: str) -> bool:
    """把各阶段耗时画成横向柱状图（剔除端到端合计项，避免重复计数）。"""
    # pylint: disable=too-many-locals
    # 绘图需要同时持有标签、数值、坐标轴与样式参数，变量偏多属正常。
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("未安装 matplotlib，跳过绘图")
        return False

    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "SimSun", "DejaVu Sans"):
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False

    items = [(name, value) for name, value in stages.items() if name != "端到端 compare_texts"]
    items.sort(key=lambda item: item[1])
    labels = [name for name, _value in items]
    values = [value for _name, value in items]

    figure, axes = plt.subplots(figsize=(10, 5))
    bars = axes.barh(labels, values, color="#2f7d4f")
    axes.set_xlabel("单次比对耗时（秒）", fontsize=10)
    axes.set_title("论文查重：各处理阶段耗时（真实语料 orig.txt vs orig_add.txt）", fontsize=12)
    axes.grid(axis="x", linestyle=":", alpha=0.5)

    total = sum(values) or 1.0
    for bar, value in zip(bars, values):
        axes.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            " %.4fs (%.1f%%)" % (value, value / total * 100),
            va="center",
            fontsize=9,
        )
    axes.set_xlim(0, max(values) * 1.3 if values else 1.0)
    figure.tight_layout()
    figure.savefig(target, dpi=150)
    plt.close(figure)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="查重程序性能基准：分阶段计时与优化前后对照")
    parser.add_argument("--no-chart", action="store_true", help="不生成图表")
    args = parser.parse_args(argv)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    original = read_text_file(os.path.join(DATA_DIR, "orig.txt"))
    copy = read_text_file(os.path.join(DATA_DIR, "orig_add.txt"))

    for _ in range(WARMUP_ROUNDS):
        PlagiarismChecker().compare_texts(original, copy)

    lines = []
    lines.append("论文查重程序性能基准")
    lines.append("=" * 62)
    lines.append("语料：orig.txt (%d 字符) vs orig_add.txt (%d 字符)" % (len(original), len(copy)))
    lines.append("")

    # 顺序信号的对照**先跑**：它要在堆比较干净的时候测量。放在后面会被
    # 100x 阶段产生的大量 n-gram 字典挤出的内存碎片拖慢，测出偏大的数字。
    gc.collect()
    lines.append("--- 顺序敏感信号：优化前后对照 ---")
    lines.append("  %-12s %8s %12s %12s %8s" % ("规模", "字符数", "difflib", "位并行LCS", "提速"))
    for name, length, before, after, same in sequence_signal_comparison(original, copy):
        lines.append(
            "  %-12s %8d %11.4fs %11.4fs %7.1fx  结果一致=%s"
            % (name, length, before, after, before / after if after else 0.0, same)
        )
    lines.append("")

    for label, scale in (("真实规模 1x", 1), ("放大 10x", 10), ("放大 100x", 100)):
        gc.collect()
        stages = stage_breakdown(original * scale, copy * scale)
        lines.append("--- %s ---" % label)
        total = sum(value for name, value in stages.items() if name != "端到端 compare_texts")
        for name, value in stages.items():
            if name == "端到端 compare_texts":
                continue
            share = value / total * 100 if total else 0.0
            lines.append("  %-26s %9.4f s  %5.1f%%" % (name, value, share))
        lines.append("  %-26s %9.4f s" % ("阶段合计", total))
        lines.append("  %-26s %9.4f s" % ("端到端实测", stages["端到端 compare_texts"]))
        lines.append("")

    report = "\n".join(lines)
    print(report)

    report_path = os.path.join(OUTPUT_DIR, "benchmark.txt")
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(report + "\n")
    print("\n已写入：%s" % report_path)

    if not args.no_chart:
        chart_path = os.path.join(OUTPUT_DIR, "benchmark_chart.png")
        if render_chart(stage_breakdown(original, copy), chart_path):
            print("已生成图表：%s" % chart_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
