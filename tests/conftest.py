# -*- coding: utf-8 -*-
"""让 ``pytest`` 能从仓库根目录导入 ``arithmetic`` 包。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
