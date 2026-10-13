# 02 · Git 工作流与钩子

> 实验台：`lab/module2-git/scripts/check_tests_touched.py`（429 行，module 2 里唯一有逻辑的文件）。
> 它是"改了 `src/` 却没改 `tests/` 就拒绝提交"的守卫，把本文要讲的每一条都落成了可执行代码。
> spec-kit 侧的证据来自 `spec-kit/`，权威参考是 `docs/04-spec-kit架构拆解.md`。

---

## 一、三个区域与 `git diff` 的三个变体

```
工作区 (working tree)  --git add-->  暂存区 (index)  --git commit-->  版本库 (HEAD)
```

`git diff` 系列的每个变体，本质都是**指定这里的两个端点**：

| 命令 | 比较的两端 | 回答的问题 |
|---|---|---|
| `git diff` | 工作区 ↔ **暂存区** | "我改了但还没 `git add` 的是什么？" |
| `git diff --cached`（=`--staged`） | **暂存区** ↔ HEAD | "我下一次 commit **会提交什么**？" |
| `git diff HEAD` | 工作区 ↔ HEAD | "相对上次提交的全部改动（含已暂存）是什么？" |

三个必须记住的点：

1. **`git diff` 看不到已经 `git add` 过的改动**。"我明明改了，diff 是空的"就是这个原因。
2. **`git diff --cached` 才是"提交前审稿"那一条**。钩子要判断"这次提交改了什么"，用的就是它——`check_tests_touched.py:318` 的默认模式正是 `diff --cached --name-only -z --`。
3. `git diff HEAD` = 前两者的并集（同一处重叠会合并展示）。`check_tests_touched.py:307` 的 `--all` 模式用它。

旁证：`git status --short` 的 `XY path` 两列顺序正好对应两端——**X 是暂存区相对 HEAD，Y 是工作区相对暂存区**。`M ` 已暂存、` M` 未暂存、`MM` 两处都有。

### 1.1 一条边界的硬证据：未出生的 HEAD

```bash
git init && git add a.txt
git diff HEAD         # fatal: ambiguous argument 'HEAD'  → 退出码 128
git diff --cached     # 正常工作（index vs 空树）
```

`check_tests_touched.py:64-71` 的注释记录了这件事，`:303-319` 是它的处理：`--all` 模式先探测 HEAD（`:291-300` 的 `git rev-parse --verify --quiet HEAD`），不存在就把基准换成 `diff --cached`，并把 `base` 写成 `"index vs empty tree (HEAD is unborn)"` 放进 JSON 载荷。

**教训**：`HEAD` 不是永远存在的符号。脚本里对 rev 的每次引用都要问一句"首次提交之前它指向什么"。同类问题在 CI 里表现为"首次 push 时不能拿 `HEAD^` 当基准"（见 §8.3）。

---

## 二、按路径过滤变动

### 2.1 只要路径，或路径+状态

```bash
git diff --name-only        # 只列文件名
git diff --name-status      # 每行 "M<tab>路径"
git diff --cached --name-only -z --    # 脚本用：暂存区 vs HEAD，NUL 分隔
```

`--name-only` 是脚本的默认搭档：先拿到路径集合，再决定要不要跑昂贵的检查。`check_tests_touched.py:307/313/318` 三条命令都带 `--name-only -z`。

### 2.2 `--diff-filter` 的字母含义

| 字母 | 含义 | 备注 |
|---|---|---|
| **A** | Added | 新增 |
| **C** | Copied | 需 `-C` 才可能检测 |
| **D** | Deleted | 删除 |
| **M** | Modified | 内容或权限变了 |
| **R** | Renamed | 需重命名检测 |
| **T** | Type changed | 普通文件 ↔ 符号链接 ↔ 子模块 |
| **U** | Unmerged | 未解决冲突 |
| **X** / **B** | Unknown / Broken | 罕见 |

- `--diff-filter=ACMR` 读作"**只看改动之后内容仍然存在的那些**"——新增、拷贝、修改、重命名。用途是筛出"需要继续检查的文件"：被删的文件不用再 lint、再跑版本守卫。
- **大写=保留，小写=排除**。`--diff-filter=D` 只要删除；`--diff-filter=d` 是"所有非删除"。两个都是合法命令，语义相反。
- 搭配 `--no-renames` 可让重命名退化成 A+D，脚本就只需处理三种字母。spec-kit 的版本守卫这么做（`spec-kit/.github/scripts/check_extension_version_bump.py:68`）。

### 2.3 pathspec：`--` 之后才是路径

```bash
git diff --name-only -- '*.py'                  # 通配
git diff --name-only -- 'src/**/*.py'
git diff --name-only -- . ':(exclude)tests/'    # 全部，减去 tests/
git diff --name-only -- ':!tests/'              # 同上的简写
```

- **`--` 是必需的**。没有它，`git diff foo.py` 会被当成"跟 `foo.py` 这个 rev 比"。实验台每条 diff 命令都以 `--` 收尾（`:307/313/318`）。
- 默认模式 `*` 可以跨 `/`；想要 shell 语义用 `:(glob)**/*.py`（`*` 不跨目录、`**` 跨）。
- **pathspec 什么都没匹配到的时候，`git diff` 退出码是 0、输出为空**。所以脚本**不能靠退出码判断"有没有相关改动"，必须判输出是否为空**。这是"假绿"的另一个来源。

### 2.4 前缀比较的隐藏前提：cwd

`git diff` 报告的路径是**相对当前目录**的。所以从子目录跑检查器时，`src/` 的含义就变了。

`check_tests_touched.py:268-275` 的 `find_repo_root()` 用 `git rev-parse --show-toplevel` 拿到根目录，**之后的每条 diff 都以 `cwd=root` 执行**，注释写明目的："Pinning cwd to the top level keeps the prefix semantics absolute and reproducible no matter where the caller is."

另一侧的对称处理：`--src-prefix` / `--tests-prefix` 会被规范化（`:225-236`）——反斜杠换成 `/`（git 输出永远用 `/`，`:74-75`）、去掉 `./` 和前导 `/`、**补上结尾的 `/`**。最后这一条有具体理由（`:232-235`）：不补的话 `--src-prefix src` 会连 `src2/x.py` 一起匹配。而**空前缀是 exit 2 而不是"匹配所有"**（`:72-73`、`:231`）——空前缀会让守卫变成噪音，属于用法错误。

---

## 三、`-z` 的真实必要性（安全问题）

### 3.1 git 默认会"转义"路径

git 默认的路径输出是给**人**看的。含非 ASCII 或控制字符时它做 **C-quote**：加双引号，非 ASCII 字节写成八进制。

实验台把实测记录写在了 docstring 里（`check_tests_touched.py:39-45`，环境 git 2.53.0.windows.2）：

```
$ git diff --cached --name-only
src/app.py
"src/\344\270\255\346\226\207.py"     <- one file; that is not its name
tests/t.py
```

`-z` 之后（`:54`）：**原始字节、NUL 结尾、完全不转义**——`b'src/\xe4\xb8\xad\xe6\x96\x87.py\x00'`。

两条性质各自解决一类问题：**不转义**解决"名字被改写"，**NUL 分隔**解决"名字里的换行/回车把一条路径劈成两条"（文件名可以合法包含这两种字符）。

### 3.2 两种咬人的方式（实际怎么被绕过）

对上面那段转义输出做 `startswith("src/")` 或整段子串匹配的检查器，会被两种方式骗过（`check_tests_touched.py:49-53` 的注释）：

1. **静默放行**：一个真的 `src/` 改动，路径渲染成 `"src/\346..."`，开头是 `"` 而不是 `s` → 前缀匹配失败 → **守卫认为 src 没被动过 → 退出码 0 放行**。没有任何报错，CI 是绿的。
2. **伪装**：一个位于 `src/` 下、**文件名里含 `tests/`**（甚至含换行）的文件，在转义文本里会让整段输出匹配到 `tests/`。于是守卫以为"测试也改了"→ 放行。文件实际在哪，与那段文本无关。

**为什么是安全问题**：它把"守卫"变成了"可以被文件名决定是否生效的守卫"。攻击者不需要绕过检查逻辑，只要改个文件名就能让逻辑看不见自己。**任何基于路径前缀的授权/门禁都有这个失效模式。**

### 3.3 正确写法（照抄实验台那三行）

```python
raw = run_git(["diff", "--cached", "--name-only", "-z", "--"], cwd=root)   # :318, :321
paths = [os.fsdecode(chunk) for chunk in raw.split(b"\0") if chunk]        # :325
```

- **`os.fsdecode()`**（`:55-57` 解释）：UTF-8 + `surrogateescape`。git 把索引路径存为 UTF-8；PEP 529 让 Windows 的 `os.fsdecode` 也同意这一点。用 `errors="replace"` 会让**不同**的非法字节都变成 `�`，两条不同路径塌成同一个字符串；`surrogateescape` 保证"解码再编码"能原样还原字节，也让一条怪路径**永远不会让守卫崩溃**。
- **绝不对 diff 输出用 `splitlines()`**（`:59-60`）：换行分隔和 C-quote 这两件事，在 NUL 作为分隔符之后**同时消失**。
- `-z` 是唯一**不依赖环境配置**的解法。`git config core.quotepath false` 只解决转义那一半，而且要靠每台机器都配对。

---

## 四、Git Hooks 的完整生命周期

钩子是放在 `$GIT_DIR/hooks/`（默认 `.git/hooks/`，可由 `core.hooksPath` 改写）里的**可执行文件**，名字固定。

### 4.1 客户端钩子

| 钩子 | 时点 | 能打断吗 | 关键点 |
|---|---|---|---|
| `pre-commit` | 生成 commit 对象**之前** | ✅ | lint/测试的主战场；`--no-verify` 可跳过 |
| `prepare-commit-msg` | 打开编辑器之前 | ✅ | **`--no-verify` 不跳过它**——别把强制逻辑放这儿 |
| `commit-msg` | 信息写好、commit 落库之前 | ✅ | 校验提交信息格式；`--no-verify` 可跳过 |
| `post-commit` | commit 已落库之后 | ❌ 退出码被忽略 | 只能通知，改不了已发生的事 |
| `pre-push` | `git push` 发出之前 | ✅ | stdin 给待推送 ref 列表；跑全量测试的常见位置 |
| `pre-rebase` / `pre-applypatch` | 变基/打补丁前 | ✅ | |
| `post-checkout` / `post-merge` / `post-rewrite` | 操作之后 | ❌ | 触发依赖安装、重新生成产物 |

### 4.2 服务端钩子（裸仓库 / 自建 Git 服务）

| 钩子 | 时点 | 能打断吗 | 输入 |
|---|---|---|---|
| `pre-receive` | 整批推送、**任何 ref 更新之前** | ✅ 拒绝整批 | stdin：每行 `<old-sha> <new-sha> <ref>` |
| `update` | **每个 ref** 更新前 | ✅ 只拒绝该 ref | 参数 `<ref> <old> <new>` |
| `post-receive` / `post-update` | 全部更新成功之后 | ❌ 退出码被忽略 | 常用于部署、通知 |

层级要记清：**`pre-receive` 是整批闸门，`update` 是单条闸门，`post-receive` 只是公告栏。**

现实约束：**GitHub / GitLab 不允许上传自定义服务端钩子**。托管平台上"把门禁放到服务端"其实等于**分支保护 + 必需状态检查（CI）+ 强制审查**——这直接决定了 §8 的结论。

---

## 五、钩子打断提交的机制就是退出码

`check_tests_touched.py:13-20` 把契约写成了 docstring 的第一块内容：

```
0 = ALLOW   nothing to complain about
1 = BLOCK   src/ files are staged and no tests/ file is staged
2 = USAGE   bad arguments / not a git work tree / git itself failed
```

并跟上一句判词（`:19-20`）："git itself only ever looks at the exit code, so the contract above is the real interface. Everything else is decoration."

对应关系：

| 钩子退出码 | git 的行为 |
|---|---|
| `0` | 继续（认为检查通过） |
| 非 `0` | **放弃当前操作**，把钩子的 stderr 原样显示给用户 |

由此推出四条纪律：

1. **用退出码汇报结论，不要打印一句"有问题"再 `exit 0`**。后者制造了"已检查"的假象。
2. **诊断走 stderr**。让机器读的载荷留在 stdout：`:22-35` 的"流纪律"规定 stdout 只有 `--json` 时的 JSON 文档、stderr 只有 `ERROR: ` 开头的行，且成功时 stderr 完全为空。理由（`:27-30`）：caller 是**机器**（git 或 CI），人和载荷共用 stdout 会让下游必须"猜"载荷从哪开始。
3. **人类信息由 git 转呈**。`:32-33`：人在 `git commit` 那个终端上，会直接看到失败钩子的 stderr。
4. **`--help` 走 stdout 并 exit 0**（`:162`、`:376-377`）：帮助是载荷，不是错误。这是"退出码 + 流分工"一致性的一个小考据点。

一个工程细节：这个脚本**手写参数解析而不用 argparse**（`:183-186`），理由是 argparse 会往 stderr 打自己的 usage 措辞，而脚本承诺 stderr 只有 `ERROR: ` 行。**当你的输出契约比标准库的默认行为更严时，就得放弃标准库。**

### 5.1 一个实现 + 两个瘦包装

`lab/module2-git/scripts/check_tests_touched.py:7-10` 说明了模块结构：`hooks/pre-commit`（bash）和 `hooks/pre-commit.ps1`（PowerShell）都是**瘦包装，只调用这个脚本并转发它的退出码**。"One implementation means the rule cannot drift between two shells."（本节最初写作时 `hooks/` 下只有 `pre-commit` 一个文件；**现在已完整落盘**：`hooks/pre-commit`、`hooks/pre-commit.ps1`、`hooks/prepare-commit-msg` 三个都在，`README.md`（492 行）也已存在，说明安装方式和 Windows 场景——脚本头部 `:7-10` 的"one implementation"承诺兑现了。唯一仍以示例形式存在的是 README「方式 C」里的 `scripts/install-hooks.sh`——README 仅展示脚本内容，实际文件未创建，使用前照抄即可。）

这是钩子脚本最值得学的一条设计：**规则只有一份实现，平台适配层薄到可以一眼看完**。反面写法是把判断逻辑复制进 `.sh` 和 `.ps1` 各一份——两份规则一旦不一致，你就有了一个"取决于用什么 shell 提交"的门禁。

---

## 六、Husky / pre-commit 的配置原理：没有魔法

| 框架 | 机制 |
|---|---|
| **Husky**（v5+） | 执行 `git config core.hooksPath .husky`，把钩子目录换到仓库内 → 钩子**可被提交进版本库** |
| **pre-commit** | 往 `git rev-parse --git-path hooks` 得到的目录写一个 **shim 脚本**，shim 再调框架本体跑 `.pre-commit-config.yaml` 里声明的第三方 hook |

所以：Husky 卖的是"钩子可版本化"，pre-commit 卖的是"钩子实现可复用 + 依赖隔离"。**"钩子"这个概念本身没有任何框架特性。**

等价的原生做法：

```sh
# 方式 A：直接放（最简单，但不进版本库）
printf '#!/bin/sh\nexec python scripts/check_tests_touched.py\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit      # 忘了 chmod，钩子会静默不生效

# 方式 B：改 core.hooksPath（钩子可进版本库，Husky 的等价物）
mkdir -p .githooks && mv ... ; chmod +x .githooks/*
git config core.hooksPath .githooks
```

"钩子不生效"的排查路径因此是固定的：① `git config core.hooksPath` 设了什么（一旦设置，`.git/hooks/` 里的东西**全部被忽略**）；② 文件在不在 `$GIT_DIR/hooks/`；③ 有没有可执行位（WSL/Windows 混合编辑时经常丢）；④ 第一行有没有 shebang。反过来说，`git -c core.hooksPath=/dev/null commit` 可以一次性关掉所有钩子。

---

## 七、钩子的三个真实局限

### ① `--no-verify` 可以绕过

```bash
git commit --no-verify -m "..."   # 跳过 pre-commit 和 commit-msg
git commit -n -m "..."            # 同一开关的短形式
git push --no-verify              # 跳过 pre-push
```

**客户端钩子对"有决心的人"没有任何强制力**——而"这次赶时间"就足够了。它是官方支持的、文档化的逃生门。（细节：`--no-verify` 只跳过 `pre-commit` 和 `commit-msg`；`prepare-commit-msg` 仍会跑，所以别把强制逻辑放那儿。）

有意思的是实验台**主动把这个逃生门告诉了用户**：违规时最后一行 stderr 是 `or skip this hook once with: git commit --no-verify`（`check_tests_touched.py:359`）。这是诚实的做法——既然拦不住，就别假装拦得住；把"我知道你能绕过，请你自己判断"写进提示，比留一个"其实很容易绕过但没人说"的假门禁更好。

### ② `.git/` 不进版本库，`git clone` 带不来钩子

`.git/hooks/` 的内容不会被 push 也不会被 clone。**团队新人克隆完仓库，默认是零保护的**，而且他可能永远不知道有这回事。

`core.hooksPath` 指向仓库内目录（方式 B）能缓解：钩子文件进版本库了。但 `git config core.hooksPath` 这条配置仍然不会自动生效，新人必须跑一次 onboarding 步骤——**还是靠纪律，不是靠机制**。

（`.git/hooks/*.sample` 是 `git init` 放的示例，命名不以钩子名结尾，**永远不会执行**。很多人以为"默认有钩子"。）

### ③ 只在本机、只在本地流程上生效

- **只在你的机器上**：别人的机器是另一套环境、另一套钩子（或者没有）。
- **只在 git CLI 路径上**：IDE 的提交按钮、库调用、网页端编辑、API 提交，钩子行为并不一致；GitHub 网页上 "Commit directly" 根本不经过任何客户端钩子。
- **完全不约束 CI**：CI 里没有你的 `.git/hooks`。

### 结论

> **钩子适合做"本地快速反馈"，不能当作强制门禁。强制门禁必须放在服务端（CI / 分支保护 / 服务端钩子）。**

正确分工是"同一套检查，两个执行点"：本地钩子让你**在 5 秒内**发现问题，CI 是**不可绕过**的那一道。实验台的脚本天生支持这两种角色——`--all` 模式（`:155-158`）就是给"提交之外"的场合（CI、评审机器人）用的，它把基准从"index vs HEAD"换成"work tree + index vs HEAD"：钩子需要的是前者，CI 需要的是后者。**同一份实现，两种基准，一个退出码契约。**

---

## 八、CI 质量门禁：退出码怎么变成"阻断合并"

### 8.1 从退出码到红叉

```
step 里 run: 的命令退出非 0
  → 该 step 结论 = failure
  → job = failure（默认后续 step 不再执行）
  → workflow run = failure  →  对应 check run = failure
  → 分支保护的"必需状态检查"未满足  →  Merge 按钮禁用
```

链路上每一环都是**符号结论**，没有人去读日志正文。推论：把所有错误 `|| true` 掉的 job **在这条链路上等于不存在**；想做"失败了只警告"，正确工具是 `continue-on-error`（UI 上留明确标注），而不是 `|| true`（什么都不留）。

`continue-on-error: true` 的语义：该 step 失败**不使 job 失败**，job 仍绿、必需检查通过、不阻断合并。它适合提示性检查（覆盖率趋势、AI 评审建议），不适合任何你真正想拦住东西的检查。

### 8.2 `paths:` / `paths-ignore:` 的陷阱（spec-kit 真踩过）

```yaml
on:
  pull_request:
    paths: ['extensions/**']     # ← 危险
```

机理：① 路径过滤发生在 **workflow 被创建之前**，不匹配则 workflow 根本不跑、**不产生任何 check run**；② 若这个检查被列为"必需"，GitHub 等的是一个**永远不会到来的结论**；③ 于是它停在 **"Expected"（等待中）**，**所有不触碰该路径的 PR 全部卡死**；④ 页面上没有红色失败，只有一个永远转圈的等待项——**排查成本极高**。

spec-kit 把这个坑写在 workflow 注释里（`spec-kit/.github/workflows/extension-version-guard.yml:13-16`，原文）：

> Deliberately no `paths:` filter: a required status check that is skipped by path filtering stays in "Expected" state and blocks every PR that does not touch extensions/**. The check runs on every pull request instead and the script reports success when nothing under extensions/ changed.

修法就是末句：**不要用 paths 过滤，改成"永远运行，脚本自己判断没有相关改动就成功返回 0"**。对照那个脚本的退出码：没有 `extensions/` 改动 → 说明一行 → `return 0`；有改动但不满足不变量 → `return 1`（`spec-kit/.github/scripts/check_extension_version_bump.py:106-109`）。

| 情况 | 退出码 | check 结论 | 对 PR 的影响 |
|---|---|---|---|
| 没有相关改动 | 0 | success | 不阻挡（正是我们想要的） |
| 有改动且合规 | 0 | success | 不阻挡 |
| 有改动但违规 | 1 | failure | **阻挡**（正是我们想要的） |
| 参数/环境错误 | 2 | failure | 阻挡（不装懂） |

**"跳过"被表达成了"成功"，而不是"不运行"。** 实验台的 `decide_reason()` 是同一个设计：`"nothing staged"` / `"no source files touched"` / `"source and tests both touched"` 三种"没事"都归到 exit 0（`:344-351`），只有真违规才 1。

`paths:` 什么时候是对的？——**只用在非必需的检查上**。spec-kit 对 `docs.yml:4-9`（`on.push.paths: ['docs/**']`）就是这么用的：它控的是 Pages 部署，不跑没有副作用。

### 8.3 两个实战细节

- **基于 diff 的门禁必须先想清"基准是什么"**。`spec-kit/.github/workflows/lint.yml:33-51` 的 `git diff --check` 按事件分成三路：`pull_request` 用 base 比对；**首次 push（全 0 的 SHA）不能拿 `HEAD^` 当基准**；普通 push 才用 `HEAD^..HEAD`。这和 §1.1 的未出生 HEAD 是同一类问题，只是换了个触发场景。
- **守卫脚本自身要严谨**。`extension-version-guard.yml:50-54` 同时用了 `set -euo pipefail` 和显式的 `git rev-parse --verify --quiet HEAD^2` 判断 + `::error::` 注记 + `exit 1`（见 `docs/03-Shell与退出码.md`）。实验台的对偶设计是**顶层兜底**：`check_tests_touched.py:427-429` 捕获所有异常，打印 `internal error: ...` 并 `sys.exit(2)`，注释写着 "never hand a traceback to a hook: exit 2 instead"。**守卫自己崩溃时必须给一个明确的非 0，而不是让 traceback 去决定。** 另外 `:133` 的 `eprint()` 强制 `ERROR: ` 前缀，配合 `:115-128` 的流配置（详见 `docs/03-Shell与退出码.md` §9）。

---

## 九、本地钩子 vs CI 门禁 的分工

| 维度 | 本地钩子（pre-commit / pre-push） | CI 门禁（Actions + 必需检查） |
|---|---|---|
| 强制力 | 无（`--no-verify` 可绕） | 有（合并按钮被禁用） |
| 生效范围 | 只在本机、只在 git CLI 路径 | 所有人、所有提交路径（含网页提交、API） |
| 新人默认状态 | 没有（`.git/` 不进版本库） | 自动生效（跟着仓库走） |
| 反馈延迟 | 秒级 | 分钟级 |
| 环境一致性 | 各不相同（"在我这儿是好的"） | 统一、可复现 |
| 适合承载 | lint、格式化、提交信息格式、快速单测 | 全量测试、构建、跨平台矩阵、安全扫描、版本守卫 |
| 失败处置 | 开发者自己决定要不要绕过 | 无法绕过，只能修 |
| 结论用词 | "建议"、"提醒" | "**门禁**" |

**唯一正确的姿势：两者跑同一套检查，但只有 CI 的结论算数。** 钩子的价值是省时间，不是把关。落到实验台上：`scripts/check_tests_touched.py` 是那份"同一套检查"，`--all` 模式给 CI，默认 staged 模式给钩子。

---

## 十、自检清单

1. `git diff` 为空但 `git diff --cached` 有内容，说明发生了什么？提交后 `git diff HEAD` 是什么？
2. `git init` 后只 `git add`、还没 commit 时，`git diff HEAD` 会怎样？正确基准是什么（`check_tests_touched.py:303-319`）？
3. `--diff-filter=ACMR` 保留哪四类？为什么筛"需要继续检查的文件"用它？大写与小写有什么区别？
4. `git diff --name-only -- 'extensions/'` 什么都没匹配到时退出码是多少？脚本该靠什么判断"没有相关改动"？
5. 路径含 `é` 或 `中` 的文件，`git diff --name-only` 输出什么？用它做 `startswith("src/")` 会怎样失效？**第二种咬人方式**（伪装成 tests 下的改动）是怎么发生的？
6. `-z` 解决了两个问题，分别是什么？为什么用 `os.fsdecode()` 而不是 `errors="replace"`？为什么这个脚本绝不对 diff 用 `splitlines()`？
7. 为什么 `find_repo_root()` 要把 cwd 钉在仓库根？`--src-prefix src` 为什么要补成 `src/`？空前缀为什么是 exit 2？
8. `pre-receive` / `update` / `post-receive` 的时点与"能否打断"分别是什么？GitHub 上为什么没有它们可用？
9. `git commit --no-verify` 跳过哪些钩子？它**不**跳过哪个？由此得出什么设计纪律？
10. 给一个**必需**检查加了 `paths:` 过滤会发生什么？为什么比"漏跑检查"更难排查？spec-kit 的替代做法是什么？
11. 为什么"规则只有一份实现 + 平台适配层是瘦包装"比"两份独立实现"好？实验台是怎么组织的？
