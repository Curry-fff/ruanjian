# -*- coding: utf-8 -*-
"""文件读写层单元测试。

测试函数：:func:`plagcheck.textio.read_text_file`、
:func:`plagcheck.textio.decode_bytes`、:func:`plagcheck.textio.format_answer`、
:func:`plagcheck.textio.write_answer_file`。

构造测试数据的思路：这一层是"程序与磁盘的唯一通道"，也是最容易被
评测环境搞垮的一层，所以按**故障模式**而不是按代码分支来设计用例：
编码不认识、文件不存在、传进来的是目录、文件是空的、文件大到会
爆内存、答案目录不存在、答案路径是目录……每一条都对应一类真实
会遇到的评测环境问题。
"""

from __future__ import annotations

import os

import pytest

from plagcheck import textio
from plagcheck.exceptions import (
    EmptyDocumentError,
    InputPathError,
    InputReadError,
    OutputWriteError,
)
from plagcheck.textio import (
    decode_bytes,
    format_answer,
    read_text_file,
    write_answer_file,
)

CHINESE_SENTENCE = "今天是星期天，天气晴，今天晚上我要去看电影。"


class TestReadTextFileEncodings:
    """编码自适应：评测语料可能是任意一种常见中文编码。"""

    def test_reads_utf8(self, write_file):
        """标准 UTF-8。"""
        path = write_file(CHINESE_SENTENCE, encoding="utf-8")
        assert read_text_file(path) == CHINESE_SENTENCE

    def test_reads_utf8_with_bom(self, write_file):
        """带 BOM 的 UTF-8：BOM 必须被吃掉，不能混进正文。"""
        path = write_file(CHINESE_SENTENCE, encoding="utf-8-sig")
        text = read_text_file(path)
        assert text == CHINESE_SENTENCE
        assert not text.startswith("\ufeff")

    def test_reads_gbk(self, write_file):
        """GBK 是中文 Windows 上最常见的默认编码。"""
        path = write_file(CHINESE_SENTENCE, encoding="gbk")
        assert read_text_file(path) == CHINESE_SENTENCE

    def test_reads_gb18030(self, write_file):
        """GB18030 是 GBK 的超集，必须同样支持。"""
        path = write_file(CHINESE_SENTENCE, encoding="gb18030")
        assert read_text_file(path) == CHINESE_SENTENCE

    def test_reads_utf16_with_bom(self, write_file):
        """带 BOM 的 UTF-16（记事本"Unicode"另存为的产物）。"""
        path = write_file(CHINESE_SENTENCE, encoding="utf-16")
        assert read_text_file(path) == CHINESE_SENTENCE

    def test_ascii_only_file(self, write_file):
        """纯 ASCII 内容（例如英文论文）。"""
        path = write_file("The quick brown fox.", encoding="ascii")
        assert read_text_file(path) == "The quick brown fox."

    def test_preserves_newlines_exactly(self, write_file):
        """本层不做行尾统一；换行交给归一化层处理。"""
        payload = "第一行\n第二行\r\n第三行"
        path = write_file(payload, encoding="utf-8")
        assert read_text_file(path) == payload

    def test_whitespace_only_file_is_not_treated_as_empty(self, write_file):
        """只有换行的文件不算"空文件"，它应当正常读出，由归一化层处理。"""
        path = write_file("\n", encoding="utf-8")
        assert read_text_file(path) == "\n"


class TestDecodeBytesFallbacks:
    """解码兜底路径：任何字节串都不能让程序抛异常。"""

    def test_bom_is_stripped(self):
        """UTF-8 BOM 必须被吃掉，不能作为一个字符混进正文。"""
        assert decode_bytes(b"\xef\xbb\xbfabc") == "abc"

    def test_utf16_bom_is_honoured(self):
        """带 BOM 的 UTF-16 要按 UTF-16 解码，而不是当成本地编码硬解。"""
        assert decode_bytes("汉字".encode("utf-16")) == "汉字"

    def test_truncated_utf16_bom_falls_back_instead_of_raising(self):
        """以 ``FF FE`` 开头但长度是奇数的文件不是合法 UTF-16。

        这条用例专门防止"BOM 分支直接 decode 并抛 UnicodeDecodeError"
        这种写法——那会让程序在评测中异常退出。
        """
        assert isinstance(decode_bytes(b"\xff\xfeabc"), str)

    def test_garbage_bytes_never_raise(self):
        """任意字节序列都必须返回字符串。"""
        for payload in (b"\xff\xfe\x00", b"\x80\x81\x82", bytes(range(256))):
            assert isinstance(decode_bytes(payload), str)


class TestReadTextFileFailures:
    """读取失败的各种场景。"""

    def test_missing_file_raises_input_path_error(self, tmp_path):
        """路径不存在 → InputPathError（退出码 3）。"""
        missing = str(tmp_path / "not_here.txt")
        with pytest.raises(InputPathError) as excinfo:
            read_text_file(missing)
        assert missing in excinfo.value.message
        assert excinfo.value.exit_code == 3

    def test_directory_raises_input_path_error(self, tmp_path):
        """把目录当文件传进来 → InputPathError，而不是 IsADirectoryError。"""
        with pytest.raises(InputPathError) as excinfo:
            read_text_file(str(tmp_path))
        assert "不是普通文件" in excinfo.value.message

    def test_empty_file_raises_empty_document_error(self, write_file):
        """0 字节文件 → EmptyDocumentError（退出码 5）。"""
        path = write_file("", encoding="utf-8")
        with pytest.raises(EmptyDocumentError) as excinfo:
            read_text_file(path)
        assert excinfo.value.exit_code == 5

    def test_oversized_file_raises_input_read_error(self, write_file, monkeypatch):
        """超过内存上限保护阈值 → InputReadError（退出码 4）。

        通过把上限改小来构造"超大文件"，避免真的写一个 500 MB 的文件。
        """
        path = write_file("x" * 4096, encoding="utf-8")
        monkeypatch.setattr(textio, "MAX_INPUT_BYTES", 128)
        with pytest.raises(InputReadError) as excinfo:
            read_text_file(path)
        assert excinfo.value.exit_code == 4
        assert "过大" in excinfo.value.message

    def test_unreadable_file_raises_input_read_error(self, write_file, monkeypatch):
        """读盘失败（这里是权限被拒）必须被翻译成 InputReadError。

        直接打桩 ``open`` 来模拟极端 IO 故障，比在 Windows 上折腾
        ACL 更稳定，也更能精确命中目标分支。
        """
        path = write_file("内容", encoding="utf-8")
        real_open = open

        def failing_open(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr("builtins.open", failing_open)
        with pytest.raises(InputReadError) as excinfo:
            read_text_file(path)
        monkeypatch.setattr("builtins.open", real_open)
        assert excinfo.value.exit_code == 4

    def test_size_query_failure_raises_input_read_error(self, write_file, monkeypatch):
        """``os.path.getsize`` 失败（例如统计信息拿不到）也要被翻译。

        场景：文件在 ``exists()`` 与 ``getsize()`` 之间被删除，或网络盘
        掉线。底层会抛 ``OSError``，绝不能让它以原始形态冒到顶层。
        """
        path = write_file("内容", encoding="utf-8")

        def failing_getsize(_path):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(os.path, "getsize", failing_getsize)
        with pytest.raises(InputReadError) as excinfo:
            read_text_file(path)
        assert excinfo.value.exit_code == 4
        assert "无法获取文件大小" in excinfo.value.message

    def test_out_of_memory_while_reading_raises_input_read_error(self, write_file, monkeypatch):
        """读盘时内存不足 → InputReadError，而不是让 MemoryError 逃逸。

        评测环境有 2048 MB 内存上限，这条路径必须存在且被验证。
        """
        path = write_file("内容", encoding="utf-8")

        def failing_open(*args, **kwargs):
            raise MemoryError("模拟内存耗尽")

        monkeypatch.setattr("builtins.open", failing_open)
        with pytest.raises(InputReadError) as excinfo:
            read_text_file(path)
        assert excinfo.value.exit_code == 4
        assert "内存不足" in excinfo.value.message


class TestFormatAnswer:
    """答案格式化：题目要求精确到小数点后两位。"""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, "0.00"),
            (1.0, "1.00"),
            (0.6514, "0.65"),
            (0.005, "0.01"),
            (0.999, "1.00"),
            (0.12345, "0.12"),
            (0.125, "0.12"),
        ],
    )
    def test_two_decimal_places(self, value, expected):
        """各种取值都必须格式化到恰好两位小数。"""
        assert format_answer(value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            (-0.5, "0.00"),
            (-1e9, "0.00"),
            (1.5, "1.00"),
            (42.0, "1.00"),
        ],
    )
    def test_out_of_range_values_are_clamped(self, value, expected):
        """越界值被夹紧，绝不会输出 "-0.00" 或 "1.00" 以外的怪值。"""
        assert format_answer(value) == expected

    def test_negative_zero_never_appears(self):
        """负零是浮点误差的经典产物，必须显示成 0.00。"""
        assert format_answer(-0.0) == "0.00"

    def test_result_is_always_parseable_as_float(self):
        """任何输入产生的输出都要能被 float() 解析。"""
        for value in (0.0, 0.33, 0.6666666666, 1.0):
            assert isinstance(float(format_answer(value)), float)


class TestWriteAnswerFile:
    """答案写出。"""

    def test_writes_two_decimals_without_trailing_newline(self, answer_path):
        """内容必须是纯 "0.65"，不带换行——这样按字符串严格比较也不出错。"""
        written = write_answer_file(answer_path, 0.6514)
        assert written == "0.65"
        with open(answer_path, "rb") as handle:
            assert handle.read() == b"0.65"

    def test_creates_missing_parent_directory(self, tmp_path):
        """答案目录不存在时自动创建，避免"算完了却写不出去"。"""
        target = tmp_path / "deep" / "nested" / "ans.txt"
        write_answer_file(str(target), 0.5)
        assert target.read_text(encoding="utf-8") == "0.50"

    def test_overwrites_existing_answer(self, answer_path):
        """答案文件已存在（含上一次运行留下的长内容）时必须被覆盖。"""
        with open(answer_path, "w", encoding="utf-8") as handle:
            handle.write("0.99 旧内容 旧内容 旧内容")
        write_answer_file(answer_path, 0.25)
        with open(answer_path, encoding="utf-8") as handle:
            assert handle.read() == "0.25"

    def test_directory_as_target_raises_output_write_error(self, tmp_path):
        """答案路径是个已存在的目录 → OutputWriteError（退出码 6）。

        不依赖打桩：Windows 抛 ``PermissionError``、Linux 抛
        ``IsADirectoryError``，两者都是 ``OSError``，必须被统一翻译。
        """
        with pytest.raises(OutputWriteError) as excinfo:
            write_answer_file(str(tmp_path), 0.5)
        assert excinfo.value.exit_code == 6

    def test_unwritable_parent_raises_output_write_error(self, tmp_path, monkeypatch):
        """父目录无法创建 → OutputWriteError。"""
        blocked = tmp_path / "blocked"

        def failing_makedirs(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(os, "makedirs", failing_makedirs)
        with pytest.raises(OutputWriteError):
            write_answer_file(str(blocked / "ans.txt"), 0.5)

    def test_uses_utf8_and_lf_newline_convention(self, answer_path):
        """写入结果是纯 ASCII，任何编码都能正确还原。"""
        write_answer_file(answer_path, 0.07)
        with open(answer_path, "rb") as handle:
            assert handle.read().decode("ascii") == "0.07"
