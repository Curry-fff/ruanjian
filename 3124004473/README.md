# 论文查重程序

> 学号：3124004473　课程：软件工程　作业：个人项目 —— 论文查重

给定一篇论文原文和一份在其基础上经过**增、删、改**的抄袭版论文，
程序计算两者的重复率，并把结果（精确到小数点后两位的浮点数）
写入答案文件。

* 语言：**Python 3**，入口文件 `main.py`
* 依赖：**零第三方运行时依赖**，只用标准库
* 单元测试：**212 个**，行覆盖率 **100%**
* 代码质量：`pylint` **10.00/10**，`flake8` **0 告警**
* 真实语料单次比对耗时：**0.022 秒**（时限 5 秒）

---

## 一、快速开始

```bash
python main.py <原文文件> <抄袭版论文文件> <答案文件>
```

例如：

```bash
python main.py C:\tests\orig.txt C:\tests\orig_add.txt C:\tests\ans.txt
```

运行后 `C:\tests\ans.txt` 中会写入类似 `0.79` 的内容。

三个参数都是文件路径，以空格分隔，路径中不能含空格。程序**只**会读写
这三个文件，不会创建任何临时文件、缓存或日志，也不会访问网络。

### 可选参数

| 参数 | 作用 |
| --- | --- |
| `-v` / `--verbose` | 把各分项得分、字符数与耗时打印到**标准错误**（标准输出在任何情况下都保持安静） |
| `-h` / `--help` | 显示用法 |

```bash
python main.py orig.txt orig_add.txt ans.txt --verbose
```

```
重复率: 0.79
原文归一化字符数: 8493
抄袭版归一化字符数: 10256
顺序敏感信号已启用: 是
耗时: 0.022 秒
分项得分:
  bigram_cosine      得分 0.8966  权重 0.10
  bigram_coverage    得分 0.6594  权重 0.25
  sequence_ratio     得分 0.9060  权重 0.30
  trigram_coverage   得分 0.5235  权重 0.10
  unigram_coverage   得分 0.8281  权重 0.25
```

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 2 | 命令行参数错误（数量不对 / 路径为空字符串） |
| 3 | 输入路径不存在或不是普通文件 |
| 4 | 输入文件读取失败（IO 错误 / 文件过大 / 内存不足） |
| 5 | 输入文件为空（0 字节） |
| 6 | 答案文件写入失败 |

任何异常都会变成"带诊断信息的退出码"，程序不会抛 traceback 崩溃退出。

---

## 二、算法简介

### 字符 n-gram + 多信号融合

程序先把原文与抄袭版做**归一化**（NFKC 兼容分解、丢弃空白与标点、
大小写折叠），再切成字符 n-gram 并统计词频，最后计算五路信号加权融合：

| 信号 | 权重 | 捕捉什么 |
| --- | ---: | --- |
| `sequence_ratio`：`2·LCS/(len_a+len_b)` | 0.30 | 顺序敏感，对增删改都稳定 |
| `unigram_coverage`：`Σmin(tf)/Σtf`（1-gram） | 0.25 | 字符级内容保留率，对局部乱序免疫 |
| `bigram_coverage`（2-gram） | 0.25 | 局部指纹，改一个字只破坏 2 个窗口 |
| `trigram_coverage`（3-gram） | 0.10 | 对"连续照抄"极敏感 |
| `bigram_cosine` | 0.10 | 篇幅均衡，避免抄袭版更长时分数虚高 |

不用中文分词库，是为了**零依赖**（评测环境不一定能联网装包）且对
"改写"更稳健。权重不是拍脑袋定的，而是用
`scripts/calibrate.py` 在带标注的语料集上做实验选出的
（平均绝对误差 0.055）。

### 在真实语料上的表现

课程下发的语料 `orig.txt`（余华《活着》前言与第一章，8,493 个有效字符）
与 `orig_add.txt`（在其上做字符级随机插入，净增 20.8%）：

| 信号 | 得分 |
| --- | ---: |
| `unigram_coverage` | **0.828** |
| `sequence_ratio` | 0.906 |
| `bigram_coverage` | 0.659 |
| `trigram_coverage` | 0.524 |
| `bigram_cosine` | 0.897 |
| **融合重复率** | **0.79** |

语料命名中的 "0.8" 与算法给出的 **0.79** 高度吻合，这是准确度最有力的
一条外部证据。详细设计与算法取舍见 [`docs/design.md`](docs/design.md)。

---

## 三、运行测试

```bash
python -m pytest tests -q          # 212 个用例
python scripts/run_coverage.py     # 覆盖率报告 → docs/coverage/coverage.txt
```

测试与覆盖率都不需要安装任何第三方包（覆盖率用标准库 `trace`）。

开发期工具（可选，不参与评测运行）：

```bash
python scripts/calibrate.py     # 权重标定实验
python scripts/benchmark.py     # 分阶段性能基准 + 对比图
python scripts/profile_run.py   # cProfile 性能分析 + 火焰图
```

---

## 四、目录结构

```
3124004473/
├── main.py                    程序入口（作业要求的文件名）
├── requirements.txt           运行时依赖声明（零第三方依赖）
├── pylintrc                   代码质量分析配置（每条 disable 都写了理由）
├── plagcheck/                 算法核心包
│   ├── exceptions.py          异常体系（五类 + 基类，各带退出码）
│   ├── textio.py              文件读写（编码自适应、答案格式化）
│   ├── normalize.py           文本归一化
│   ├── tokenize.py            字符 n-gram 词频统计
│   ├── similarity.py          相似度度量（覆盖率 / 余弦 / Jaccard / 位并行 LCS）
│   ├── engine.py              查重引擎（多信号加权融合）
│   └── cli.py                 命令行解析与退出码映射
├── tests/                     212 个单元测试 + 真实语料夹具
├── scripts/                   开发期工具（标定 / 基准 / 覆盖率 / 性能分析）
└── docs/
    ├── PSP.md                 PSP 表格（预估 vs 实际）
    ├── blog.md                博客正文
    ├── design.md              设计文档
    ├── coverage/              覆盖率报告
    └── profile/               性能分析与基准产物
```

---

## 五、性能

真实语料（10,511 / 12,274 字符）单次比对的分阶段耗时：

| 阶段 | 耗时 | 占比 |
| --- | ---: | ---: |
| 顺序相似度 `sequence_ratio` | 0.0189 s | 50.4% |
| n-gram 词频统计 | 0.0102 s | 27.2% |
| 归一化 | 0.0047 s | 12.5% |
| 覆盖率与余弦 | 0.0037 s | 9.9% |
| **端到端** | **0.022 s** | |

核心优化：把顺序信号从 `difflib.SequenceMatcher` 换成
**位并行 LCS**（Hyyrö 2004），在真实语料上**提速 23.7 倍**
（0.2568 s → 0.0109 s），且匹配字符数逐位相同（M = L = 8493）。

`difflib` 在输入变长时会急剧劣化——3.4 万字符需要 8.46 秒，已经足以
突破 5 秒时限；换成位并行实现后只需 0.228 秒。因此这次替换不只是优化，
更是时限安全的保证。性能分析过程与图表见
[`docs/profile/`](docs/profile/)。

---

## 六、文档

| 文档 | 内容 |
| --- | --- |
| [`docs/design.md`](docs/design.md) | 模块划分、接口设计、算法原理、异常设计、测试设计 |
| [`docs/PSP.md`](docs/PSP.md) | PSP 表格（预估 vs 实际）与估时偏差分析 |
| [`docs/blog.md`](docs/blog.md) | 博客正文（作业提交用） |
| [`docs/coverage/coverage.txt`](docs/coverage/coverage.txt) | 行覆盖率报告 |
| [`docs/profile/benchmark.txt`](docs/profile/benchmark.txt) | 分阶段性能基准 |
| [`docs/profile/profile_report_1x.txt`](docs/profile/profile_report_1x.txt) | cProfile 分析报告 |

## 七、环境

* Python ≥ 3.9（已在 Python 3.12.4 / Windows 10 上验证）
* 无需安装任何第三方包
