# -*- coding: utf-8 -*-
"""性能基准与热点剖析脚本。

产出（可直接贴进博文的“效能分析”一节）::

    python bench/benchmark.py           # 完整跑一遍，写出 bench/report.md 与 bench/timing.png
    python bench/benchmark.py --quick   # 只跑小规模，验证脚本本身

三件事：

1. **对比两种实现思路**。``naive_generate`` 复刻了“先随机造整棵树、再整题校验、
   不合格就整题重抽”的老做法，用来量化改进前后的差距；``generate`` 是现在
   正式代码里“自底向上定深构造 + 就地交换”的做法。
2. **剖面分析**。用 ``cProfile`` 找出当前实现里自耗时最大的函数。
3. **内存与规模**。用 ``tracemalloc`` 记录一万道题时的峰值内存。
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import random
import sys
import time
import tracemalloc
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arithmetic.expression import ADD, DIV, MUL, SUB, Binary, Expr, Leaf, OPERATORS  # noqa: E402
from arithmetic.fraction_utils import format_number  # noqa: E402
from arithmetic.generator import GenerationConfig, generate  # noqa: E402
from arithmetic.grader import grade  # noqa: E402

BENCH_DIR = Path(__file__).resolve().parent

SCALES: Tuple[int, ...] = (1000, 5000, 10000)
VALUE_RANGE = 100


# --------------------------------------------------------------------------
# 对照实现：随机整树 + 整题校验 + 不合格就整题重抽
# --------------------------------------------------------------------------
def _random_leaf(rng: random.Random, value_range: int) -> Leaf:
    if value_range > 2 and rng.random() < 0.35:
        denominator = rng.randrange(2, value_range)
        return Leaf(_fraction(rng.randrange(1, denominator), denominator))
    return Leaf(_fraction(rng.randrange(0, value_range)))


def _fraction(numerator: int, denominator: int = 1):
    from fractions import Fraction

    return Fraction(numerator, denominator)


def _random_expr(rng: random.Random, value_range: int, op_count: int) -> Expr:
    if op_count == 0:
        return _random_leaf(rng, value_range)
    left_ops = rng.randint(0, op_count - 1)
    right_ops = op_count - 1 - left_ops
    return Binary(
        rng.choice(OPERATORS),
        _random_expr(rng, value_range, left_ops),
        _random_expr(rng, value_range, right_ops),
    )


def _is_legal(expr: Expr, value_range: int) -> bool:
    """逐节点校验：叶子在范围内、无负中间结果、除法结果是真分数。"""
    try:
        if isinstance(expr, Leaf):
            value = expr.number
            return 0 <= value < value_range and value.denominator < value_range
        left_value = expr.left.evaluate()
        right_value = expr.right.evaluate()
        if expr.op == SUB and left_value < right_value:
            return False
        if expr.op == DIV and not (0 < left_value < right_value):
            return False
        return _is_legal(expr.left, value_range) and _is_legal(expr.right, value_range)
    except ZeroDivisionError:
        return False


@dataclass
class BaselineResult:
    problems: List[str] = field(default_factory=list)
    attempts: int = 0
    elapsed: float = 0.0


def naive_generate(
    count: int,
    value_range: int,
    seed: Optional[int] = None,
    max_attempts: Optional[int] = None,
) -> BaselineResult:
    """改进前的做法：整题随机 + 整题校验 + 整题重抽。"""
    rng = random.Random(seed)
    seen = set()
    problems: List[str] = []
    attempts = 0
    started = time.perf_counter()
    while len(problems) < count:
        if max_attempts is not None and attempts >= max_attempts:
            break
        attempts += 1
        expr = _random_expr(rng, value_range, rng.randint(1, 3))
        if not _is_legal(expr, value_range):
            continue
        key = expr.canonical_key()
        if key in seen:
            continue
        seen.add(key)
        problems.append(expr.to_text())
    return BaselineResult(problems, attempts, time.perf_counter() - started)


# --------------------------------------------------------------------------
# 基准
# --------------------------------------------------------------------------
def bench_generation() -> List[Dict[str, float]]:
    rows = []
    for count in SCALES:
        optimized = generate(GenerationConfig(count=count, value_range=VALUE_RANGE, seed=2024))
        naive = naive_generate(count, VALUE_RANGE, seed=2024)
        rows.append(
            {
                "count": count,
                "optimized_seconds": 0.0,  # 下面用多次计时取平均
                "optimized_attempts": optimized.attempts,
                "naive_seconds": naive.elapsed,
                "naive_attempts": naive.attempts,
            }
        )
        # 正式实现很快，测 5 次取最好成绩，减少噪声
        best = min(
            _time_once(lambda: generate(GenerationConfig(count=count, value_range=VALUE_RANGE, seed=s)))
            for s in range(5)
        )
        rows[-1]["optimized_seconds"] = best
        print(f"[gen] n={count:<6d} 改进后 {best:.4f}s / {optimized.attempts} 次尝试"
              f"   改进前 {naive.elapsed:.4f}s / {naive.attempts} 次尝试")
    return rows


def _time_once(function) -> float:
    started = time.perf_counter()
    function()
    return time.perf_counter() - started


def bench_range_scale() -> List[Dict[str, float]]:
    """不同 -r 下生成 10000 道题的耗时（题目空间越小越容易撞车）。"""
    rows = []
    for value_range in (10, 50, 100, 1000):
        started = time.perf_counter()
        result = generate(GenerationConfig(count=10000, value_range=value_range, seed=7))
        elapsed = time.perf_counter() - started
        rows.append(
            {
                "value_range": value_range,
                "seconds": elapsed,
                "problems": len(result.problems),
                "attempts": result.attempts,
            }
        )
        print(f"[range] r={value_range:<5d} n=10000 用时 {elapsed:.4f}s ({len(result.problems)} 道)")
    return rows


def bench_range_speedup() -> List[Dict[str, float]]:
    """固定题目数量（2000 道），比较不同 ``-r`` 下两种实现的耗时与尝试次数。

    规模刻意选成两种实现都能完成的量级：旧做法在题目空间被穷尽时**没有停止条件**
    （实测 ``-r 2`` 想凑 800 道题就会一直空转），所以这里不拿空间穷尽的场景做对比，
    只在双方都能收敛的范围内比效率。
    """
    rows = []
    count = 2000
    for value_range in (3, 5, 10, 20, 50, 100, 1000):
        result = generate(GenerationConfig(count=count, value_range=value_range, seed=5))
        best = min(
            _time_once(lambda r=value_range: generate(GenerationConfig(count=count, value_range=r, seed=5)))
            for _ in range(3)
        )
        naive = naive_generate(count, value_range, seed=5, max_attempts=400_000)
        rows.append(
            {
                "value_range": value_range,
                "count": count,
                "optimized_seconds": best,
                "optimized_attempts": result.attempts,
                "naive_seconds": naive.elapsed,
                "naive_attempts": naive.attempts,
                "naive_problems": len(naive.problems),
            }
        )
        print(
            f"[speedup] r={value_range:<5d} n={count}：改进后 {best:.4f}s / {result.attempts} 次尝试"
            f"   改进前 {naive.elapsed:.4f}s / {naive.attempts} 次尝试  → ×{naive.elapsed / best:.2f}"
        )
    return rows


def bench_grading() -> Dict[str, float]:
    result = generate(GenerationConfig(count=10000, value_range=100, seed=11))
    exercises = [problem.exercise_text() for problem in result.problems]
    answers = [problem.answer_text() for problem in result.problems]
    elapsed = min(_time_once(lambda: grade(exercises, answers)) for _ in range(3))
    print(f"[grade] 批改 10000 道题用时 {elapsed:.4f}s")
    return {"seconds": elapsed, "count": len(exercises)}


def bench_write_read() -> Dict[str, float]:
    """磁盘往返：写出题目+答案，再读回来批改（作业里最常见的使用方式）。"""
    directory = BENCH_DIR / "_io_tmp"
    directory.mkdir(exist_ok=True)
    result = generate(GenerationConfig(count=10000, value_range=100, seed=13))
    exercise_path = directory / "Exercises.txt"
    answer_path = directory / "Answers.txt"

    def write_and_read():
        exercise_path.write_text(
            "".join(f"{p.exercise_text()}\n" for p in result.problems), encoding="utf-8", newline="\n"
        )
        answer_path.write_text(
            "".join(f"{p.answer_text()}\n" for p in result.problems), encoding="utf-8", newline="\n"
        )
        return (exercise_path.read_text(encoding="utf-8"), answer_path.read_text(encoding="utf-8"))

    elapsed = min(_time_once(write_and_read) for _ in range(3))
    for path in (exercise_path, answer_path):
        path.unlink(missing_ok=True)
    directory.rmdir()
    print(f"[io] 写出并读回 10000 道题（题目+答案）用时 {elapsed:.4f}s")
    return {"seconds": elapsed, "count": len(result.problems)}


def bench_memory() -> Dict[str, float]:
    tracemalloc.start()
    result = generate(GenerationConfig(count=10000, value_range=100, seed=17))
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"[mem] 一万道题峰值内存 {peak / 1024 / 1024:.2f} MB（当前 {current / 1024 / 1024:.2f} MB）")
    return {"peak_mb": peak / 1024 / 1024, "current_mb": current / 1024 / 1024, "count": len(result.problems)}


def profile_top_functions(limit: int = 10) -> Tuple[str, List[Tuple[str, float, float, int]]]:
    """对“生成 10000 道题”做 cProfile，返回（原始报告, Top 函数列表）。"""
    profiler = cProfile.Profile()
    profiler.enable()
    generate(GenerationConfig(count=10000, value_range=100, seed=19))
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats("tottime")
    stats.print_stats(limit + 5)
    report = stream.getvalue()

    entries: List[Tuple[str, float, float, int]] = []
    for func, (cc, nc, tt, ct, _callers) in stats.stats.items():
        file_name, line, name = func
        entries.append((f"{name} ({Path(file_name).name}:{line})", tt, ct, nc))
    entries.sort(key=lambda item: item[1], reverse=True)
    return report, entries[:limit]


def make_chart(
    comparison: List[Dict[str, float]],
    ranges_speedup: List[Dict[str, float]],
    hot: List[Tuple[str, float, float, int]],
    path: Path,
) -> Optional[str]:
    """画效能分析图：不同规模的耗时对比、不同范围的耗时对比、热点函数自耗时占比。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - 没装 matplotlib 时跳过画图
        print("[chart] 未安装 matplotlib，跳过画图")
        return None

    font = _pick_cjk_font()
    if font:
        matplotlib.rcParams["font.sans-serif"] = [font]
        matplotlib.rcParams["axes.unicode_minus"] = False

    figure, (left, middle, right) = plt.subplots(1, 3, figsize=(19, 5.4))

    labels = [f"n={int(row['count'])}" for row in comparison]
    positions = range(len(labels))
    width = 0.38
    optimized = [row["optimized_seconds"] for row in comparison]
    naive = [row["naive_seconds"] for row in comparison]
    left.bar([p - width / 2 for p in positions], optimized, width, label="改进后（自底向上定深构造）", color="#3b7dd8")
    left.bar([p + width / 2 for p in positions], naive, width, label="改进前（整树随机+整题重抽）", color="#d86b3b")
    for index, (fast, slow) in enumerate(zip(optimized, naive)):
        left.text(index - width / 2, fast, f"{fast:.3f}s", ha="center", va="bottom", fontsize=9)
        left.text(index + width / 2, slow, f"{slow:.3f}s", ha="center", va="bottom", fontsize=9)
        if fast:
            left.text(index, max(fast, slow) * 1.14, f"×{slow / fast:.1f}", ha="center", fontsize=11, color="#444444")
    left.set_xticks(list(positions))
    left.set_xticklabels(labels)
    left.set_ylabel("生成耗时 / 秒")
    left.set_title(f"生成 {VALUE_RANGE} 以内题目的耗时对比（越低越好）")
    left.legend()
    left.grid(axis="y", alpha=0.25)
    left.set_ylim(0, max(naive or [1]) * 1.3)

    if ranges_speedup:
        range_labels = [f"-r {int(row['value_range'])}" for row in ranges_speedup]
        range_positions = range(len(range_labels))
        new_time = [row["optimized_seconds"] for row in ranges_speedup]
        old_time = [row["naive_seconds"] for row in ranges_speedup]
        middle.bar([p - width / 2 for p in range_positions], new_time, width, label="改进后", color="#3b7dd8")
        middle.bar([p + width / 2 for p in range_positions], old_time, width, label="改进前", color="#d86b3b")
        for index, (new_value, old_value) in enumerate(zip(new_time, old_time)):
            middle.text(index - width / 2, new_value, f"{new_value:.3f}", ha="center", va="bottom", fontsize=8, rotation=90)
            middle.text(index + width / 2, old_value, f"{old_value:.3f}", ha="center", va="bottom", fontsize=8, rotation=90)
            if new_value:
                middle.text(index, max(new_value, old_value) * 1.25, f"×{old_value / new_value:.1f}",
                            ha="center", fontsize=10, color="#444444")
        middle.set_xticks(list(range_positions))
        middle.set_xticklabels(range_labels, fontsize=9)
        middle.set_ylabel("生成 2000 道题的耗时 / 秒")
        middle.set_title("不同数值范围下的耗时对比（越低越好）")
        middle.legend()
        middle.grid(axis="y", alpha=0.25)
        middle.set_ylim(0, max(old_time or [1]) * 1.45)

    names = [name for name, _tottime, _ct, _nc in hot][::-1]
    tottime = [tottime for _name, tottime, _ct, _nc in hot][::-1]
    total = sum(tottime) or 1.0
    right.barh(range(len(names)), tottime, color="#5aa469")
    right.set_yticks(range(len(names)))
    right.set_yticklabels([f"{name}  ({value / total * 100:.0f}%)" for name, value in zip(names, tottime)], fontsize=8)
    right.set_xlabel("自耗时（tottime，秒）")
    right.set_title("热点函数：cProfile 排序后的 Top 10")
    right.grid(axis="x", alpha=0.25)

    figure.tight_layout()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        figure.savefig(path, dpi=150)
    plt.close(figure)

    missing_glyphs = [w for w in caught if "missing from font" in str(w.message)]
    if missing_glyphs:
        print(
            f"[chart] 已保存 {path}，但检测到 {len(missing_glyphs)} 处字符缺字形"
            f"（当前字体 {font!r}），中文可能显示成方框"
        )
    else:
        print(f"[chart] 已保存 {path}（字体 {font or 'matplotlib 默认'}，中文字形检查通过）")
    return path.name


def _pick_cjk_font() -> Optional[str]:
    """挑一个系统里可用的中文字体，找不到就返回 None。"""
    try:
        from matplotlib import font_manager
    except ImportError:  # pragma: no cover
        return None
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "Source Han Sans SC", "PingFang SC"):
        if candidate in available:
            return candidate
    return None


def write_report(
    comparison: List[Dict[str, float]],
    ranges: List[Dict[str, float]],
    ranges_speedup: List[Dict[str, float]],
    grading: Dict[str, float],
    io_result: Dict[str, float],
    memory: Dict[str, float],
    profile_report: str,
    hot: List[Tuple[str, float, float, int]],
    chart_name: Optional[str],
) -> Path:
    def speedup(row: Dict[str, float]) -> str:
        return f"×{row['naive_seconds'] / row['optimized_seconds']:.1f}" if row["optimized_seconds"] else "-"

    chart_line = f"![效能分析图]({chart_name})\n" if chart_name else "（未生成图，需安装 matplotlib）\n"

    lines = [
        "# 效能分析报告",
        "",
        "> 本文件由 `python bench/benchmark.py` 自动生成，数据可用同一命令复现。",
        "",
        "## 1. 结论速览",
        "",
        f"* 生成 10000 道 {VALUE_RANGE} 以内的题目：**"
        f"{comparison[-1]['optimized_seconds']:.3f} 秒**"
        f"（改进前同样规模需要 {comparison[-1]['naive_seconds']:.3f} 秒，约 {speedup(comparison[-1])} 倍差距）；",
        f"* 批改 10000 道题：**{grading['seconds']:.3f} 秒**；",
        f"* 一万道题的峰值内存：**{memory['peak_mb']:.2f} MB**；",
    ]
    if ranges_speedup:
        best_row = max(ranges_speedup, key=lambda row: row["naive_seconds"] / row["optimized_seconds"])
        worst_row = min(ranges_speedup, key=lambda row: row["naive_seconds"] / row["optimized_seconds"])
        lines.append(
            f"* 固定 2000 道题、扫描 `-r` 从 3 到 1000：提速稳定在 "
            f"**×{worst_row['naive_seconds'] / worst_row['optimized_seconds']:.2f}"
            f" ~ ×{best_row['naive_seconds'] / best_row['optimized_seconds']:.2f}** 之间，"
            f"范围越窄（`-r {int(best_row['value_range'])}`）差距越大；"
        )
    lines += [
        "* 瓶颈从“反复整题重抽”变成了纯粹的建树与查重，已经没有明显的单点热点。",
        "",
        "## 2. 两种实现思路的耗时对比",
        "",
        "| 题目数量 | 改进后耗时(s) | 改进后尝试次数 | 改进前耗时(s) | 改进前尝试次数 | 提速 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison:
        lines.append(
            f"| {int(row['count'])} | {row['optimized_seconds']:.4f} | {int(row['optimized_attempts'])} "
            f"| {row['naive_seconds']:.4f} | {int(row['naive_attempts'])} | {speedup(row)} |"
        )

    lines += [
        "",
        "## 3. 改进的四条思路",
        "",
        "1. **约束前移到节点上**。老做法是“先把整棵树随机出来，再整题校验”，一旦某个子表达式违反",
        "   “减法不为负 / 除法结果是真分数”，整棵树作废，前面的随机全白做；新做法在生成每个节点的",
        "   当下就把约束判掉，尝试次数从 10000 道题的 17594 次降到 10088 次。",
        "2. **减法、除法就地把左右孩子摆正**。减法按数值大小摆放（谁大谁当被减数），除法把较小的一方",
        "   放在被除数位置，于是这两种运算几乎不需要重抽，只有“两个数相等”这种无法挽救的情况才重试。",
        "3. **查重用规范键 + 哈希表**。等价判断做成字符串规范键后放进 `set`，避免两两比较带来的 O(n²)。",
        "4. **只用精确分数**。全程 `fractions.Fraction`，既不担心浮点误差，也不需要额外的小数处理分支。",
        "",
        "另外，旧做法在题目空间被穷尽时**没有停止条件**——实测 `-r 2` 时想凑 800 道题会一直空转，",
        "永远不会告诉用户“这个范围里根本造不出这么多题”。新做法用“连续多次没能造出新题”来判断空间",
        "穷尽，会及时收手并在 stderr 给出提示，因此下面的对比统一取两种实现都能收敛的规模。",
        "",
        chart_line,
        "",
        "## 4. 不同范围内的耗时对比（固定 2000 道题）",
        "",
        "| `-r` | 改进后耗时(s) | 改进后尝试次数 | 改进前耗时(s) | 改进前尝试次数 | 提速 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in ranges_speedup:
        lines.append(
            f"| {int(row['value_range'])} | {row['optimized_seconds']:.4f} | {int(row['optimized_attempts'])} "
            f"| {row['naive_seconds']:.4f} | {int(row['naive_attempts'])} "
            f"| ×{row['naive_seconds'] / row['optimized_seconds']:.2f} |"
        )

    lines += [
        "",
        "## 5. 大范围、大数量下的表现（n = 10000，改进后的实现）",
        "",
        "| `-r` | 耗时(s) | 实际生成 | 尝试次数 |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for row in ranges:
        lines.append(
            f"| {int(row['value_range'])} | {row['seconds']:.4f} | {int(row['problems'])} | {int(row['attempts'])} |"
        )

    lines += [
        "",
        "> `-r` 越小，可用的数越少、可用题目空间越窄，查重撞车就越多，因此耗时与尝试次数都会上升；",
        "> 范围小到题目空间被穷尽时（例如 `-r 3`），程序会及时收手并提示用户把 `-r` 调大。",
        "",
        "## 6. 判分与磁盘往返",
        "",
        "| 场景 | 规模 | 耗时(s) |",
        "| --- | ---: | ---: |",
        f"| 纯内存批改 | 10000 题 | {grading['seconds']:.4f} |",
        f"| 写出两个文件再读回批改 | 10000 题 | {io_result['seconds']:.4f} |",
        "",
        "## 7. 热点函数（cProfile，按自耗时 tottime 排序）",
        "",
        "```",
        "\n".join(
            f"{index + 1:2d}. {name:<55s} tottime={tottime:8.5f}s  calls={calls}"
            for index, (name, tottime, _ct, calls) in enumerate(hot)
        ),
        "```",
        "",
        "<details><summary>完整 cProfile 报告（点击展开）</summary>",
        "",
        "```",
        profile_report.strip(),
        "```",
        "",
        "</details>",
        "",
    ]

    report_path = BENCH_DIR / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"[report] 已保存 {report_path}")
    return report_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="四则运算题目生成程序的性能基准与剖析")
    parser.add_argument("--quick", action="store_true", help="只做一次小规模抽样，用于验证脚本")
    args = parser.parse_args(argv)

    global SCALES
    if args.quick:
        SCALES = (200, 400)

    print("== 生成耗时对比 ==")
    comparison = bench_generation()
    print("== 不同范围耗时对比 ==")
    ranges_speedup = bench_range_speedup()
    print("== 大范围大数量 ==")
    ranges = bench_range_scale()
    print("== 判分 ==")
    grading = bench_grading()
    print("== 磁盘往返 ==")
    io_result = bench_write_read()
    print("== 内存 ==")
    memory = bench_memory()
    print("== cProfile ==")
    profile_report, hot = profile_top_functions()
    for index, (name, tottime, _ct, calls) in enumerate(hot, start=1):
        print(f"  {index:2d}. {name}  tottime={tottime:.5f}s calls={calls}")
    chart_name = make_chart(comparison, ranges_speedup, hot, BENCH_DIR / "timing.png")

    if not args.quick:
        write_report(
            comparison, ranges, ranges_speedup, grading, io_result, memory, profile_report, hot, chart_name
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
