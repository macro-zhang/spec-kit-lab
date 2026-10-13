# 模块2：Git 工作流与钩子

> 一句话：Git 钩子的全部机制是「git 在固定的时点，去 `.git/hooks/<名字>` 执行一个程序，
> 然后**只看它的退出码**」。本模块把这句抽象的话拆成可运行、可断言、可重复的实验，
> 而且**不引入任何第三方依赖**——不用 Husky，不用 pre-commit 框架，不用 npm。
> 刻意的：先看清机制，再决定要不要上工具。

---

## 这个模块要证明什么

一个"改了 `src/` 就必须同时改 `tests/`"的提交前关卡。它由三个场景和一组断言支撑，
断言不符合预期时演示脚本自己 `exit 1`：

| 场景 | 你要做的操作 | 期望的结果 | 证明了什么 |
| --- | --- | --- | --- |
| SCENARIO 1 | 只 `git add src/app.py`，然后 `git commit` | 提交**失败**（非 0 退出） | 钩子的退出码能打断提交流程 |
| SCENARIO 2 | 再 `git add tests/test_app.py`，然后 `git commit` | 提交**成功**（退出 0） | 关卡不是"一律拦"，它真的在判断内容 |
| SCENARIO 3 | `git commit --no-verify` | 提交**成功** | 本地钩子可以被绕过 —— 这是它的真实局限，必须诚实展示 |
| EXTRA | 暂存一个非 ASCII 文件名 `src/中文.py` | 普通 `git diff` 输出被 C-quote，检查器仍能识别 | 为什么必须用 `git diff -z` |

两条附带要证明的事（在 `ci/quality-gate.yml` 里）：

- 同一个判断规则在 CI 里可以用**同一份代码**执行：`check_tests_touched.py` 既被钩子调用，也被流水线调用。
- 流水线靠**非 0 退出码**阻断；而 `paths:` 过滤器会让一个"必需检查"变成永远卡在 `Expected` 的死锁。

---

## 目录结构

```
lab/module2-git/
├── scripts/
│   └── check_tests_touched.py   ★ 唯一的逻辑所在：判定"改了 src/ 但没改 tests/"
├── hooks/
│   ├── pre-commit               ★ bash 版钩子：定位 Python、调用检查器、原样透传退出码
│   ├── pre-commit.ps1           ★ PowerShell 版钩子：同行为、同退出码、同 stdout/stderr 纪律
│   └── prepare-commit-msg       ★ 第二种钩子：不拦截，而是**改写**提交信息（注入分支名）
├── demo_hook.ps1                ★ 端到端演示驱动器（PowerShell，本机已跑通 17/17 断言）
├── demo_hook.sh                 ★ 同样的三场景，给 Git Bash / Linux / macOS 用户
├── ci/
│   └── quality-gate.yml         ★ GitHub Actions 样例：故意放在实验台里，不写进 .github/workflows/
├── .pytest_cache/               并行产出的 pytest 套件留下的缓存（见文末「附」）
├── pyproject.toml               并行产出的 pytest 配置
├── scripts/
│   ├── gate_lab.py              并行产出：场景表与共享脚手架
│   ├── demo_gate.py             并行产出：叙述式演示（含"钩子到底跑没跑"的判定）
│   └── probe_win_hook_dispatch.py 并行产出：测量 git 在 Windows 上如何派发钩子
├── tests/                       并行产出：58 个 pytest 用例，在本机全部通过
└── tools/hookprobe/             并行产出：一个原生 .exe 钩子探针（Windows 上能被子进程执行）
```

每个文件为什么存在、属于哪个知识点：

| 文件 | 为什么需要它 | 讲的知识点 |
| --- | --- | --- |
| `scripts/check_tests_touched.py` | 把"什么算违规"收敛到一处。两个钩子、CI 流水线都调用它，规则只有一份实现 | `git diff --cached --name-only -z`、退出码契约、stdout/stderr 分工 |
| `hooks/pre-commit` | 证明"钩子就是一段会被 git 执行、退出码会被 git 尊重的普通程序" | `pre-commit` 的时点、`exit $?` 透传、`set -euo pipefail`、解释器探测 |
| `hooks/pre-commit.ps1` | Windows 用户不该被迫写 bash；行为必须与 bash 版逐条对齐 | 同一契约的第二种实现、PowerShell 5.1 对原生命令 stderr 的处理 |
| `hooks/prepare-commit-msg` | 钩子不只能"拦"，还能"改"。只演示 `pre-commit` 会让人以为钩子只有一种能力 | 第二种钩子类型、消息文件的可写性、`--no-verify` 的盲区 |
| `demo_hook.ps1` | 光有文件不算证明。"改了 src 会提交失败"必须能被一条命令重放出来 | 端到端断言、临时仓库、`core.hooksPath`、shebang 与执行位 |
| `demo_hook.sh` | Git Bash / Linux / macOS 的读者应该有同一份实验，而不是读一段 Windows 专属的代码 | POSIX shell 写法、`mktemp`、环境变量传递给钩子 |
| `ci/quality-gate.yml` | 本地钩子只在本机生效。真正的抓手在 CI，这份样例把两侧接上 | 非 0 退出码阻断、`::error::` 注解、`paths:` 陷阱 |
| `README.md` | 机制讲清楚，坑记下来，让人不用重复踩 | —— |

---

## 怎么跑

### 1. PowerShell 端到端演示（本机已实测）

```powershell
cd lab/module2-git
powershell -NoProfile -ExecutionPolicy Bypass -File .\demo_hook.ps1
```

本机实测输出（**逐行原样**，只做了删节：省掉部分重复的 `[PASS]` 断言块和路径前缀，
SCENARIO 1/2/3 与 SUMMARY 的每一行文本、退出码都没有改动）：

```
  [i] lab directory : lab/module2-git
  [i] hook flavour  : python
  [i] PowerShell    : 5.1.26100.9168
  [i] git           : git version 2.53.0.windows.2
  [i] python        : python    (3.11.0)
  [i] temp repo     : <临时目录>\dsh-7dOFih\module2-git-demo-4ef2aaf6
  [i] branch        : feature/hooked
  [i] hooks         : python shebang shims -> ...\lab\module2-git\scripts\check_tests_touched.py

==============================================================================
SCENARIO 1 / stage src/ only -> the commit MUST be blocked
==============================================================================
  > git add src/app.py
    exit code: 0
    | <no output>
  > git commit -m "feat: change src only"
    exit code: 1
    | ERROR: source files are staged but no test file is staged.
    | ERROR:   staged under source prefix (1): src/app.py
    | ERROR:   staged under tests  prefix (0): -
    | ERROR: fix: stage the test that covers this change, e.g. git add tests/test_app.py
    | ERROR:      or skip this hook once with: git commit --no-verify
  [PASS] the commit is blocked (non-zero exit)
  [PASS] git really refused it (HEAD still unborn)
  [PASS] the staged change survived the abort

==============================================================================
SCENARIO 2 / also stage a test -> the commit MUST succeed
==============================================================================
  > git commit -m "feat: add app and test"
    exit code: 0
    | [feature/hooked (root-commit) 7563bb3] feat: add app and test
    |  2 files changed, 11 insertions(+)
  [PASS] prepare-commit-msg injected the branch

==============================================================================
SCENARIO 3 / git commit --no-verify -> the gate CAN be skipped
==============================================================================
  > git commit --no-verify -m "chore: bypass the hook"
    exit code: 0
  [PASS] --no-verify does NOT skip prepare-commit-msg
  [i] re-proof: undo that commit (keep the index) and commit again without the flag
  > git reset --soft HEAD~1
  > git commit -m "chore: same state, no bypass"
    exit code: 1
  [PASS] same state WITHOUT the flag is blocked
  [PASS] still only one commit (nothing slid through)

==============================================================================
SUMMARY
==============================================================================
SC   ASSERTION                                EXPECTED       ACTUAL                         RESULT
---------------------------------------------------------------------------------------------------
S1   the commit is blocked (non-zero exit)    true           true                           PASS
S1   the staged change survived the abort     src/app.py     src/app.py                     PASS
S2   the commit succeeded (exit 0)            0              0                              PASS
S2   prepare-commit-msg injected the branch   true           true                           PASS
S3   it landed with no test change at all     src/app.py     src/app.py                     PASS
S3   --no-verify does NOT skip prepare-com... true           true                           PASS
X    plain git output is C-quoted (the trap)  true           true                           PASS
X    the checker sees the real path, not t... true           true                           PASS

RESULT: 17 passed, 0 failed  (flavour: python)
ALL ASSERTIONS PASSED
  [i] removed temp repo: <临时目录>\dsh-7dOFih\module2-git-demo-4ef2aaf6
  [DEMO-EXITCODE=0]
```

注意 SCENARIO 1 里 `git commit` 的失败输出就是检查器打到 **stderr** 的那五行 `ERROR:`——
**失败路径上钩子不加任何装饰**，它只把检查器的退出码原样 `exit` 出去（成功路径上 `hooks/pre-commit`
会多打一行 `pre-commit[check-tests-touched]: ok`，同样在 stderr，`TESTS_TOUCHED_QUIET=1` 可关）。
这正是"stdout 只放载荷、stderr 只放 ERROR"这条纪律的收益：git 把 stderr 直接转给用户看，
不需要钩子再做一层格式化。提交哈希（`7563bb3` 等）每次运行都不同，这里原样保留以免看起来像编的。

`-ExecutionPolicy Bypass` 是必需的：本机 `CurrentUser` 策略是 `RemoteSigned`，新写的 `.ps1`
没有签名，直接 `& .\demo_hook.ps1` 会报 "is not digitally signed"。

`demo_hook.ps1` 还有一个 `-Shebang bash` 开关（把 bash 版钩子原样拷进临时仓库）。在**本机**
它会主动放弃并 `exit 2`，因为这台机器的 msys 运行时起不来（详见文末「沙箱踩坑记录」）；
在能正常跑 Git Bash 的机器上它才是有意义的选项。

**关于默认的 Python shebang 垫片（shim）**：`demo_hook.ps1` 默认往临时仓库的 `.git/hooks/`
里放两个**内容等价**的垫片——`pre-commit` 的 shebang 指向 `python.exe`，然后
`runpy.run_path(<lab>/scripts/check_tests_touched.py, run_name="__main__")`。这不是"绕过"，
而是因为本机连 `env.exe` 都起不来（见坑 1），任何 bash 钩子都会以系统错误告终；
垫片与 `hooks/pre-commit` 调的是**同一份检查器、同一个退出码契约**，只是换了执行者。
在能跑 Git Bash 的机器上，请用 `-Shebang bash` 或 `demo_hook.sh`，那才是把
`hooks/pre-commit` 原样拷进 `.git/hooks/` 的真实路径。

### 2. Git Bash / Linux / macOS 演示

```bash
cd lab/module2-git
bash demo_hook.sh            # 三场景 + 断言，全部通过则 exit 0
bash demo_hook.sh --keep     # 留着临时仓库，方便自己进去翻 .git/
bash demo_hook.sh --python /usr/bin/python3
```

脚本内部的三个场景与 PowerShell 版逐条对应（同样的 17 条断言）。它需要的是一个真能跑的
bash：本机无法执行（见「沙箱踩坑记录」），只做了静态检查，请在能跑 bash 的机器上复跑一次。

### 3. 单独调用检查器（退出码契约）

```bash
cd <任意 git 仓库>
python /path/to/check_tests_touched.py --help          # 用法打到 stdout，退出 0
python /path/to/check_tests_touched.py                 # 暂存区判定：0 放行 / 1 拦截
python /path/to/check_tests_touched.py --json          # stdout 是 JSON 载荷（纯 ASCII）
python /path/to/check_tests_touched.py --all           # 对比 HEAD，用于非提交场景
python /path/to/check_tests_touched.py --src-prefix packages/api/ --tests-prefix packages/api/tests/
```

手工构造三种状态即可验证三个退出码：

```bash
# 0：只改文档
mkdir -p docs && echo hi > docs/note.md && git add docs/note.md
python check_tests_touched.py; echo "exit=$?"          # exit=0

# 1：改了 src/ 但没改 tests/
mkdir -p src && echo 'x = 1' > src/app.py && git add src/app.py
python check_tests_touched.py; echo "exit=$?"          # exit=1，stderr 五行 ERROR

# 2：用法/环境错误
python check_tests_touched.py --nope; echo "exit=$?"   # exit=2
python check_tests_touched.py --src-prefix ''; echo "exit=$?"   # exit=2
```

---

## 速查表 ①：`git diff` 的各种变体

写钩子和 CI 的人 90% 的时间花在回答"**这次改动到底包含哪些文件**"上，而 `git diff` 的
默认行为是"工作区 vs 索引"，偏偏**不是**钩子要的那个集合。

| 命令 | 比较的两端 | 典型用途 | 关键代码 / 注意 |
| --- | --- | --- | --- |
| `git diff` | 工作区 ↔ 索引（未暂存改动） | 提交前看看还有哪些没 `add` | 钩子**不能**用它判断"本次提交内容" |
| `git diff --cached`（`--staged` 同义） | 索引 ↔ HEAD | **pre-commit 的标准取数口** | 就是"本次提交将包含什么" |
| `git diff HEAD` | 工作区 ↔ HEAD（暂存 + 未暂存） | 非提交场景总览（评审、报告） | 刚 `git init` 没有 HEAD 时：`fatal: ambiguous argument 'HEAD'`，必须先探测 |
| `git diff HEAD~1 HEAD` | 提交 ↔ 提交 | 事后审计"上次提交改了什么" | CI 常用 `HEAD^1`；长命 PR 上 `github.event.pull_request.base.sha` 可能已过期 |
| `git diff base...HEAD`（三点） | 合并基 ↔ HEAD | PR 里"这条分支相对主干改了什么" | 三点=**分支差异**；两点 `base..HEAD`=两端全部差异 |
| `git diff --name-only` | 同上，只要文件名 | 判断"碰了哪些目录" | 非 ASCII 路径被 C-quote：`"src/\344\270\255\346\226\207.py"` |
| `git diff --cached --name-only -z` | 同上，NUL 分隔 | **本模块无条件使用** | 输出裸 UTF-8 字节，不转义；Python 侧 `raw.split(b"\0")`，绝不能 `splitlines()` |
| `git diff --cached --name-only --diff-filter=d` | 同上，排除删除 | "改代码"不含"删文件" | 小写=排除，大写=只留；`d` = deleted |
| `git diff --cached --name-status` | 带 `A/M/D/R` 状态 | 需要区分新增 / 修改 / 删除 | 与 `-z` 同用才能正确解析重命名的一对路径 |
| `git diff --cached --name-only -- 'src/**'` | 加 pathspec | 只看某个目录 | `--` 之后全是路径，避免与 revision 名撞车；`**` 要加引号防 shell 展开 |

`-z` 那一行是本模块的核心：

```python
# 不用 -z 时，git 会把非 ASCII 路径转义成普通字符序列（C-quoting），
# 于是 "src/中文.py" 变成 "src/\344\270\255\346\226\207.py"。
# 任何基于前缀的判断都可能被这层转义骗过去 —— 这是"看着对"和"真的对"的分界线。
raw = run_git(["diff", "--cached", "--name-only", "-z"], cwd=root)
paths = [os.fsdecode(chunk) for chunk in raw.split(b"\0") if chunk]
```

---

## 速查表 ②：客户端钩子一览

| 钩子 | 触发时点 | 参数（`$1 $2 $3`） | 能否打断 | 能否改写内容 | 本实验 |
| --- | --- | --- | --- | --- | --- |
| `pre-commit` | `git commit` 生成提交信息**之前** | 无 | ✅ 非 0 即放弃提交 | ❌ | ✅ `hooks/pre-commit`、`hooks/pre-commit.ps1` |
| `prepare-commit-msg` | 生成默认提交信息之后、打开编辑器之前 | `$1` 消息文件、`$2` 来源（`message`/`template`/`merge`/`squash`/`commit`）、`$3` sha | ✅ | ✅ 直接写 `$1` | ✅ `hooks/prepare-commit-msg`（注入 `[branch xxx]`） |
| `commit-msg` | 编辑器关闭、提交信息定稿之后 | `$1` 消息文件 | ✅ 校验消息格式 | ✅ | ❌（表中说明即可，机制与 `prepare-commit-msg` 相同） |
| `post-commit` | 提交**已经完成**之后 | 无 | ❌ 木已成舟 | ❌ | 探测钩子时序时用到 |
| `pre-push` | `git push` 发数据之前 | `$1` remote 名、`$2` remote URL | ✅ 非 0 即取消 push | ❌ | ❌ |
| `pre-receive` / `update`（服务端） | 在服务器上接收推送时 | 见 git 文档 | ✅ | ❌ | ❌（**唯一**不能被 `--no-verify` 绕过的一类） |

本机实测的调用顺序与时点（用只记录自己名字的探针钩子测出）：

```
git commit                          -> pre-commit, prepare-commit-msg, commit-msg, post-commit
git commit --no-verify              -> prepare-commit-msg, post-commit
git commit --amend --no-edit --no-verify -> prepare-commit-msg, post-commit
```

也就是说：`--no-verify` **只**跳过 `pre-commit` 和 `commit-msg`，它**不跳过** `prepare-commit-msg`。
这条反直觉的结论是用实验测出来的，不是从文档抄的（文档只说"跳过 pre-commit 和 commit-msg 钩子"）。

---

## 速查表 ③：退出码约定

| 退出码 | 含义 | 谁产生 | 后果 |
| --- | --- | --- | --- |
| `0` | 允许 | 检查器 / 钩子 | 流程继续：提交继续、流水线继续 |
| `1` | 违规拦截 | 检查器 | 钩子退出 1 → git 放弃本次提交，**工作区与索引原样保留**（改动不会丢） |
| `2` | 用法 / 环境错误 | 检查器 | 同样非 0 → 同样拦截。这是**故意**的 fail-closed：宁可挡住，也不要静默放行 |
| 其它非 0（`127`、`128`、`0xC0000142`…） | 钩子自身崩了、解释器找不到、被系统拒绝执行 | 任意一步 | git 一样中止提交 —— **只要不是 0，就是拦** |

配套的三条流纪律（写在 `check_tests_touched.py` 头部注释里）：

1. **退出码是唯一接口**。调用方靠退出码编程，不靠人去读日志。
2. **stdout 只放载荷**（`--json` 时的 JSON，纯 ASCII，`ensure_ascii=True`）。干净的非 JSON 运行 stdout 为空。
3. **stderr 只放 `ERROR: ` 开头的行**。理由：人类要看的话和机器要读的数据混在一条流里，
   任何下游管道都得开始做字符串解析，契约立刻退化。CI 正因此能把 stderr 逐行变成 `::error::` 注解。

`--help` 是唯一的例外：用法打到 **stdout** 并退出 `0`（它是被请求的输出，不是错误）。

---

## 为什么用原生钩子，而不是 Husky / pre-commit 框架

先说结论：**那些框架本质上就是在 `.git/hooks/` 里放一个转发脚本**，外加帮你管理依赖和缓存。
它们解决的核心问题，`git` 自己用一条配置就能解决——而那条配置值得你先知道：

```bash
# 把钩子目录从「不进版本库的 .git/hooks」换成「在版本库里的 hooks/」
git config core.hooksPath hooks
```

于是：

- 框架做的事 = 生成一个 3~5 行的 `.git/hooks/pre-commit`，内容是"去调用我真正的检查程序"。
  本模块的 `demo_hook.ps1` 里那个 python shebang 转发脚本，就是同一个东西，只不过写了 8 行。
- 框架的价值在别处：多语言工具链、插件生态、并行执行、增量缓存、团队统一版本。
  它**不**在于"能不能拦住提交"——那是 git 的能力，不是框架的。
- 代价也是真实的：多一层依赖、多一层版本升级、多一层"钩子没跑起来时你不知道该怪谁"。
  先把机制看清楚，再决定要不要这一层，是比较省事的路。

所以本模块的全部依赖只有：`git`、标准库 `python3`、以及一个 shell。

---

## 钩子的三个真实局限

想清楚这三条，你就会明白为什么**规范落地不能只靠 git 钩子**。

### 1. 可以被 `--no-verify` 绕过

`git commit --no-verify` 直接跳过 `pre-commit` 和 `commit-msg`（实测，见速查表 ②）。
本模块的 SCENARIO 3 就是专门演示这件事的：脚本会真的用 `--no-verify` 提交成功一次，
并断言"这一提交里没有任何测试改动"。

这不是 bug，是设计：钩子是**给人用的提示器**，不是**强制执行的安全边界**。
要强制，只能放到服务端（`pre-receive`）或 CI 的必需检查上；那两处没有 `--no-verify` 开关。

### 2. 只在本机生效

钩子只影响"装了它的那个工作副本"。后果：

- 新人 `git clone` 之后没有任何钩子；他不知道有这条规矩，也不需要绕过它。
- 每个人的 git 版本、Python 路径、shell 都不一样（本模块的解释器探测就是在跟这件事打交道）。
- 任何"团队约定"如果只写在钩子里，就等于"只在装了它的人的机器上成立"。

### 3. `.git/` 不进版本库，所以钩子不会被 clone 下来

`git clone` 拿到的是工作区文件，`.git/` 是本地状态。你把钩子写进 `.git/hooks/pre-commit`，
**它永远不会出现在别人的仓库里**，`git status` 也看不见它（它不在索引里）。
标准解法只有两条：

- `git config core.hooksPath <仓库内的目录>`，把钩子文件放进版本库；再加一个"新环境初始化脚本"（`make setup`）；
- 或者干脆把判断搬到 CI 的必需检查上。

**这正好解释了 spec-kit 的选择**：它没有把 git 钩子当作规范落地的抓手，而是用 CI 的
必需状态检查（`.github/workflows/extension-version-guard.yml`）。而且那份 workflow 头部
专门写了一行"故意不加 `paths:` 过滤"：

> Deliberately no `paths:` filter: a required status check that is skipped by path
> filtering stays in "Expected" state and blocks every PR that does not touch
> `extensions/**`. The check runs on every pull request instead and the script reports
> success when nothing under `extensions/**` changed.
> —— `spec-kit/.github/workflows/extension-version-guard.yml:13-16`

被 `paths:` 跳过的必需检查**什么状态都不报**，于是 PR 永远卡在 "Expected"。
这是个静默失败：Actions 页面看起来"没跑"（因为确实没跑），而所有 PR 都被卡住。
正确做法是那份 workflow 采用的：**每次都跑**，让检查脚本自己在"没碰相关目录"时报告成功。
本模块的检查器就是按这个契约设计的——没有 `src/` 改动时 `reason` 是
`no source files touched`，退出 `0`，CI 绿。

---

## 把钩子接到真实项目上

三种方式，按"省事"到"可靠"排列：

**方式 A：直接拷进 `.git/hooks/`（最快，也最脆）**

```bash
cp lab/module2-git/hooks/pre-commit          <项目>/.git/hooks/pre-commit
cp lab/module2-git/hooks/prepare-commit-msg  <项目>/.git/hooks/prepare-commit-msg
chmod +x <项目>/.git/hooks/pre-commit <项目>/.git/hooks/prepare-commit-msg   # Git Bash / Linux / macOS
```

Windows 上 `chmod` 是无意义的：NTFS 没有可执行位，git for Windows 靠**shebang / 文件内容**
判断能不能跑。`git update-index --chmod=+x .git/hooks/pre-commit` 也不行——它只作用于被索引
跟踪的文件，而 `.git/hooks/` 永远不在索引里（实测报 `Ignoring path` + `fatal: cannot chmod +x`）。

**方式 B：用 `core.hooksPath` 指向仓库内的目录（推荐）**

```bash
mkdir -p hooks
cp lab/module2-git/hooks/pre-commit lab/module2-git/hooks/prepare-commit-msg hooks/
cp lab/module2-git/scripts/check_tests_touched.py scripts/
git config core.hooksPath hooks        # 相对路径：git 会相对工作区根解析
git config --get core.hooksPath        # 复核
```

这样钩子文件进了版本库，能被 clone、能被 review、能被 diff。
注意别把 `core.hooksPath` 写成 `git diff` 那种 POSIX 风格绝对路径：
Windows 原生 git 读到 `/tmp/xxx` 会当成 `C:/tmp/xxx`，钩子就再也找不到了。

**方式 C：写上初始化脚本（可靠的团队方案）**

```bash
# scripts/install-hooks.sh  —— 新环境跑一次
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath hooks
chmod +x hooks/* 2>/dev/null || true
echo "hooks installed: $(git config --get core.hooksPath)"
```

再配上一句 README 里的 `bash scripts/install-hooks.sh`，以及 CI 里跑同一个检查器。
"本机提示 + CI 强制"两层一起上，才是能落地的组合。

**Windows + PowerShell 版钩子的接法**（`hooks/pre-commit.ps1` 文件头也写了）：

```bash
# hooks/pre-commit —— bash 转发脚本，文件名字必须是 pre-commit（git 不看扩展名）
#!/usr/bin/env bash
set -euo pipefail
exec powershell -NoProfile -ExecutionPolicy Bypass -File "$(dirname "$0")/pre-commit.ps1" "$@"
```

`#!/usr/bin/env pwsh` 这种写法在本机不可行（没有 `pwsh`，而且 msys 的 `env.exe` 起不来）。
`powershell … -File` 是稳的：它不依赖执行策略签名，也不依赖 `.ps1` 关联。

**接完之后的检查清单**

- [ ] `git config --get core.hooksPath` 指向你放钩子的目录；
- [ ] `hooks/pre-commit` 能被 `bash -n`（或直接跑）通过 —— 语法错误会让**每一次提交**都失败；
- [ ] 故意制造一次违规（只改 `src/`）确认提交被拦；再制造一次合规提交确认能过；
- [ ] 确认 `TESTS_TOUCHED_CHECKER` / `TESTS_TOUCHED_PYTHON` / `TESTS_TOUCHED_QUIET` 这三个环境变量
      你有没有需要覆盖（钩子里的查找顺序是：环境变量 → `.git/hooks/` → `<repo>/scripts/` → 本实验台路径）；
- [ ] 把同一份检查器接进 CI 的必需检查，并且**不要**给它加 `paths:` 过滤。

---

## 本次交付的验证状态（诚实标注）

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| `check_tests_touched.py` 的 0/1/2 退出码契约 | ✅ 实测 | 独立的 Python 校验脚本 11 组共 **56 条断言全部通过**（含无 HEAD 的刚 init 仓库、非 ASCII 路径被 C-quote 的对照、`--src-prefix src` 不再误伤 `src2/`、用法/环境错误、`--help`） |
| `check_tests_touched.py` 的 stdout/stderr 纪律 | ✅ 实测 | 违规运行：stdout **为空**、stderr 恰好 5 行 `ERROR: `、退出 1；`--json` 运行：stdout 一行 ASCII JSON |
| `demo_hook.ps1`（默认 `-Shebang python`） | ✅ 实测 | `RESULT: 17 passed, 0 failed` / `ALL ASSERTIONS PASSED` / 退出码 0 |
| `demo_hook.ps1 -Shebang bash` 的前置检查 | ✅ 实测 | 本机 msys 起不来 → 明确报错并退出 2（不是伪装成"通过了"） |
| git 的钩子派发顺序与 `--no-verify` 的盲区 | ✅ 实测 | `pre-commit` → `prepare-commit-msg` → `commit-msg` → `post-commit`；`--no-verify` 只跳过前两者中的 `pre-commit` 和 `commit-msg` |
| `ci/quality-gate.yml` | ✅ 已校验 | YAML 能被解析；5 个 `run:` 块逐个通过引号/块配平/LF/无 BOM 检查；触发条件确认**没有** `paths:` |
| `demo_hook.sh`、`hooks/pre-commit`、`hooks/prepare-commit-msg` | ⚠️ **未能在本机执行** | 三个文件只做了静态检查（引号配平、块配平、LF、无 BOM）。原因见下节：本机任何 msys 二进制都无法启动 |
| `hooks/pre-commit.ps1` 的端到端运行 | ⚠️ 未在本机以 `.git/hooks/pre-commit` 的身份运行 | 它引用的检查器路径、退出码与流纪律已逐条核对；python shebang 转发版钩子已在真实 `git commit` 中被证明能拦住提交 |
| 目录外的副作用 | ✅ 已确认 | 仓库根下 `.github/` 不存在；spec-kit 克隆 `git status --porcelain` 干净 |

---

## 沙箱踩坑记录

按"如果再遇到，应该先想到它"的顺序：

1. **本机所有 msys/cygwin 程序都不能启动**。`bash.exe`、`sh.exe`、`ls.exe`、`env.exe`、`dash.exe`
   全部立刻退出，退出码 `-1073741502`（`0xC0000142`），stderr 是
   `*** fatal error - couldn't create signal pipe, Win32 error 5`。
   后果很重：**git 无法执行 bash 钩子**（它解析 shebang 后去 spawn `/usr/bin/env.exe`，那个进程死了）。
   绕法：用原生 PE 解释器当 shebang（`#!C:/…/python.exe`），并在代码注释里说明这一点。
   替代方案 WSL 也不可用（`wsl.exe` 返回 `E_ACCESSDENIED`）。
2. **`$Args` 是 PowerShell 自动变量**。写 `param([string[]]$Args)` 会被静默覆盖，收到的永远是 `$null`。
   改名 `$Argv` 即可。这个坑会让你以为"参数没传进来"，实际是语言层面的占位。
3. **`Start-Process -PassThru` + `WaitForExit(ms)` 读不到 `ExitCode`**（拿到空值）。
   要读退出码就用 `& cmd` + `$LASTEXITCODE`；`Start-Process` 还会在嵌套 PowerShell 里报
   `Access is denied`。
4. **PowerShell 5.1 会污染原生命令的 stderr**：`cmd 2>&1 | Out-String` 会给第一条 stderr 行套上
   `At line:… CategoryInfo… NativeCommandError`；`cmd 2> file` 写进去的是 UTF-16LE 的 ErrorRecord，
   不是原始字节。要拿干净文本得逐条取 `$_.Exception.Message`，或者干脆不重定向、让子进程继承流。
5. **`-like` 的 `[...]` 是字符集**，不是字面量。`-like '*[branch main]*'` 几乎能匹配任何字符串，
   断言会静默失效。含方括号的字面量一律用 `.Contains(...)`，或用 `grep -F`。
6. **控制台编码是 GBK**：脚本输出只用 ASCII 是最省事的解法；检查器还额外对 stdout/stderr 调
   `reconfigure(errors="replace")`，保证任何路径都不会把"判定"变成 `UnicodeEncodeError` 回溯。
   `--json` 的载荷用 `ensure_ascii=True`，在 GBK 控制台、PowerShell 管道、CI 日志里都是同一串字节。
7. **`git update-index --chmod=+x .git/hooks/pre-commit` 不可能生效**（实测退出 128，
   `Ignoring path` + `cannot chmod +x`）：它只处理索引里的文件，而 `.git/hooks/` 不在索引里。
   Windows 上真正决定钩子能不能跑的是 shebang。
8. **Git Bash 里 `git config core.hooksPath /tmp/…` 会写进一个原生 git 读不懂的路径**。
   msys 会对**命令行参数**做路径转换，但不会转换**配置值**；`/tmp/x` 被原生 git 解析成 `C:/tmp/x`，
   钩子直接找不到。用相对路径（`.git/hooks`）最稳。`demo_hook.sh` 里为此专门写了注释。
9. **执行策略拦新脚本**：`CurrentUser = RemoteSigned`，刚生成的 `.ps1` 没有签名，
   `& .\x.ps1` 直接拒绝运行（文件上**没有** Zone.Identifier）。跑法：
   `powershell -NoProfile -ExecutionPolicy Bypass -File x.ps1`。
10. **每一条 git 命令都会打一行无害警告**：
    `warning: unable to access '~/.config/git/ignore': Permission denied`（Windows 上打印的是家目录全路径；退出码仍是 0）。
    它会污染"合并两个流"的断言——所以演示脚本的断言只读 **stdout**，显示才用合并输出。

---

## 附：同目录的并行产出

同一次实验里，这个目录还得到了一套互补的验证材料（不是上表那 8 个交付文件的一部分，
但它们**引用的正是同一个 `scripts/check_tests_touched.py`**，因此可以当作独立复核）：

| 路径 | 内容 | 怎么用 |
| --- | --- | --- |
| `tests/` + `pyproject.toml` | 58 个 pytest 用例，直接驱动检查器（含"违规时 stdout 必须为空"这类流纪律断言） | `..\.venv\Scripts\python.exe -m pytest -q` |
| `scripts/gate_lab.py` | 场景表 + 共享脚手架，让下面的叙述式演示和 pytest 跑**同一套场景** | 被上面两者 import |
| `scripts/demo_gate.py` | 叙述式演示：退出码契约 / `-z` 的必要性 / "这台机器上 git 到底能不能执行钩子" | `python scripts/demo_gate.py` |
| `scripts/probe_win_hook_dispatch.py` + `tools/hookprobe/` | 用一个**不含任何逻辑**的原生 `.exe` 钩子探针，测量 Windows 上 git 的钩子派发（名字、参数、顺序、失败后果） | `python scripts/probe_win_hook_dispatch.py` |

它们的共同观点值得单独记一句：**"提交被拦住了"本身不是证据**——它可能是钩子真的判了违规，
也可能是钩子根本没启动（本机就存在这种情况：msys 起不来时**每一次**提交都会失败，
哪怕钩子本该退出 0）。要区分这两种情况，就必须测"派发"而不是测"结果"。
