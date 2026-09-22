# -*- coding: utf-8 -*-
"""测试用的小工具。

所有测试用的临时目录统一建在仓库内的 ``.testtmp/`` 下：
既方便用完即删，也不会污染系统临时目录；``.gitignore`` 已经把它排除。
"""

from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
_TEMP_ROOT = ROOT / ".testtmp"


@contextmanager
def workspace_tempdir() -> Iterator[Path]:
    """产出一个用完即删的临时目录（清理失败也不让测试挂掉）。"""
    _TEMP_ROOT.mkdir(exist_ok=True)
    path = _TEMP_ROOT / uuid.uuid4().hex[:12]
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
