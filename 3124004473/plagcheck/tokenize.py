# -*- coding: utf-8 -*-
"""n-gram 切分与词频统计。

为什么用 **字符 n-gram** 而不是分词？

* 中文分词需要词典（jieba 等第三方库），会引入运行时依赖、提高评测
  环境的安装风险，而且对"周天/星期天"这类近义改写的切分结果不稳定；
* 字符 n-gram 不需要任何词典，对 **增、删、改** 三种抄袭手段都有
  稳定的响应：改动一个字符只影响 n 个窗口，删除一段只让局部窗口失配；
* 它天然是"局部指纹"，连续抄袭会留下大片重合的 n-gram，而独立写作
  的两篇文章在 n=3、n=4 上几乎不可能偶然重合。

代价是丢失词边界信息，因此引擎会同时使用多种 n 值互相补偿。
"""

from __future__ import annotations

from collections import Counter

__all__ = ["ngram_frequencies", "total_frequency"]

#: 词频字典的类型别名：n-gram 字符串 -> 出现次数。
FrequencyMap = dict


def ngram_frequencies(text: str, n: int) -> FrequencyMap:
    """统计 ``text`` 中所有长度为 ``n`` 的字符 n-gram 及其出现次数。

    参数:
        text: 已归一化的文本（见 :func:`plagcheck.normalize.normalize`）。
        n: n-gram 窗口长度，必须 >= 1。

    返回:
        ``{n-gram: 出现次数}``。返回值满足
        ``sum(result.values()) == max(len(text) - n + 1, 1)``。

    边界约定:
        * ``text`` 为空 → 返回空字典；
        * ``len(text) < n`` → 整段文本自成一个 n-gram，返回 ``{text: 1}``。
          这样做是为了让极短文本（例如只有两三个字的标题）也能参与
          比对，而不是因为"窗口放不下"就直接判定为 0% 重合。

    异常:
        ValueError: ``n < 1``。

    实现说明:
        ``zip(*(text[k:] for k in range(n)))`` 在 C 层一次性拉出所有
        滑动窗口，比 Python 层逐个切片快得多；显式循环版本见
        ``docs/profile`` 中的性能对比。
    """
    if n < 1:
        raise ValueError(f"n-gram 长度必须 >= 1，实际为 {n!r}")

    length = len(text)
    if length == 0:
        return {}
    if length < n:
        return {text: 1}

    return Counter(map("".join, zip(*(text[offset:] for offset in range(n)))))


def total_frequency(frequencies: FrequencyMap) -> int:
    """返回词频字典的总词数（含重复计数）。

    等价于 ``sum(frequencies.values())``，单独抽出成函数是为了让
    引擎层的公式读起来与数学定义一一对应。
    """
    return sum(frequencies.values())
