# 软件工程课程作业仓库

本仓库用于提交《软件工程》课程的个人项目作业，每份作业在根目录下以
**学号**为名建立独立文件夹。

## 作业列表

| 学号目录 | 作业 | 说明 |
| --- | --- | --- |
| [`3124004473/`](3124004473/) | 个人项目：论文查重 | 给定原文与经过增删改的抄袭版论文，计算重复率 |

## 论文查重项目

* **GitHub 仓库**：<https://github.com/Curry-fff/ruanjian>
* **博客地址**：<https://www.cnblogs.com/00Lyf/p/22980140>
* **程序入口**：`3124004473/main.py`
* **实现语言**：Python 3（零第三方运行时依赖）

### 运行方式

```bash
python main.py <原文文件> <抄袭版论文文件> <答案文件>
```

### 关键结果

| 指标 | 结果 |
| --- | --- |
| 单元测试 | 219 个，全部通过 |
| 行覆盖率 | 100%（321/321 行） |
| `pylint` | 10.00 / 10，零告警 |
| `flake8` | 0 告警 |
| 真实语料单次比对耗时 | 0.022 s（时限 5 s） |
| 真实语料重复率 | 0.79（语料命名标注为 0.8） |

详细内容见 [`3124004473/README.md`](3124004473/README.md) 与
[`3124004473/docs/`](3124004473/docs/)。

### 提交历史约定

按功能划分提交：每完成一个模块并编译（通过测试）后提交一次，
提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat(engine): 实现五路信号融合的查重引擎
test: 补齐 176 个单元测试与真实语料夹具
perf: 用位并行 LCS 替换 difflib，真实语料提速 23 倍
docs: 补充设计文档、PSP 表与博客初稿
```

## 本地开发

```bash
# 运行测试
python -m pytest tests -q

# 覆盖率报告
python scripts/run_coverage.py

# 代码质量
python -m pylint plagcheck main.py tests
python -m flake8 -j 1 --max-line-length=110 plagcheck tests scripts main.py
```
