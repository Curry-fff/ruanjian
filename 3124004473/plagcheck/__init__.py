# -*- coding: utf-8 -*-
"""plagcheck —— 论文查重核心库。

对外稳定接口只暴露下面这些名字，内部模块的私有实现可以自由重构。

典型用法::

    from plagcheck import PlagiarismChecker, write_answer_file

    checker = PlagiarismChecker()
    result = checker.compare_files("orig.txt", "orig_add.txt")
    write_answer_file("ans.txt", result.duplication)
"""

from .engine import (
    MAX_SEQUENCE_CHARS,
    DuplicationResult,
    PlagiarismChecker,
    SimilarityWeights,
)
from .exceptions import (
    ArgumentError,
    EmptyDocumentError,
    InputPathError,
    InputReadError,
    OutputWriteError,
    PlagCheckError,
)
from .normalize import normalize
from .similarity import cosine, coverage, jaccard, sequence_ratio
from .textio import format_answer, read_text_file, write_answer_file
from .tokenize import ngram_frequencies, total_frequency

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # 异常体系
    "PlagCheckError",
    "ArgumentError",
    "InputPathError",
    "InputReadError",
    "EmptyDocumentError",
    "OutputWriteError",
    # 引擎
    "PlagiarismChecker",
    "DuplicationResult",
    "SimilarityWeights",
    "MAX_SEQUENCE_CHARS",
    # 文本处理
    "normalize",
    "ngram_frequencies",
    "total_frequency",
    # 度量
    "coverage",
    "cosine",
    "jaccard",
    "sequence_ratio",
    # 文件读写
    "read_text_file",
    "write_answer_file",
    "format_answer",
]
