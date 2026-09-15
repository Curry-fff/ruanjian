# -*- coding: utf-8 -*-
"""相似度度量。

本模块只提供"纯函数"，不碰文件、不读配置、不做时间统计——所有
度量都以词频字典或字符串为输入、以 ``[0.0, 1.0]`` 的浮点数为输出，
因此可以单独做单元测试和边界穷举。

三种度量各自回答一个不同的问题：

===================  ==============================================
度量                 回答的问题
===================  ==============================================
``coverage``         抄袭版里有多大比例的内容在原文中出现过？（主指标）
``cosine``           两篇文本的整体用词分布有多接近？
``sequence_ratio``   两篇文本的**顺序**有多接近？（增删改敏感）
===================  ==============================================
"""

from __future__ import annotations

import math
from difflib import SequenceMatcher

from .tokenize import total_frequency

__all__ = ["coverage", "cosine", "jaccard", "sequence_ratio"]


def coverage(reference: dict, target: dict) -> float:
    """``target`` 的 n-gram 被 ``reference`` 覆盖的比例（含词频）。

    数学定义::

        coverage = Σ_g min(tf_ref(g), tf_tgt(g)) / Σ_g tf_tgt(g)

    这个量正是"重复率"最自然的定义：把抄袭版拆成一堆 n-gram 指纹，
    数一数其中有多少能在原文里找到**足量**的对应物。

    * 抄袭版完全由原文复制而来（哪怕中间插入了新段落，只要这段
      文字本身取自原文）→ 接近 ``1.0``；
    * 抄袭版只是原文的一小段摘抄 → 仍然是 ``1.0``（对摘抄式抄袭敏感）；
    * 抄袭版大面积重写、只剩少量原句 → 接近 ``0.0``。

    注意本函数是**非对称**的：``coverage(a, b) != coverage(b, a)``。
    调用时参数顺序为 ``(原文, 抄袭版)``。

    参数:
        reference: 参考文本（原文）的 n-gram 词频。
        target: 待考察文本（抄袭版）的 n-gram 词频。

    返回:
        ``0.0 ~ 1.0`` 的浮点数；``target`` 为空时返回 ``0.0``。
    """
    target_total = total_frequency(target)
    if target_total == 0:
        return 0.0

    # 遍历较小的字典以减少查表次数：min() 对两边是对称的。
    if len(reference) > len(target):
        reference, target = target, reference

    shared = 0
    reference_get = reference.get
    for gram, target_count in target.items():
        reference_count = reference_get(gram, 0)
        shared += target_count if reference_count > target_count else reference_count

    return shared / target_total


def cosine(frequencies_a: dict, frequencies_b: dict) -> float:
    """两个 n-gram 词频向量的余弦相似度。

    ``cos = Σ_g tf_a(g)·tf_b(g) / (‖tf_a‖·‖tf_b‖)``

    与 :func:`coverage` 互补：coverage 只惩罚"抄袭版里有多少新东西"，
    cosine 还会惩罚"原文里有多少内容没被抄到"，因此对"部分抄袭"
    给出更温和的分数。两者取长补短。

    返回:
        ``0.0 ~ 1.0``；任一向量为零向量时返回 ``0.0``。
    """
    if not frequencies_a or not frequencies_b:
        return 0.0

    if len(frequencies_a) > len(frequencies_b):
        frequencies_a, frequencies_b = frequencies_b, frequencies_a

    dot_product = 0
    frequencies_b_get = frequencies_b.get
    for gram, count_a in frequencies_a.items():
        count_b = frequencies_b_get(gram, 0)
        if count_b:
            dot_product += count_a * count_b

    if dot_product == 0:
        return 0.0

    norm_a = math.sqrt(sum(count * count for count in frequencies_a.values()))
    norm_b = math.sqrt(sum(count * count for count in frequencies_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return min(1.0, dot_product / (norm_a * norm_b))


def jaccard(frequencies_a: dict, frequencies_b: dict) -> float:
    """n-gram 词频字典的 (多重集) Jaccard 系数。

    ``J = Σ min / Σ max``。它同时惩罚"多出来的"和"没抄到的"内容，
    是比 coverage 更严格的度量，用于报告与调参，不参与最终加权。
    """
    if not frequencies_a and not frequencies_b:
        return 0.0

    shared = 0
    union = 0
    for gram in set(frequencies_a) | set(frequencies_b):
        count_a = frequencies_a.get(gram, 0)
        count_b = frequencies_b.get(gram, 0)
        shared += count_a if count_a < count_b else count_b
        union += count_a if count_a > count_b else count_b

    if union == 0:
        return 0.0
    return shared / union


def sequence_ratio(text_a: str, text_b: str) -> float:
    """基于最长匹配块的顺序敏感相似度。

    等价于 ``difflib.SequenceMatcher.ratio()``，即
    ``2·M / (len(a) + len(b))``，``M`` 是所有匹配块长度之和。

    为什么还需要它：n-gram 度量只看"内容出现了没有"，不看"出现在
    哪里"。把原文所有句子打乱重排，n-gram coverage 依然是 1.0，但
    人一眼就能看出这不是正常写作。本度量能捕捉这种顺序异常。

    参数 ``autojunk=False`` 是刻意的：``SequenceMatcher`` 默认会把
    长序列中占比超过 1% 的"高频元素"当成垃圾丢掉，而在按字符切分的
    中文长文本里，这会误伤"的""是"等真正承载信息的常用字，导致
    相似度被系统性地低估。

    参数:
        text_a, text_b: 已归一化的文本。

    返回:
        ``0.0 ~ 1.0``；任一文本为空时返回 ``0.0``。

    复杂度:
        最坏 ``O(len(a)·len(b))``，因此调用方必须对输入长度设上限，
        见 :data:`plagcheck.engine.MAX_SEQUENCE_CHARS`。
    """
    if not text_a or not text_b:
        return 0.0
    if text_a == text_b:
        return 1.0

    matcher = SequenceMatcher(None, text_a, text_b, autojunk=False)
    return matcher.ratio()
