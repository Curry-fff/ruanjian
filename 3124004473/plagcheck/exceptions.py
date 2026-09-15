# -*- coding: utf-8 -*-
"""异常体系。

设计目标（对应作业评分点「异常处理说明」）：

1. **单一职责**：每一种异常只描述一类可以被独立诊断的故障场景，
   这样单元测试才能对"哪种输入触发哪种异常"做精确断言。
2. **不吞错**：库层只把标准库异常"翻译"成本项目异常，绝不在
   ``except`` 之后静默返回一个看起来正常的返回值——那会把故障
   伪装成结果。
3. **可定位**：异常消息中必须带上出错的绝对路径或具体数值，
   使用者不需要打开调试器就能知道是哪一步、哪个文件出的问题。
4. **与退出码绑定**：每个异常自带 ``exit_code``，命令行入口据此
   返回确定的进程退出码。这样程序永远不会"抛异常崩溃退出"，
   而是"带诊断信息、以约定码正常退出"。
"""

from __future__ import annotations

__all__ = [
    "PlagCheckError",
    "ArgumentError",
    "InputPathError",
    "InputReadError",
    "EmptyDocumentError",
    "OutputWriteError",
]


class PlagCheckError(Exception):
    """本项目所有自定义异常的基类。

    属性:
        message: 面向使用者的中文错误说明。
        exit_code: 命令行入口应当返回的进程退出码。

    退出码约定::

        0  成功
        2  命令行参数错误
        3  输入路径不存在或不是普通文件
        4  输入文件读取失败（IO 错误 / 文件过大）
        5  输入文件为空（0 字节）
        6  答案文件写入失败
        1  其他未预期错误（由命令行入口兜底）
    """

    exit_code: int = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - 直接复用基类实现
        return self.message


class ArgumentError(PlagCheckError):
    """命令行参数不合法：数量不对、路径为空字符串等。

    场景：使用者只传了 2 个参数，或把某个参数写成空字符串。
    设计目标：在真正碰磁盘之前就把用法错误拦住，给出正确的调用示例。
    """

    exit_code = 2


class InputPathError(PlagCheckError):
    """输入路径不可用：不存在、是目录、或是无权限访问的路径。

    场景：``orig.txt`` 拼写错误，或把文件夹路径当成论文文件传了进来。
    设计目标：明确区分"路径本身有问题"与"文件内容读不出来"，
    避免把 ``IsADirectoryError`` 之类的底层异常直接抛给使用者。
    """

    exit_code = 3


class InputReadError(PlagCheckError):
    """输入文件存在但读不出来：IO 错误、编码无法识别、文件超出上限。

    场景：文件被其他进程独占、磁盘掉线，或文件大到会突破
    2048 MB 内存上限。
    设计目标：把 ``OSError`` / ``MemoryError`` 统一翻译成本异常，
    保证进程不会因为底层异常而崩溃退出。
    """

    exit_code = 4


class EmptyDocumentError(PlagCheckError):
    """输入文件是 0 字节，不能作为一篇论文参与比对。

    场景：评测时把空文件传了进来，或误传了尚未写入内容的答案文件。
    设计目标：显式报错，而不是让空文档参与计算并输出一个
    看似合法的 0.00——前者是"输入有问题"，后者是"结果不可信"。

    注意：与之相邻但不属于异常的情形是"文件非空、但去掉标点空白后
    没有可比对内容"（例如整篇都是标点）。这属于合法输入，按约定
    重复率记 0.00，见 :mod:`plagcheck.engine`。
    """

    exit_code = 5


class OutputWriteError(PlagCheckError):
    """答案文件写不进去：目录不存在且无法创建、磁盘满、无写权限。

    场景：评测程序给出的答案路径位于一个不存在的目录下。
    设计目标：把"计算成功但结果丢了"这种最危险的失败明确暴露出来，
    让使用者一眼看到是输出环节而非算法环节出了问题。
    """

    exit_code = 6
