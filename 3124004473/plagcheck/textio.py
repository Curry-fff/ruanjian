# -*- coding: utf-8 -*-
"""文件读写层。

本模块是程序与磁盘之间的唯一通道，它承担三件事：

1. **只碰被指定的文件**。程序自始至终只会打开命令行给出的三个路径，
   不会读写配置文件、缓存、日志或任何其他文件——这是作业的硬性约束。
2. **编码自适应**。评测语料可能是 UTF-8（含 BOM）、GBK/GB18030 或
   UTF-16，本模块按"先严格、后宽松"的顺序试解码，尽可能还原文本，
   并且在任何情况下都不抛出 ``UnicodeDecodeError``。
3. **答案格式固定**。按题目要求输出精确到小数点后两位的浮点数。
"""

from __future__ import annotations

import os

from .exceptions import (
    EmptyDocumentError,
    InputPathError,
    InputReadError,
    OutputWriteError,
)

__all__ = [
    "read_text_file",
    "write_answer_file",
    "format_answer",
    "MAX_INPUT_BYTES",
    "DETECT_ENCODINGS",
]

#: 单个输入文件的字节上限。超过它就有突破 2048 MB 内存上限的风险，
#: 因此在读取之前先行拦截（作业约束：内存占用不得超过 2048 MB）。
#:
#: 这些模块级常量刻意写成"大写名 + 类型注解"，而没有引入
#: ``typing.Final``：本机的代码质量分析工具是 pylint 2.16，其依赖的
#: astroid 无法解析 Python 3.12 标准库 ``typing.py`` 中的 PEP 695
#: 类型别名语法，只要有任何模块 ``import typing``，pylint 就会以
#: ``Fatal error (astroid-error)`` 崩溃。去掉这一个可选装饰后，整个
#: 包在 pylint 下可以做到零告警（见 docs/design.md 的说明）。
MAX_INPUT_BYTES: int = 512 * 1024 * 1024

#: 解码试探顺序。
#:
#: ``utf-8-sig`` 排在最前，是为了顺手吃掉 UTF-8 BOM（否则 BOM 会变成
#: 一个不可见字符混进正文）；``utf-8`` 严格模式用于识别真正的 UTF-8；
#: 之后才是中文语料常见的 ``gb18030``（GBK 的超集，覆盖面更广）。
#: 最后的 ``utf-16`` 需要 BOM 才能正确解码，所以放在最后兜底。
DETECT_ENCODINGS: tuple = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "big5",
    "utf-16",
)

#: 答案文件的小数位数——题目要求"精确到小数点后两位"。
ANSWER_PRECISION: int = 2


def read_text_file(path: str) -> str:
    """读取一个文本文件的全部内容，并自动识别其编码。

    参数:
        path: 论文文件的绝对路径（相对路径同样可用，会被规范化）。

    返回:
        文件解码后的完整文本。行尾不做任何统一处理——换行符在后续
        归一化阶段会被当作空白字符丢弃，因此这里保留原始形态。

    异常:
        InputPathError: 路径不存在、不是普通文件。
        EmptyDocumentError: 文件是 0 字节。
        InputReadError: 读盘失败、文件过大或编码完全无法识别。
    """
    absolute_path = os.path.abspath(path)

    if not os.path.exists(absolute_path):
        raise InputPathError(f"输入文件不存在：{absolute_path}")
    if not os.path.isfile(absolute_path):
        raise InputPathError(f"输入路径不是普通文件：{absolute_path}")

    try:
        size = os.path.getsize(absolute_path)
    except OSError as error:  # pragma: no cover - 极端文件系统故障
        raise InputReadError(f"无法获取文件大小：{absolute_path}（{error}）") from error

    if size == 0:
        raise EmptyDocumentError(f"输入文件为空（0 字节）：{absolute_path}")
    if size > MAX_INPUT_BYTES:
        megabytes = size / 1024 / 1024
        limit_megabytes = MAX_INPUT_BYTES / 1024 / 1024
        raise InputReadError(
            f"输入文件过大：{absolute_path}（{megabytes:.1f} MB，上限 {limit_megabytes:.0f} MB）"
        )

    try:
        with open(absolute_path, "rb") as handle:
            raw = handle.read()
    except OSError as error:
        raise InputReadError(f"读取文件失败：{absolute_path}（{error}）") from error
    except MemoryError as error:  # pragma: no cover - 需要极端环境
        raise InputReadError(f"读取文件时内存不足：{absolute_path}") from error

    return decode_bytes(raw)


def decode_bytes(raw: bytes) -> str:
    """按"先精确、后宽松"的顺序把字节解码成文本。

    候选编码的顺序分两段：

    1. **BOM 段**：先看开头是不是 UTF-8 BOM（``EF BB BF``）或 UTF-16
       BOM（``FF FE`` / ``FE FF``）。BOM 是文件自己声明的编码，可信度
       最高，应当优先采用。
    2. **试探段**：依 :data:`DETECT_ENCODINGS` 逐个严格试解。

    任何一步失败都只是"换下一个候选"，绝不向上抛异常。全部失败时
    退化为 ``utf-8`` + ``errors="replace"``，宁可损失少量字符也要
    保证程序给出答案，而不是崩溃退出。

    注意 BOM 段必须允许失败：一个以 ``FF FE`` 开头、长度却是奇数的
    文件并不是合法 UTF-16，此时应当继续尝试常规编码，而不是直接报错。
    """
    candidates = []
    if raw.startswith(b"\xef\xbb\xbf"):
        candidates.append("utf-8-sig")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates.append("utf-16")
    candidates.extend(DETECT_ENCODINGS)

    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    # GB18030 几乎能吃掉任意字节串，走到这里说明数据非常规。
    return raw.decode("utf-8", errors="replace")


def format_answer(duplication: float) -> str:
    """把重复率格式化成答案文件中的字符串。

    题目要求"浮点型、精确到小数点后两位"，因此统一使用 ``%.2f``。
    先把取值夹紧到 ``[0.00, 1.00]``，避免浮点误差产生 ``-0.00``
    或 ``1.0000000000000002`` 之类的越界输出。
    """
    clamped = min(1.0, max(0.0, float(duplication)))
    return f"{clamped:.{ANSWER_PRECISION}f}"


def write_answer_file(path: str, duplication: float) -> str:
    """把重复率写入答案文件。

    参数:
        path: 答案文件的绝对路径。
        duplication: 重复率，取值 0.0 ~ 1.0。

    返回:
        实际写入的字符串（例如 ``"0.44"``），方便调用方打日志。

    异常:
        OutputWriteError: 目标目录无法创建，或文件写入失败。

    实现说明:
        内容不带结尾换行符。这样无论评测方是 ``float(f.read())``、
        还是按行读取、还是与期望字符串做严格比较，都能得到一致结果。
    """
    absolute_path = os.path.abspath(path)
    text = format_answer(duplication)

    parent = os.path.dirname(absolute_path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as error:
            raise OutputWriteError(
                f"答案文件所在目录不存在且无法创建：{parent}（{error}）"
            ) from error

    try:
        with open(absolute_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as error:
        raise OutputWriteError(f"写入答案文件失败：{absolute_path}（{error}）") from error

    return text
