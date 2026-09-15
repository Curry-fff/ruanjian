# -*- coding: utf-8 -*-
"""文本归一化。

查重算法最怕"表面差异掩盖真实抄袭"：把逗号换成句号、把全角换成半角、
在句子里塞几个换行，都不应该让两份实质相同的论文看起来毫不相关。
归一化层负责把这类无意义的书写差异抹平，只留下可比对的"内容信号"。

处理步骤：

1. **Unicode NFKC 兼容分解**：全角字母数字 ``ＡＢＣ``→``ABC``、
   全角标点 ``，``→``,``、上标/罗马数字等统一成常规形态；
2. **丢弃空白与标点（默认）**：只保留字母、数字、汉字等在
   ``str.isalnum()`` 下为真的字符。这一步让"标点被改写"完全不扣分；
3. **大小写折叠**：``Python`` 与 ``python`` 视为同一内容。

被保留下来的字符拼成一条连续字符串，供后续 n-gram 切分使用。
"""

from __future__ import annotations

import unicodedata

__all__ = ["normalize", "is_effectively_empty"]


def normalize(
    text: str,
    *,
    keep_punctuation: bool = False,
    casefold: bool = True,
) -> str:
    """把原始文本归一化成只含"内容字符"的字符串。

    参数:
        text: 原始文本（任意编码解码后的 ``str``）。
        keep_punctuation: 为 ``True`` 时只丢空白、保留标点。
            适用于"标点本身也有信息量"的场景（例如比对代码、公式）。
            默认 ``False``，因为中文论文的标点改写属于常见伪装手段。
        casefold: 是否把大写字母折叠成小写。默认 ``True``。

    返回:
        归一化后的文本；``text`` 为空时返回空串。

    复杂度:
        ``O(len(text))``，单次遍历。
    """
    if not text:
        return ""

    decomposed = unicodedata.normalize("NFKC", text)

    characters = []
    append = characters.append

    if keep_punctuation:
        for character in decomposed:
            if character.isspace():
                continue
            append(character.lower() if casefold else character)
    else:
        for character in decomposed:
            # isalnum() 对汉字、假名、字母、数字都为真，
            # 对标点、空白、控制字符、符号都为假——正好是我们要的过滤规则。
            if character.isalnum():
                append(character.lower() if casefold else character)

    return "".join(characters)


def is_effectively_empty(normalized_text: str) -> bool:
    """判断归一化结果是否"等于没有内容"。

    用途：区分两种空输入。
    * 0 字节文件 → :class:`~plagcheck.exceptions.EmptyDocumentError`（输入非法）；
    * 非空文件但去掉标点空白后为空（例如整篇都是 ``……``）→ 合法输入，
      按约定重复率记 ``0.00``。
    """
    return not normalized_text
