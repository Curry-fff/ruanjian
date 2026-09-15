#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文查重程序入口。

用法::

    python main.py <原文文件> <抄袭版论文文件> <答案文件>

三个参数都是文件路径，以空格分隔，路径中不能含空格（作业要求）。
答案文件中写入一个精确到小数点后两位的浮点数，即重复率。

本文件只负责"启动"，全部逻辑位于同目录下的 ``plagcheck`` 包中，
这样算法核心才能被单元测试直接导入、单独测试。
"""

import sys

from plagcheck.cli import main

if __name__ == "__main__":
    sys.exit(main())
