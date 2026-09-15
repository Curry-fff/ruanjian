# -*- coding: utf-8 -*-
"""命令行入口单元测试。

测试函数：:func:`plagcheck.cli.main` 与 :func:`plagcheck.cli.build_parser`。

构造测试数据的思路：命令行入口是评测方**唯一**会碰到的接口，因此这里
全部采用"黑盒 + 真实文件"的方式：真的建立两个语料文件、真的调用 main()、
真的把答案文件读回来比对。断言集中在三件事上：

1. **契约**——退出码与作业要求一致，答案文件必须是两位小数；
2. **安静**——标准输出默认不能有任何内容，避免干扰评测方的输出捕获；
3. **不崩**——穷举各种坏参数，程序必须"带诊断信息、按约定码退出"，
   而不是抛 traceback 或挂死（这正对应作业的扣分项"发生异常退出"）。
"""

from __future__ import annotations

import os

import pytest

from plagcheck import PlagiarismChecker
from plagcheck.cli import build_parser, main

#: 作业题目里给出的样例原文与抄袭版（与 conftest 中的常量保持一致）。
SAMPLE_ORIGINAL = "今天是星期天，天气晴，今天晚上我要去看电影。"
SAMPLE_COPY = "今天是周天，天气晴朗，我晚上要去看电影。"


class TestSuccessfulRun:
    """正常路径。"""

    def test_three_arguments_produce_answer_file(self, write_file, answer_path):
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="orig_add.txt")

        exit_code = main([original, copy, answer_path])

        assert exit_code == 0
        with open(answer_path, encoding="utf-8") as handle:
            assert handle.read() == "0.71"

    def test_answer_matches_library_result(self, write_file, answer_path, data_dir):
        """命令行输出必须与直接调用引擎的结果完全一致。"""
        original = os.path.join(data_dir, "orig.txt")
        copy = os.path.join(data_dir, "orig_add.txt")

        assert main([original, copy, answer_path]) == 0
        expected = PlagiarismChecker().compare_files(original, copy).duplication
        with open(answer_path, encoding="utf-8") as handle:
            assert handle.read() == "%.2f" % expected

    def test_identical_files_give_one(self, write_file, answer_path):
        """原文与自己比对必须是 1.00。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        assert main([original, original, answer_path]) == 0
        with open(answer_path, encoding="utf-8") as handle:
            assert handle.read() == "1.00"

    def test_gbk_input_files_work_end_to_end(self, write_file, answer_path):
        """评测语料可能是 GBK，整条链路都必须能跑通。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt", encoding="gbk")
        copy = write_file(SAMPLE_COPY, name="orig_add.txt", encoding="gbk")
        assert main([original, copy, answer_path]) == 0

    def test_answer_file_is_created_in_a_new_directory(self, write_file, tmp_path):
        """答案目录不存在时也要能写出结果。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="orig_add.txt")
        target = os.path.join(str(tmp_path), "nested", "ans.txt")

        assert main([original, copy, target]) == 0
        assert os.path.isfile(target)

    def test_absolute_and_relative_paths_both_work(self, write_file, monkeypatch, tmp_path):
        """题目要求绝对路径，但相对路径也应当能正常工作。"""
        write_file(SAMPLE_ORIGINAL, name="orig.txt")
        write_file(SAMPLE_COPY, name="copy.txt")
        monkeypatch.chdir(tmp_path)

        assert main(["orig.txt", "copy.txt", "ans.txt"]) == 0
        assert os.path.isfile(os.path.join(str(tmp_path), "ans.txt"))


class TestOutputDiscipline:
    """输出纪律：标准输出必须保持安静。"""

    def test_stdout_is_silent_on_success(self, write_file, answer_path, capsys):
        """结果只进答案文件；标准输出被占用可能干扰评测方。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="copy.txt")

        assert main([original, copy, answer_path]) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_verbose_writes_details_to_stderr_only(self, write_file, answer_path, capsys):
        """--verbose 的诊断信息走标准错误，不能污染标准输出。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="copy.txt")

        assert main([original, copy, answer_path, "--verbose"]) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "重复率" in captured.err
        assert "bigram_coverage" in captured.err

    def test_verbose_short_flag_is_equivalent(self, write_file, answer_path, capsys):
        """-v 与 --verbose 等价。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="copy.txt")
        assert main([original, copy, answer_path, "-v"]) == 0
        assert "重复率" in capsys.readouterr().err


class TestArgumentErrors:
    """参数错误：必须在碰磁盘之前就被拦住，退出码 2。"""

    def test_no_arguments_exits_with_code_two(self, capsys):
        """一个参数都不给 → argparse 用法错误。"""
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2
        assert "usage" in capsys.readouterr().err.lower()

    def test_too_few_arguments_exits_with_code_two(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["only-one.txt"])
        assert excinfo.value.code == 2

    def test_too_many_arguments_exits_with_code_two(self, capsys):
        """多给参数同样属于用法错误，不能静默忽略。"""
        with pytest.raises(SystemExit) as excinfo:
            main(["a.txt", "b.txt", "c.txt", "d.txt"])
        assert excinfo.value.code == 2

    def test_help_exits_with_code_zero(self, capsys):
        """--help 是正常退出，且要把用法说明打印出来。"""
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])
        assert excinfo.value.code == 0
        assert "原文文件" in capsys.readouterr().out

    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_empty_string_argument_returns_code_two(self, write_file, answer_path, position, capsys):
        """空字符串参数 → ArgumentError（退出码 2）。

        argparse 只检查"参数有没有给"，不检查内容；如果不拦，程序会一路
        走到 ``os.path.abspath("")``，报错信息指向当前工作目录，极难排查。
        """
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="copy.txt")
        argv = [original, copy, answer_path]
        argv[position] = ""

        assert main(argv) == 2
        assert "不能为空字符串" in capsys.readouterr().err


class TestInputFailures:
    """输入故障：必须是"受控退出"，而不是崩溃。"""

    def test_missing_original_returns_code_three(self, write_file, answer_path, capsys):
        copy = write_file(SAMPLE_COPY, name="copy.txt")
        assert main([os.path.join(os.path.dirname(copy), "missing.txt"), copy, answer_path]) == 3
        assert "不存在" in capsys.readouterr().err

    def test_missing_copy_returns_code_three(self, write_file, answer_path, capsys):
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        missing = os.path.join(os.path.dirname(original), "missing.txt")
        assert main([original, missing, answer_path]) == 3
        assert "不存在" in capsys.readouterr().err

    def test_directory_as_input_returns_code_three(self, write_file, answer_path, tmp_path, capsys):
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        assert main([original, str(tmp_path), answer_path]) == 3
        assert "不是普通文件" in capsys.readouterr().err

    def test_empty_input_file_returns_code_five(self, write_file, answer_path, capsys):
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        empty = write_file("", name="empty.txt")
        assert main([original, empty, answer_path]) == 5
        assert "为空" in capsys.readouterr().err

    def test_unwritable_answer_returns_code_six(self, write_file, tmp_path, capsys):
        """答案路径是目录 → 退出码 6，且错误信息指明是输出环节。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="copy.txt")
        assert main([original, copy, str(tmp_path)]) == 6
        assert "答案文件" in capsys.readouterr().err

    def test_no_traceback_ever_escapes(self, write_file, answer_path, tmp_path):
        """坏参数只能变成退出码，绝不能抛异常。"""
        original = write_file(SAMPLE_ORIGINAL, name="orig.txt")
        copy = write_file(SAMPLE_COPY, name="copy.txt")
        bad_cases = [
            ["", "", ""],
            [original, copy],
            [original, os.path.join(str(tmp_path), "nope.txt"), answer_path],
            [original, str(tmp_path), answer_path],
        ]
        for argv in bad_cases:
            try:
                exit_code = main(argv)
            except SystemExit as exc:  # argparse 的用法错误是系统退出，允许
                exit_code = exc.code
            assert isinstance(exit_code, int)
            assert exit_code != 0


class TestParserMetadata:
    """解析器自身的元信息。"""

    def test_program_name_matches_submission_requirement(self):
        """作业要求入口文件名为 main.py，帮助信息里必须体现。"""
        assert build_parser().prog == "main.py"

    def test_three_positional_arguments_map_to_expected_destinations(self):
        """三个位置参数必须按题目顺序落到原文 / 抄袭版 / 答案三个字段上。"""
        namespace = build_parser().parse_args(["o.txt", "c.txt", "a.txt"])
        assert namespace.original_path == "o.txt"
        assert namespace.copy_path == "c.txt"
        assert namespace.answer_path == "a.txt"
        assert namespace.verbose is False

    def test_help_text_documents_each_argument(self):
        """帮助信息用中文说明每个位置参数是什么，便于助教直接照抄命令。"""
        help_text = build_parser().format_help()
        for label in ("原文文件", "抄袭版论文文件", "答案文件"):
            assert label in help_text
        assert "main.py" in help_text
