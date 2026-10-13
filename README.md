# spec-kit-lab

把 [GitHub spec-kit](https://github.com/github/spec-kit) 里「用确定性代码守住质量门禁」的思路拆开，重做成三块**能直接跑起来**的实验台：TDD 与契约测试、Git 工作流与钩子、Shell 与退出码。

一句话主张：**「什么叫做对了」不该由人来判断——它应该是一段会返回非 0 退出码的程序。**

## 为什么做这个

spec-kit 是一个把「规范 → 计划 → 实现」流程化、并给 Agent 产出加上确定性门禁的工具项目。读它的源码时我发现，真正值得学的不是它的命令，而是它反复使用的一个模式：

> 把验收标准写成会执行、会返回退出码的程序，让人和 Agent 都没有「差不多就行」的空间。

于是我把这个模式拆成三个最小的、可运行的实验台——每个都只依赖一两个常见工具，但把「判卷」这件事做得足够硬。

## 三个实验台

| 目录 | 主题 | 能跑到什么 |
|---|---|---|
| [`lab/module1-tdd`](lab/module1-tdd/) | TDD 与契约测试 | `run_red_green_refactor.py` 把 Red → Green → Refactor 三个阶段**真的执行一遍并自检**：红灯必须是有效红灯，绿灯和重构都必须全绿，否则驱动器自己非 0 退出。含 8 正例 + 10 负例 + 非字符串的行为用例、Pydantic 与 JSON Schema 两侧的契约测试、防漂移断言，以及 Python / Node 双实现的等价性验证 |
| [`lab/module2-git`](lab/module2-git/) | Git 工作流与钩子 | pre-commit 钩子矩阵与钩子探针：哪些操作会触发哪个钩子、钩子返回非 0 时提交如何被拦下 |
| [`lab/module3-shell`](lab/module3-shell/) | Shell 与退出码 | 退出码语义（0 / 1 / 2 / 4 / 5 各自意味着什么）、管道与 `set -e` 的坑、跨平台脚本的编码陷阱 |

## 拆解笔记

实验台负责「能跑」，`docs/` 负责「讲清楚为什么这么设计」：

| 文件 | 内容 |
|---|---|
| [`docs/01-TDD与契约测试.md`](docs/01-TDD与契约测试.md) | 有效红灯 vs 假红灯的判据、契约的三种形态与「冻结后防漂移」 |
| [`docs/02-Git工作流与钩子.md`](docs/02-Git工作流与钩子.md) | 钩子能拦什么、拦不住什么，门禁该放在哪一层 |
| [`docs/03-Shell与退出码.md`](docs/03-Shell与退出码.md) | 退出码是脚本唯一的对外表达，以及 Windows/POSIX 的差异 |
| [`docs/04-spec-kit架构拆解.md`](docs/04-spec-kit架构拆解.md) | spec-kit 的命令链路、三镜像 parity 测试、门禁三层 |
| [`docs/05-知识点映射表.md`](docs/05-知识点映射表.md) | 每个知识点 ↔ spec-kit 源码位置的对照表 |

## 快速开始

```bash
# 第 1 块：全量用例
cd lab/module1-tdd
python -m pytest -q

# 第 1 块：把 TDD 循环实跑一遍（驱动器自带自检）
python run_red_green_refactor.py
```

依赖：Python 3.11+，`pytest`、`pydantic`、`jsonschema`。`lab/module1-tdd/node/` 那部分是**零依赖**的，用 Node 内置的 `node:test`，直接 `node run-rgr.mjs` 即可。

> **Windows 用户注意**：本仓库的脚本会把 stdout/stderr 先 reconfigure 成 UTF-8。这不是装饰——GBK 控制台遇到中文输出会直接 `UnicodeEncodeError` 把整份报告从中间截断，这个坑我真的踩过，修法写进了 `run_red_green_refactor.py` 的 `_force_utf8()`。

## 现状

- 三块实验台均已建成，用例与脚本全绿。
- 逐模块的实操讲解与扩写在持续进行中，README 与 `docs/` 会随进度更新。