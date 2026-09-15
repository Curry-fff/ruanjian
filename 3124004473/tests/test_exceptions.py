# -*- coding: utf-8 -*-
"""异常体系单元测试。

测试函数：:class:`plagcheck.exceptions.PlagCheckError` 及其五个子类。
构造测试数据的思路：异常是"契约"而不是"逻辑"，因此这里不构造业务
数据，而是逐条断言契约本身——退出码是否唯一且与设计文档一致、
消息是否原样保留、继承关系是否正确。这些断言一旦被破坏，命令行
入口的退出码约定就会失效，属于必须钉死的接口。
"""

from __future__ import annotations

import pytest

from plagcheck.exceptions import (
    ArgumentError,
    EmptyDocumentError,
    InputPathError,
    InputReadError,
    OutputWriteError,
    PlagCheckError,
)

ALL_EXCEPTION_TYPES = (
    ArgumentError,
    InputPathError,
    InputReadError,
    EmptyDocumentError,
    OutputWriteError,
)


def test_all_exceptions_derive_from_base():
    """每个自定义异常都必须继承基类，否则命令行入口的 except 会漏掉它。"""
    for exception_type in ALL_EXCEPTION_TYPES:
        assert issubclass(exception_type, PlagCheckError)


def test_exit_codes_match_design_document():
    """退出码必须与 docs/design.md 中的约定表逐一对齐。"""
    assert ArgumentError.exit_code == 2
    assert InputPathError.exit_code == 3
    assert InputReadError.exit_code == 4
    assert EmptyDocumentError.exit_code == 5
    assert OutputWriteError.exit_code == 6


def test_exit_codes_are_unique():
    """退出码必须互不相同，否则使用者无法从退出码区分故障类型。"""
    codes = [exception_type.exit_code for exception_type in ALL_EXCEPTION_TYPES]
    assert len(set(codes)) == len(codes)


def test_message_is_preserved_verbatim():
    """异常消息要被原样保留，且 message 属性与 str() 一致。"""
    error = InputPathError("输入文件不存在：C:\\tests\\missing.txt")
    assert error.message == "输入文件不存在：C:\\tests\\missing.txt"
    assert str(error) == "输入文件不存在：C:\\tests\\missing.txt"


def test_message_is_also_reachable_through_args():
    """同时兼容 ``except Exception as e: e.args[0]`` 的惯用写法。"""
    error = EmptyDocumentError("输入文件为空（0 字节）：C:\\tests\\empty.txt")
    assert error.args[0].startswith("输入文件为空")


@pytest.mark.parametrize("exception_type", ALL_EXCEPTION_TYPES)
def test_exception_can_be_raised_and_caught_as_base(exception_type):
    """任何一种异常都必须能被 ``except PlagCheckError`` 捕获。"""
    with pytest.raises(PlagCheckError) as excinfo:
        raise exception_type("测试消息")
    assert excinfo.value.exit_code == exception_type.exit_code
