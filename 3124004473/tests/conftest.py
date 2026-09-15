# -*- coding: utf-8 -*-
"""pytest 公共夹具。

作用一：把 ``3124004473`` 目录加入 ``sys.path``，让 ``import plagcheck``
在仓库里直接可用，不需要先 ``pip install``——评测方 clone 下来就能跑测试。

作用二：提供"临时语料文件"的构造夹具，让每个测试都能用一行代码
造出任意编码、任意内容的输入文件。
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import sys

import pytest

# 本文件位于 3124004473/tests/，其上一级才是包所在目录。
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

#: 测试临时目录的根，固定放在项目内而不是系统 TEMP。
#:
#: 原因有两条：
#:
#: 1. **可移植性**。pytest 内置的 ``tmp_path`` 会在系统临时目录下建立
#:    ``pytest-of-<user>``，并在会话收尾时枚举该目录做清理。在某些受限
#:    环境（企业策略、容器、受管控的沙箱）中该目录不可枚举，会在
#:    ``pytest_sessionfinish`` 阶段抛 ``PermissionError``，把一次全绿的
#:    测试跑成失败退出。
#: 2. **可清理**。临时产物全部收敛在项目内，``.gitignore`` 一行就能
#:    挡住，也不会在别人的系统盘上留下垃圾。
TEST_TEMP_ROOT = os.path.join(PACKAGE_ROOT, "_test_tmp")

_BAD_PATH_CHARS = re.compile(r"[^0-9A-Za-z_.\-]+")


@pytest.fixture(name="tmp_path")
def fixture_tmp_path(request) -> pathlib.Path:
    """项目内、按用例隔离的临时目录（覆盖 pytest 内置同名夹具）。

    每个用例拿到 ``_test_tmp/<用例名>``，进入前与退出后各清空一次，
    因此同一个用例重复运行也不会读到上一次的残留文件。
    """
    safe_name = _BAD_PATH_CHARS.sub("_", request.node.name)[:80]
    path = pathlib.Path(TEST_TEMP_ROOT) / safe_name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


#: 作业题目里给出的样例原文与抄袭版。
SAMPLE_ORIGINAL = "今天是星期天，天气晴，今天晚上我要去看电影。"
SAMPLE_COPY = "今天是周天，天气晴朗，我晚上要去看电影。"


@pytest.fixture(name="data_dir")
def fixture_data_dir() -> str:
    """返回随仓库一起提交的测试语料目录。"""
    return DATA_DIR


@pytest.fixture(name="write_file")
def fixture_write_file(tmp_path):
    """返回一个"把文本写成文件并返回其路径"的工厂函数。

    用法::

        def test_x(write_file):
            path = write_file("hello", name="a.txt", encoding="gbk")
    """

    def _write(text: str, name: str = "text.txt", encoding: str = "utf-8") -> str:
        target = tmp_path / name
        # newline="" 关闭行尾翻译，否则 Windows 上会把 "\n" 悄悄写成
        # "\r\n"，使"原样读取"这类断言失去意义。
        with open(target, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        return str(target)

    return _write


@pytest.fixture(name="write_bytes")
def fixture_write_bytes(tmp_path):
    """返回一个"把原始字节写成文件并返回其路径"的工厂函数。"""

    def _write(payload: bytes, name: str = "raw.bin") -> str:
        target = tmp_path / name
        target.write_bytes(payload)
        return str(target)

    return _write


@pytest.fixture(name="answer_path")
def fixture_answer_path(tmp_path) -> str:
    """返回一个尚未创建的答案文件路径。"""
    return str(tmp_path / "ans.txt")
