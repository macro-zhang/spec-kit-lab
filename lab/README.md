# lab/ —— spec-kit 拆解配套实验台

> 每一个模块都是"概念 → 可运行实验 → 自检清单"的闭环。
> 先读各模块自己的 `README.md`（它们是最细的讲义），本文件是总览与入口。

---

## 三个模块一览

| 模块 | 讲什么 | 一句话证明什么 | 主要产物 | 自检清单 |
|---|---|---|---|---|
| `module1-tdd/` | TDD 与契约测试 | 「什么叫做对了」从主观判断变成一段返回非 0 退出码的程序 | `run_red_green_refactor.py` 驱动器 + `variants/` 三态 + Pydantic/JSON Schema 双契约 + pytest 全套 | docs/01 §九（10 题） |
| `module2-git/` | Git 工作流与钩子 | git 钩子 = 固定时点执行程序 + **只看退出码**；零第三方依赖 | `check_tests_touched.py` 检查器 + `hooks/` 三个钩子 + `ci/quality-gate.yml` + 75 个 pytest 用例 | docs/02 §十（11 题） |
| `module3-shell/` | Shell、退出码与子进程 | 三条流的职责分工 + 退出码是给机器的判定 + 编码是真实故障源 | `01_exit_codes.py` ~ `04_subprocess.py` 四脚本（内置 `_force_utf8`） | docs/03 §十一（12 题） |

配套讲义在 `../docs/01~04`，知识与产物的一一对应索引见 `../docs/05-知识点映射表.md`。

---

## 环境

- 解释器：本目录 `.venv\Scripts\python.exe`（**Python 3.11.0**，已随工作区迁移到 F 盘并验证可用）
- 依赖：三个模块**只使用标准库**（pytest 在 .venv 中，供 module1/2 的测试用）
- 无需任何环境变量：module3 四个脚本已内置 UTF-8 防护，GBK 控制台/管道下实测全部 rc=0

```powershell
# 一次性冒烟：全部模块的测试
F:\Users\zhb\Desktop\study\lab\.venv\Scripts\python.exe -m pytest -q module1-tdd module2-git
#   → module1: 全绿（RGR 三态 + 契约）
#   → module2: 75 passed（检查器 + 钩子包装 + CI YAML 契约）
```

---

## 快速开始（每个模块怎么跑）

### module1-tdd —— TDD 与契约测试

```powershell
cd module1-tdd
..\.venv\Scripts\python.exe run_red_green_refactor.py   # 主司铎：Red → Green → Refactor 全自动演示
..\.venv\Scripts\python.exe -m pytest -q                # 全部用例（含"schema 不与代码漂移"守护）
```

先读 `module1-tdd/README.md`：三阶段定义、有效红灯 vs `ImportError` 假红灯、
`contracts/user-profile.schema.json` 与 `src/calc/contracts.py` 的双契约为什么不能漂移。

### module2-git —— Git 工作流与钩子

```powershell
cd module2-git
..\.venv\Scripts\python.exe -m pytest -q                # 75 passed（含 check_tests_touched 契约）
powershell -NoProfile -ExecutionPolicy Bypass -File demo_hook.ps1   # 17/17 断言演示
```

三个钩子都已落盘：`hooks/pre-commit`（bash）、`hooks/pre-commit.ps1`、`hooks/prepare-commit-msg`。
`demo_hook.sh` 与 bash 钩子建议在 Git Bash 环境复跑（本机 Git Bash 可用，实测正常）。
接入方式（`core.hooksPath` / 直接放 `.git/hooks` / README「方式 C」的 install 脚本）见 `module2-git/README.md`。

### module3-shell —— Shell 与退出码

```powershell
cd module3-shell
..\.venv\Scripts\python.exe 01_exit_codes.py    # 退出码 0/3/1 三种来源 + returncode 读取
..\.venv\Scripts\python.exe 02_pipeline.py      # stdout/stderr 分流 + 真实 bash 管道陷阱（含 pipefail）
..\.venv\Scripts\python.exe 03_filesystem.py    # mtime 增量构建 / 只读保护 / O_EXCL 文件锁
..\.venv\Scripts\python.exe 04_subprocess.py    # 子进程四姿势 + shell=True 注入演示
```

四个脚本可独立运行，退出码 0 即通过。详细机制与 spec-kit 对照见 `module3-shell/README.md`。

---

## 目录内的辅助文件

| 文件 | 用途 |
|---|---|
| `_pip_install.py` | 重建 `.venv` 依赖的辅助脚本（按需运行，正常无需使用） |
| `_hook_matrix.ps1` | 钩子组合矩阵实验原始脚本（module2 内 `probe_win_hook_dispatch.py` 的替代物，保留作原始证据） |
| `pip-install.log` | 安装日志（可删） |

---

## 状态（2026-10-11，迁移到 F 盘后）

- ✅ 三个模块全部可用：module1（RGR + 契约）、module2（75 passed 测试 + 钩子演示 17/17）、module3（四脚本 GBK 修复后全绿）
- ✅ module3 四脚本内置 `_force_utf8()`：Windows GBK 控制台/管道不再崩溃（修复前 03/04 会 `UnicodeEncodeError` exit 1）
- ✅ module2 的 bash 钩子/`demo_hook.sh` 在本机 Git Bash 实测正常（dsh 沙箱内 0xC0000142 问题是沙箱限制，非本机问题）
- ✅ 全部引用路径已更新为 F 盘（`F:\Users\zhb\Desktop\study\lab`）

> 一句话索引：讲义在 `../docs/`，实验在这个目录，实锤在 `../spec-kit/` 的行号里。