# -*- coding: utf-8 -*-
"""生成结果合规自检脚本（可直接当验收脚本用）。

它不依赖单元测试框架，而是**另起一条链路**验证生成结果：

1. 生成一批题目；
2. 把每道题的打印文本**重新解析**回表达式树，确认求值与程序给出的答案一致；
3. 遍历表达式树，逐条核对作业约束（范围、无负数、除法为真分数、运算符个数）；
4. 检查同批次题目两两不重复（交换律等价）；
5. 核对作业说明里点名的四组去重例子。

用法::

    python tools/selfcheck.py
    python tools/selfcheck.py -n 10000 -r 100 --seed 2024

全部通过时退出码为 0，任意一条不通过则为 1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arithmetic.expression import Binary, OPERATORS  # noqa: E402
from arithmetic.fraction_utils import parse_number  # noqa: E402
from arithmetic.generator import generate_problems  # noqa: E402
from arithmetic.parser import parse_exercise_line, parse_expression  # noqa: E402

#: 作业说明里点名的去重例子：(式子 A, 式子 B, 是否应当判为同一道题)
DEDUP_EXAMPLES = [
    ("23 + 45", "45 + 23", True),
    ("6 × 8", "8 × 6", True),
    ("3 + (2 + 1)", "1 + 2 + 3", True),
    ("1 + 2 + 3", "3 + 2 + 1", False),
    ("2 − 1", "1 − 2", False),
    ("6 ÷ 3", "3 ÷ 6", False),
]


class Checker:
    """记录每个检查项的结果。"""

    def __init__(self) -> None:
        self.failures: list = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] {name}{('：' + detail) if detail else ''}")
        if not ok:
            self.failures.append(name)

    def report(self) -> int:
        print()
        if self.failures:
            print(f"自检未通过：{len(self.failures)} 项失败 -> {', '.join(self.failures)}")
            return 1
        print("自检全部通过。")
        return 0


def run(count: int, value_range: int, seed: int = 2024, max_ops: int = 3) -> int:
    checker = Checker()
    print(f"生成 {count} 道题目（-r {value_range}，最多 {max_ops} 个运算符，seed={seed}）…")
    result = generate_problems(count, value_range, seed=seed, max_ops=max_ops)
    print(f"实际生成 {len(result.problems)} 道，共尝试 {result.attempts} 次。\n")

    print("1. 数量与去重")
    checker.check("题目数量达标", len(result.problems) == count, f"{len(result.problems)} / {count}")
    keys = {problem.canonical_key() for problem in result.problems}
    checker.check("同批次题目互不重复", len(keys) == len(result.problems),
                  f"唯一规范键 {len(keys)} / 题目 {len(result.problems)}")

    print("2. 作业约束（逐节点遍历）")
    negative_count = 0
    bad_division = 0
    bad_leaf = 0
    too_many_ops = 0
    operator_usage = {operator: 0 for operator in OPERATORS}

    for problem in result.problems:
        if problem.op_count > max_ops or problem.op_count < 1:
            too_many_ops += 1
        stack = [problem.expr]
        while stack:
            node = stack.pop()
            if isinstance(node, Binary):
                operator_usage[node.op] += 1
                left, right = node.left.evaluate(), node.right.evaluate()
                if node.op == "−" and left < right:
                    negative_count += 1
                if node.op == "÷" and not 0 < left < right:
                    bad_division += 1
                stack.extend((node.left, node.right))
            else:
                value = node.number
                if value < 0 or value >= value_range or value.denominator >= value_range:
                    bad_leaf += 1

    checker.check("每道题 1~3 个运算符", too_many_ops == 0, f"违例 {too_many_ops} 处")
    checker.check("减法都不产生负数", negative_count == 0, f"违例 {negative_count} 处")
    checker.check("除法的结果都是真分数（0 < e1 < e2）", bad_division == 0, f"违例 {bad_division} 处")
    checker.check(f"数值都在 [0, {value_range}) 内（含分数分母）", bad_leaf == 0, f"违例 {bad_leaf} 处")
    print("     运算符使用次数：" + "，".join(f"{op} {times}" for op, times in operator_usage.items()))

    print("3. 文本往返一致性（重新解析题目文本，核对答案）")
    round_trip_bad = 0
    answer_bad = 0
    for problem in result.problems:
        if parse_exercise_line(problem.exercise_text()).evaluate() != problem.value:
            round_trip_bad += 1
        if parse_number(problem.answer_text()) != problem.value:
            answer_bad += 1
    checker.check("题目文本可解析且求值一致", round_trip_bad == 0, f"违例 {round_trip_bad} 处")
    checker.check("答案文本可解析且与题目一致", answer_bad == 0, f"违例 {answer_bad} 处")

    print("4. 作业说明里的去重例子")
    for first, second, should_match in DEDUP_EXAMPLES:
        actual = parse_expression(first).canonical_key() == parse_expression(second).canonical_key()
        checker.check(
            f"{first} vs {second}",
            actual == should_match,
            f"期望{'重复' if should_match else '不重复'}，实际{'重复' if actual else '不重复'}",
        )

    return checker.report()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成结果合规自检")
    parser.add_argument("-n", "--count", type=int, default=10000, help="生成题目的个数，默认 10000")
    parser.add_argument("-r", "--range", dest="value_range", type=int, default=100, help="数值范围，默认 100")
    parser.add_argument("--max-ops", type=int, default=3, help="每道题最多几个运算符，默认 3")
    parser.add_argument("--seed", type=int, default=2024, help="随机种子，默认 2024")
    args = parser.parse_args(argv)
    return run(args.count, args.value_range, args.seed, args.max_ops)


if __name__ == "__main__":
    sys.exit(main())
