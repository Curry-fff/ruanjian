#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小学四则运算题目生成 / 批改程序的命令行入口（等价于作业里的 ``Myapp.exe``）。

用法::

    python Myapp.py -n 10 -r 10
    python Myapp.py -n 10000 -r 100
    python Myapp.py -e Exercises.txt -a Answers.txt

详见 ``README.md`` 与 ``python Myapp.py -h``。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arithmetic.cli import main  # noqa: E402  （必须先补好 sys.path 再导入本地包）

if __name__ == "__main__":
    sys.exit(main())
