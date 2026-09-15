# -*- coding: utf-8 -*-
"""测试语料夹具自身的测试。

测试对象不是程序，而是**提交进仓库的测试数据**。

写这个文件的起因是一次真实事故：`tests/data/sample_orig.txt` 与
`sample_orig_add.txt` 是早期用 PowerShell 的 ``Set-Content -Encoding utf8``
生成的，而该命令会写入 UTF-8 BOM。程序自己读取时不会有问题（``read_text_file``
会把 BOM 吃掉），但如果有人用普通的 ``encoding="utf-8"`` 去读夹具，
文本开头就会多出一个不可见的 ``\\ufeff``——把这份文本再写成 GBK 时会直接
抛 ``UnicodeEncodeError``。

夹具坏掉比程序坏掉更隐蔽：测试照样"通过"，因为它们比的是程序行为，而不是
数据本身。所以这里补一组针对数据文件的断言，把"夹具必须干净"这件事也纳入
回归防线。
"""

from __future__ import annotations

import os

import pytest

from plagcheck import PlagiarismChecker
from plagcheck.textio import read_text_file

#: UTF-8 BOM 的字节序列。
UTF8_BOM = b"\xef\xbb\xbf"

#: 夹具文件清单。
FIXTURE_FILES = (
    "orig.txt",
    "orig_add.txt",
    "sample_orig.txt",
    "sample_orig_add.txt",
)


@pytest.fixture(name="fixture_bytes")
def fixture_fixture_bytes(data_dir):
    """返回 ``{文件名: 原始字节}``。"""

    def _load():
        loaded = {}
        for name in FIXTURE_FILES:
            path = os.path.join(data_dir, name)
            assert os.path.isfile(path), f"缺少夹具文件：{name}"
            with open(path, "rb") as handle:
                loaded[name] = handle.read()
        return loaded

    return _load


class TestFixturesAreClean:
    """提交进仓库的语料必须是"干净"的，不能带 BOM 或空文件。"""

    def test_no_fixture_starts_with_bom(self, fixture_bytes):
        """任何夹具都不能以 UTF-8 BOM 开头。

        带 BOM 的文本用 ``utf-8``（而非 ``utf-8-sig``）读取时会多出一个
        不可见字符，后续转写为 GBK 等编码会直接失败。
        """
        offenders = [
            name for name, raw in fixture_bytes().items() if raw.startswith(UTF8_BOM)
        ]
        assert not offenders, f"以下夹具带 UTF-8 BOM，请另存为无 BOM：{offenders}"

    def test_no_fixture_is_empty(self, fixture_bytes):
        """夹具不能是 0 字节，否则会被程序判为非法输入。"""
        offenders = [name for name, raw in fixture_bytes().items() if not raw]
        assert offenders == []

    def test_all_fixtures_decode_as_utf8(self, fixture_bytes):
        """不带 BOM 的纯 UTF-8 解码也必须成功，证明夹具确实是 UTF-8。"""
        for name, raw in fixture_bytes().items():
            text = raw.decode("utf-8")
            assert text.strip(), f"{name} 解码后没有内容"

    def test_sample_fixtures_match_the_assignment_text(self, fixture_bytes):
        """小样例夹具必须与作业题目给出的样例逐字一致。"""
        assert fixture_bytes()["sample_orig.txt"].decode("utf-8").strip() == (
            "今天是星期天，天气晴，今天晚上我要去看电影。"
        )
        assert fixture_bytes()["sample_orig_add.txt"].decode("utf-8").strip() == (
            "今天是周天，天气晴朗，我晚上要去看电影。"
        )

    def test_corpus_fixtures_are_a_genuine_plagiarism_pair(self, data_dir):
        """真实语料的两份文件必须确实构成一对"抄袭样本"。

        不能断言"开头 30 字相同"——``orig_add.txt`` 是从第 9 个字左右就开始
        插入噪声的字符级变体，前缀必然对不齐。有意义的断言是：
        抄袭版更长（插入型），且引擎给出的重复率确实很高。
        """
        original = read_text_file(os.path.join(data_dir, "orig.txt"))
        copy = read_text_file(os.path.join(data_dir, "orig_add.txt"))

        assert len(copy) > len(original), "增版应当比原文更长"

        result = PlagiarismChecker().compare_texts(original, copy)
        assert result.duplication > 0.7, "这对语料应当能判出高重复率"


class TestFixturesThroughTheReader:
    """夹具经由程序自己的读取路径必须得到预期文本。"""

    def test_reader_strips_bom_even_if_present(self, tmp_path):
        """即便夹具将来又带上 BOM，``read_text_file`` 也必须能吃掉它。

        这一条是"双保险"：上面的用例防止夹具被污染，这一条保证即使
        污染发生了，程序本身也不会因此出错。
        """
        path = tmp_path / "bom.txt"
        path.write_bytes(UTF8_BOM + "今天是星期天".encode("utf-8"))
        assert read_text_file(str(path)) == "今天是星期天"

    def test_sample_pair_scores_as_documented(self, data_dir):
        """小样例夹具走完整流程，得分应当与测试常量一致（0.71）。"""
        result = PlagiarismChecker().compare_files(
            os.path.join(data_dir, "sample_orig.txt"),
            os.path.join(data_dir, "sample_orig_add.txt"),
        )
        assert result.duplication == pytest.approx(0.71, abs=0.02)
