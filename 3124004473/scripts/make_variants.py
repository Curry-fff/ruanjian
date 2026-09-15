#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试语料生成器：按字符级"增 / 删 / 乱序"三种手段合成抄袭版。

用途
----
课程下发的语料只有 ``orig.txt`` 与 ``orig_add.txt``，``orig_0.8_del``、
``orig_0.8_dis_*`` 等文件并不公开。为了能客观评估算法在不同抄袭手段
下的**准确度**（而不是凭感觉调参），本脚本按照题面描述的手段，在原文
上合成同等强度的变体，作为标定与回归测试的语料。

合成规则（目标相似度约 0.8，即改动 20% 的字符）
------------------------------------------------
* ``add``：保留原文全部字符，随机插入约 20% 的噪声汉字。
  噪声字从 CJK 基本区随机抽取，绝大多数是原文中没出现过的生僻字——
  这一点是对照着真实 ``orig_add.txt`` 的统计特征设计的：真实的增版
  插入了 1763 个字，其中约 990 个是原文从未出现过的字符。
* ``del``：随机删除原文约 20% 的字符。
* ``dis_d``：以概率 20% 选中一个位置，把它与相距 ``d`` 个位置的字符
  交换，制造局部乱序。
* ``copy``：逐字照抄，用作上界基准（必须得 1.00）。

用法::

    python scripts/make_variants.py <原文文件> <输出目录>
"""

from __future__ import annotations

import os
import random
import sys

#: CJK 统一汉字基本区的起止码点。
CJK_START = 0x4E00
CJK_END = 0x9FA5

#: 改动比例：0.2 对应语料命名中的 "0.8"。
NOISE_RATIO = 0.20

#: 乱序变体的交换距离。
DISORDER_DISTANCES = (1, 10, 15)

DEFAULT_SEED = 20240917


def _noise_pool(size: int, forbidden: set, rng: random.Random) -> list:
    """抽取 ``size`` 个"原文中没出现过"的随机汉字。

    真实语料的增版几乎不重复使用同一个噪声字，因此这里也逐个抽取并
    剔除已在原文或本批噪声中出现过的字符，尽量贴近真实分布。
    """
    pool = []
    used = set(forbidden)
    while len(pool) < size:
        candidate = chr(rng.randint(CJK_START, CJK_END))
        if candidate in used:
            continue
        used.add(candidate)
        pool.append(candidate)
    return pool


def make_add(original: str, rng: random.Random, ratio: float = NOISE_RATIO) -> str:
    """增：保留全部原文，随机插入噪声字。"""
    insert_count = int(len(original) * ratio)
    noise = _noise_pool(insert_count, set(original), rng)
    characters = list(original)
    for character in noise:
        characters.insert(rng.randrange(len(characters) + 1), character)
    return "".join(characters)


def make_del(original: str, rng: random.Random, ratio: float = NOISE_RATIO) -> str:
    """删：随机删掉一部分字符。"""
    delete_count = int(len(original) * ratio)
    victims = set(rng.sample(range(len(original)), delete_count))
    return "".join(ch for index, ch in enumerate(original) if index not in victims)


def make_disorder(original: str, rng: random.Random, distance: int, ratio: float = NOISE_RATIO) -> str:
    """乱序：以一定概率把每个字符与相距 ``distance`` 的字符交换。"""
    characters = list(original)
    for index in range(len(characters) - distance):
        if rng.random() < ratio:
            characters[index], characters[index + distance] = (
                characters[index + distance],
                characters[index],
            )
    return "".join(characters)


def build_variants(original: str, seed: int = DEFAULT_SEED) -> dict:
    """生成全部变体，返回 ``{文件名: 文本}``。"""
    rng = random.Random(seed)
    variants = {
        "orig_copy.txt": original,
        "orig_0.8_add.txt": make_add(original, rng),
        "orig_0.8_del.txt": make_del(original, rng),
    }
    for distance in DISORDER_DISTANCES:
        variants["orig_0.8_dis_%d.txt" % distance] = make_disorder(
            original, rng, distance
        )
    return variants


def read_text(path: str) -> str:
    """读取原文，自动兼容 UTF-8 与 GB18030。"""
    with open(path, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main(argv: list) -> int:
    if len(argv) != 3:
        print(__doc__)
        print("用法: python scripts/make_variants.py <原文文件> <输出目录>")
        return 2

    original = read_text(argv[1])
    output_dir = argv[2]
    os.makedirs(output_dir, exist_ok=True)

    for name, text in build_variants(original).items():
        target = os.path.join(output_dir, name)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print("已生成 %-22s 字符数 %6d" % (name, len(text)))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
