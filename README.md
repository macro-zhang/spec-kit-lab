# spec-kit-lab

**把 GitHub [spec-kit](https://github.com/github/spec-kit) 的「确定性质量门禁」思路，拆成三块能直接跑起来的实验台。**

[![CI](https://github.com/macro-zhang/spec-kit-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/macro-zhang/spec-kit-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](#快速开始)
[![Node 20+](https://img.shields.io/badge/node-20%2B-339933?logo=nodedotjs&logoColor=white)](#快速开始)
[![依赖](https://img.shields.io/badge/依赖-3%20个%20pip%20包%20%2F%20Node%20零依赖-success)](#快速开始)

> 「什么叫做对了」不该由人来判断——它应该是一段会返回非 0 退出码的程序。

*Three runnable labs — TDD & contract testing, Git hooks, and shell exit codes — distilled from GitHub's [spec-kit](https://github.com/github/spec-kit). Every number in this README is re-verified by CI on every push.*

## 设计原则

这个仓库反复做同一件事：**把「判卷」从人的判断换成程序**。具体是三条：

1. **判卷的必须是程序。** 验收标准写成会执行、会返回非 0 退出码的测试或脚本，人和 Agent 都没有「差不多就行」的空间。
2. **红灯必须有效。** 「被测代码真的被拒绝了」（有效红灯）和「测试根本没跑起来」（假红灯：收集错误、退出码 2/4/5）是两件事，门禁必须分得清。
3. **契约是双向的、跨语言的。** 接口承诺冻结在 schema 与类型里，防漂移断言盯着「文档侧」和「代码侧」必须说法一致——Python 与 Node 两份实现共享同一份冻结 schema，改一边漏一边会被当场拦下。

第 3 条不是理论：module1 的 Node 防漂移测试真的拦下过一次只改了 Python 侧的契约变更（见下方「演进记录」）。

## 仓库结构

```text
spec-kit-lab/
├── .github/workflows/ci.yml        # CI：3 个 job，把「快速开始」里的命令原样跑一遍
├── docs/                           # 拆解笔记：讲清楚为什么这么设计
│   ├── 01-TDD与契约测试.md          #   有效红灯 vs 假红灯、契约三形态、防漂移
│   ├── 02-Git工作流与钩子.md         #   钩子能拦什么拦不住什么、门禁放在哪层
│   ├── 03-Shell与退出码.md          #   退出码是脚本唯一的对外表达
│   ├── 04-spec-kit架构拆解.md       #   命令链路、三镜像 parity、门禁三层
│   └── 05-知识点映射表.md            #   知识点 ↔ spec-kit 源码位置对照
└── lab/
    ├── module1-tdd/                # 实验台 1：TDD 与契约测试
    │   ├── src/calc/               #   被测对象：时长解析 core + 用户画像契约 contracts
    │   ├── tests/                  #   49 例 = 行为 21 + 契约 28（-m contract 可单独跑）
    │   ├── contracts/              #   冻结的 JSON Schema：Python / Node 共享的单一事实源
    │   ├── variants/               #   红 / 绿 / 重构三阶段的代码档案
    │   ├── run_red_green_refactor.py   # TDD 循环驱动器，自带自检：非有效红灯自己先非 0 退出
    │   └── node/                   #   零依赖 node:test 镜像：51 例（duration 20 + contract 31）
    ├── module2-git/                # 实验台 2：Git 工作流与钩子（75 例）
    │   ├── hooks/                  #   pre-commit / prepare-commit-msg 双平台包装
    │   ├── scripts/                #   质量门禁脚本：改实现没动测试 → 拦
    │   └── tests/                  #   钩子矩阵：哪些操作触发哪个钩子、非 0 如何拦下提交
    └── module3-shell/              # 实验台 3：Shell 与退出码（4 个讲义式脚本）
        ├── 01_exit_codes.py        #   退出码 0/1/2/4/5 的语义；子进程失败不会自动传染
        ├── 02_pipeline.py          #   管道与 pipefail：$? 只属于最后一个命令
        ├── 03_filesystem.py        #   Windows / POSIX 的路径与编码差异
        └── 04_subprocess.py        #   returncode、check=True、为什么不要 shell=True 拼输入
```

## 快速开始

依赖：Python 3.11+，三个包 `pytest`、`pydantic`、`jsonschema`；Node 20+（可选，只影响 `node/` 子目录，零第三方依赖）。

```bash
pip install pytest pydantic jsonschema
```

**实验台 1 · TDD 与契约测试（Python）**

```bash
cd lab/module1-tdd
python -m pytest -q                 # 49 passed（行为 21 + 契约 28）
python -m pytest -q -m contract     # 28 passed, 21 deselected —— 只跑契约
python run_red_green_refactor.py    # Red→Green→Refactor 实跑 + 驱动器自检
```

**实验台 1 · Node 镜像（零依赖）**

```bash
cd lab/module1-tdd/node
npm test                            # duration 20 例 + contract 31 例
npm run rgr                         # SELF-CHECK PASSED
```

**实验台 2 · Git 工作流与钩子**

```bash
cd lab/module2-git
python -m pytest -q                 # 75 passed（平台相关用例在缺工具的机器上自动 skip）
```

**实验台 3 · Shell 与退出码**（讲义式脚本，逐个运行。未纳入 CI——平台对照本身就是它的教学内容，详见 `lab/module3-shell/README.md`）

```bash
cd lab/module3-shell
python 01_exit_codes.py
python 02_pipeline.py
python 03_filesystem.py
python 04_subprocess.py
```

## CI：README 里的数字不是写的

[`ci.yml`](.github/workflows/ci.yml) 在每次 push 与 PR 时跑 3 个 job，判定只有一个——退出码：

| Job | 内容 |
|---|---|
| module1 · Python | 49 例 + TDD 驱动器自检 |
| module1 · Node | 51 例 + RGR 驱动器自检 |
| module2 · Git | 75 例（ubuntu，预配置 git 测试身份） |

没有 `continue-on-error`、没有 `|| true`——那等于把门禁拆了再挂一块绿色的牌子（`docs/01` §3.1）。

## 演进记录（摘）

- **建仓**：三块实验台 + 五篇拆解笔记。
- **上架前工程化**：绝对路径脱敏（46 处 → 0）、`.gitattributes` 统一 LF、MIT 许可。
- **需求变更演练**：用户画像新增必填 `locale`——schema、Pydantic、双侧测试同步，先红 5 后绿 49，全程 TDD。
- **跨语言漂移被拦**：上述变更只改了 Python 侧，Node 侧防漂移测试当场报红（required 集合差一个 `locale`）——随后 Node 同步修复，并上线 CI 把这件事固化成每次 push 都会跑的门禁。

## 拆解笔记

实验台负责「能跑」，`docs/` 负责「讲清楚为什么这么设计」：

| 文件 | 内容 |
|---|---|
| [`docs/01-TDD与契约测试.md`](docs/01-TDD与契约测试.md) | 有效红灯 vs 假红灯的判据、契约的三种形态与「冻结后防漂移」 |
| [`docs/02-Git工作流与钩子.md`](docs/02-Git工作流与钩子.md) | 钩子能拦什么、拦不住什么，门禁该放在哪一层 |
| [`docs/03-Shell与退出码.md`](docs/03-Shell与退出码.md) | 退出码是脚本唯一的对外表达，以及 Windows/POSIX 的差异 |
| [`docs/04-spec-kit架构拆解.md`](docs/04-spec-kit架构拆解.md) | spec-kit 的命令链路、三镜像 parity 测试、门禁三层 |
| [`docs/05-知识点映射表.md`](docs/05-知识点映射表.md) | 每个知识点 ↔ spec-kit 源码位置的对照表 |

## 关于文中的 `文件:行号`

`docs/04`、`docs/05` 里的每条 `路径:行号` 都指向 **[github/spec-kit](https://github.com/github/spec-kit) 的 `0443760`（2026-10-09）完整克隆**，放在本仓库同级目录 `spec-kit/`（不随本仓库分发）。上游 `main` 仍在演进，行号会漂移——要逐条核对，先检出那个提交：

```bash
git clone https://github.com/github/spec-kit.git ../spec-kit
git -C ../spec-kit checkout 0443760
```

（完整克隆再检出，比浅克隆加 `--depth` 稳——浅仓库里目标提交可能根本不存在。）

## Windows 用户

本仓库的脚本会把 stdout/stderr 先 reconfigure 成 UTF-8。这不是装饰——GBK 控制台遇到中文输出会直接 `UnicodeEncodeError` 把整份报告从中间截断，这个坑真实踩过，修法在 `run_red_green_refactor.py` 的 `_force_utf8()`。

## 许可

[MIT](LICENSE) © 2026 张宏博
