# 03 · Shell 与退出码

> 实验台：`lab/module3-shell/` 四个脚本（`01_exit_codes.py` / `02_pipeline.py` / `03_filesystem.py` / `04_subprocess.py`，直接 `python <file>` 运行），
> 加上 `lab/module2-git/hooks/pre-commit:1-144`——一个 144 行的真实 bash 钩子，本文的"退出码即控制流"在它身上是完整实现。
> **实测限制（如实说明）**：本会话文件沙箱禁止命名管道，`bash` 启动即 `fatal error - couldn't create signal pipe, Win32 error 5`，
> 所以 shell 语义引用的是**文档化语义 + 实验台里写好的命令**，不是我现场跑出的数字；标注「实测」的部分由别的途径验证（Python、git 命令）。

## 一、POSIX 退出状态码

进程退出时返回 0–255 的整数。**约定：0 = 成功，非 0 = 失败。这是唯一被普遍遵守的约定。**

| 码 | 含义 | 怎么产生 |
|---|---|---|
| **0** | 成功 | 一切正常的默认值 |
| 1 | 通用失败 | 绝大多数程序用它表示"业务上失败"；也是 Python 未捕获异常的码 |
| 2 | 用法错误 / 误用 | shell 内建、`git`、`pytest` 都用它表示"参数不对" |
| 3–125 | 常规失败 | 各程序自定义 |
| **126** | 找到命令但**不可执行** | 没有 x 权限、或它是个目录 |
| **127** | **命令未找到** | `nosuchcmd`；脚本里 `command not found` |
| **128+N** | 被信号 N 杀死 | `kill -9` → 137；`kill -15` → 143 |
| **130** | 被 SIGINT 中断 | 128 + 2（终端里 Ctrl-C） |
| 255 | 显式失败 / 溢出 | `exit -1` 被截断成 255 |

四件容易搞混的事：

1. **只有 0 是成功**，"非 0"没有统一语义。判成功必须写 `if cmd; then`（即 `== 0`），不要写 `if [ $? -ne 1 ]`。
2. **退出码是 8 位**：`exit 256` → 0，`exit 257` → 1。**≥256 的自定义码会静默回绕**，设计时不要超过 255。
3. **128+N 是 shell 的约定，不是操作系统的强制**。程序自己捕获信号后 `exit 0`，那它就是成功退出——所以 CI 里"被 kill 的进程"要额外看日志，不能只信码。
4. **126/127 的语义是"不是命令失败了，是命令根本没跑起来"**。这和 `docs/01-TDD与契约测试.md` 里的"无效红灯"是同一类问题：**环境错误伪装成业务失败**。

实验台 `01_exit_codes.py:38-49` 把三种成败做成了真实进程：

```python
if mode == CHILD_OK:      return 0                                    # :41
if mode == CHILD_FAIL:                                                # :43
    print("ERROR: 子进程明确失败（这是诊断，不是数据）", file=sys.stderr)  # :44
    return 3                                                          # :45
if mode == CHILD_CRASH:                                               # :46
    raise ValueError("未捕获的异常")                                    # :47
```

`CHILD_CRASH` 用**未捕获异常**：Python 打 traceback 后以**退出码 1** 结束（`01_exit_codes.py:9-13` 的 docstring 列出全部来源：`return N` / `sys.exit(N)` / 未捕获异常 → 1 / `sys.exit("msg")` → 1 且 msg 进 stderr）。于是**"程序崩溃"和"程序报告业务失败"在退出码上不可区分**——这是把粒度全押在退出码上的第一个反例（见 §10.2）。

## 二、stdout vs stderr：不是两个输出口，是两条通道

| fd | 名字 | 语义角色 | 谁读它 |
|---|---|---|---|
| 0 | stdin | 输入 | 命令 |
| **1** | stdout | **数据通道**（载荷本身） | `$()` 和管道**只接这个** |
| **2** | stderr | **诊断通道**（日志、进度、错误、警告） | 人；CI 日志聚合器 |

**`$()` 和管道只捕获 fd1**，其余全部由此推出：**stdout 只放载荷**（一个命令的 stdout 应恰好等于"它算出来的东西"，多一个字符都会污染下游）；**stderr 只放诊断**（进度、警告、错误原因随便打，不会污染管道）。

实验台做成了可运行对照：`02_pipeline.py:34-38` 的 `emit_good()` 往 stdout 打两行数据、return 0；`:41-44` 的 `emit_bad()` **stdout 什么都不打**，只往 stderr 写 `ERROR: 数据源不可用` 并 return 4；`:47-59` 的 `demo_streams()` 分别统计两个流的字节数，让"数据 0 字节、诊断 58 字节"这种事实可见。

`01_exit_codes.py:89-93` 把纪律写成总结行：**stdout = 数据；stderr = 诊断；退出码 = 判定。**

**违反它会怎样**：把 `ERROR: 数据源不可用` 打到 stdout（`01_exit_codes.py:88` 就在点这个坑）→ `$()` 把这行错误**当成数据**收进变量 → 下游 `json.loads(...)` 炸在莫名其妙的字符上，或者更糟：错误消息被当成合法数据写进产物。这是"脏数据从管道流出去"的典型路径。

真实代码的同一纪律：`lab/module2-git/hooks/pre-commit:137-142` 明确写下 "the checker owns stdout (payload only) and writes its own ERROR lines to stderr"，于是钩子自己的寒暄也只走 stderr（`>&2`）。

## 三、重定向速查与顺序敏感性

| 写法 | 精确语义 |
|---|---|
| `> file` / `>> file` | fd1 → file（**截断** / **追加**） |
| `2> file` | fd2 → file |
| `1>&2` / `2>&1` | fd1/fd2 → 复制**此刻**另一方的指向 |
| `&> file` / `&>> file` | `> file 2>&1` / `>> file 2>&1` 的简写（**bash 扩展**，POSIX sh 不支持） |
| `> file 2>&1` | 两个流都进 file |
| `2>&1 > file` | fd2 停在**原来的**目标（通常是终端），只有 fd1 进 file |
| `> /dev/null 2>&1` | 两个流都丢弃（静音，但**退出码仍保留**） |
| `2>/dev/null` | 只丢诊断，载荷照常进管道 |

### 3.1 顺序为什么敏感

因为重定向**从左到右逐个执行**，而 `2>&1` 的语义是"把 fd2 复制成 fd1 **此刻**指向的东西"，不是"让 fd2 永远等于 fd1"：

```
cmd > file 2>&1   步1: fd1 := file      步2: fd2 := 复制 fd1 → file      结果：都进 file      ✅ 捕获一切
cmd 2>&1 > file   步1: fd2 := 复制 fd1 → 终端（此时 fd1 还是终端）  步2: fd1 := file   结果：stderr 在终端，stdout 进 file ⚠️
```

一句话记忆：**`2>&1` 必须写在 `>file` 之后才"跟着走"**。

第二层用途：`2>&1 > file` 恰好是"**载荷存文件、诊断留屏幕**"——交互调试时非常有用（数据落盘，报错还能看到）。很多人第一次见它以为是笔误，其实它是刻意利用顺序语义。

## 四、`set -o pipefail` 修复什么

**默认行为**：管道的退出码 = **最后一个命令**的退出码，前面所有命令的失败被丢弃。

```bash
false | tee log
echo $?          # 0  ← false 失败了，但 tee 成功了
```

这是 CI 里最经典的**假绿**来源。`02_pipeline.py:12-16` 的 docstring 点了它，`:62-98` 的 `demo_shell_pipe()` 生成完整对照脚本（`:68-90`）：

```bash
# C) 未开 pipefail
out=$("$PY" "$SELF" --emit-bad 2>/dev/null | head -n 1)
rc=$?            # ← 0！ERROR 被 head 的成功掩盖了
# :87 之后
set -o pipefail
"$PY" "$SELF" --emit-bad 2>/dev/null | head -n 1   # 管道退出码 = 4 → 立刻暴露
```

`emit_bad` 返回 4、`head` 返回 0 → 管道返回 0，上层以为一切正常。

**精确语义**：管道退出码 = 管道中**最右边那个失败（非 0）命令**的退出码；全成功则 0。

搭配技巧：

- `cmd | tee log`：tee 同时写文件并透传 stdout——它就是为管道设计的。
- `| head -n 1` **故意早退**会让上游吃 SIGPIPE → 上游退出码可能是 141（128+13）。**这是 pipefail 的副作用**：`head` 是有意截断时，pipefail 把正常行为报成失败。别因此关掉开关，而是给那一条管道加 `|| true` 并写清原因。
- 想查管道中**每个**命令的码：bash 的 `PIPESTATUS`。`false | true; echo "${PIPESTATUS[@]}"` → `1 0`。

## 五、`set -euo pipefail`：三个开关各管什么

| 开关 | 全称 | 作用 | 坑 |
|---|---|---|---|
| `-e` | `errexit` | 命令返回非 0 就**立即退出脚本** | **大量场景下静默失效**（5.2）——"我加了 `-e` 所以不会漏错"是错的 |
| `-u` | `nounset` | 引用未定义变量 → 报错退出 | 配 `"${VAR:-default}"`；`$1` 没传就直接炸，**这通常是好事** |
| `-o pipefail` | — | 见 §4 | `head` 早退导致上游 SIGPIPE 时会把正常行为报成失败 |

**为什么必须三个一起用**：只有 `-e` 时 `false | tee log` 仍返回 0（管道只看最后一个）；只有 `pipefail` 时，不在管道里的 `false` 仍被忽略；少了 `-u`，`rm -rf "$OUTPUT_DIR/"` 在变量未定义时会变成 `rm -rf "/"`——**最危险的一行**。

`lab/module2-git/hooks/pre-commit:41` 就是这个组合，而且它的用法值得逐行看：`:48` 写成 `if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then`——**赋值 + `if` 条件**，这正好利用了 5.1 的"测试上下文不触发 `-e`"，从而自己决定"不是 git 仓库"这张牌怎么打（`:49-50` 打 stderr + `exit 1`），而不是让 `-e` 悄悄结束脚本。

### 5.1 `set -e` 在哪里失效（bash 手册原文规则）

> 如果失败的指令是下列之一，shell 不会退出：`while`/`until` 后面的指令列表的一部分；`if`/`elif` 后面的测试的一部分；`&&`/`||` 列表中**除最后一个**之外的任何指令；管道中**除最后一个**之外的任何指令；或者其返回值被 `!` 反转的指令。

```bash
set -e
false                      # → 立即退出（唯一"按预期工作"的情况）
false && echo hi           # → 不退出（false 不是 && 列表的最后一个）
false || true              # → 不退出（它被处理了，算成功）
if false; then :; fi       # → 不退出（测试上下文）
while false; do :; done    # → 不退出（测试上下文）
! false                    # → 不退出（取反 = 成功）
out=$(false)               # → **退出**（赋值的状态就是命令替换的状态）
if out=$(false); then :; fi  # → 不退出（在测试上下文里）
grep -q x file || true     # → 不退出（你主动处理掉了错误）
```

两条实践纪律：① **`set -e` 不是错误处理，它只是"默认不忽略最后一个命令的失败"**，真正的错误处理仍要 `if ! cmd; then ... fi`；② **`&&`/`||` 链是"我已知这里可能失败"的标记**，写完 `a && b` 别忘了整条链的结果也要被检查。

### 5.2 一个几乎人人踩过的坑：`local x=$(f)`

```bash
f() { x=$(false);       echo "无 local: status=$?"; }   # status=1（看得到真实失败）
f() { local x=$(false); echo "有 local: status=$?"; }   # status=0  ← 被吞了
```

原因：`local` 是内建命令，**它自己的返回值覆盖了命令替换的返回值**（`local` 几乎总是 0）。修法：**声明与赋值分两行**，或显式检查。

```bash
f() { local x; x=$(cmd) || return $?; }
```

同一类陷阱：`export X=$(cmd)`、`declare X=$(cmd)`、`readonly X=$(cmd)`——任何"内建 + 赋值"都可能掩盖状态。

## 六、在 `$()` 里取回被吞的退出码

### 6.1 基本手法

```bash
out=$(f)
status=$?                       # 必须紧邻下一行！中间夹任何命令都会覆盖 $?
printf '%s\n' "$out"
[ "$status" -eq 0 ] || exit "$status"
```

三条纪律：① **`status=$?` 必须紧跟**，插一句 `echo`，`$?` 就变成 `echo` 的状态（0）；② 不要用 `local` / `export` 的组合形式（§5.2）；③ **命令替换会剥掉所有结尾换行**——`out=$(printf 'a\n\n\n')` 得到 `a`。文本数据通常无害，但**"必须原样保存的内容"被静默截断**。

### 6.2 `printf x` 哨兵：spec-kit 的真实手法

`spec-kit/scripts/bash/check-prerequisites.sh:186-187`：

```bash
if TEMPLATE_CONTENT=$(resolve_template_content "$TEMPLATE_NAME" "$REPO_ROOT"; status=$?; printf x; exit "$status"); then
    TEMPLATE_CONTENT="${TEMPLATE_CONTENT%x}"
```

| 片段 | 解决什么 |
|---|---|
| `status=$?` | 在子 shell 内**紧跟**在函数调用之后，把真实退出码存下来 |
| `printf x` | 往输出末尾**追加哨兵**：命令替换会剥掉所有结尾换行，有哨兵之后真正要保留的换行被"顶"到哨兵之前，不会被剥 |
| `exit "$status"` | 子 shell 的退出码 = 函数的退出码（**不是 `printf` 的**），`if` 才能正确判定 |
| `${TEMPLATE_CONTENT%x}` | 从变量尾部**精确剥掉那一个哨兵**（`%` 是最短后缀匹配） |

**为什么必须这么写**：`resolve_template_content` 输出的是模板文件内容。模板若以空行结尾，末尾空行被吃掉 → 模板"变形"，而且**没有任何报错**。哨兵是唯一同时满足"内容原样 + 退出码保留"的写法。

> 一句话记忆：**`$()` 吃掉两样东西——末尾换行和退出码；哨兵修前者，`status=$?; exit $status` 修后者。**

Python 读者的对照：这相当于 `subprocess.run(..., capture_output=True)` 同时给你 `.stdout` 和 `.returncode`；shell 的难处是它把两者塞进了同一次求值。

**同一手法的另一个真实用例**：`lab/module2-git/hooks/pre-commit:132-144` 必须把检查器的退出码原样传给 git，所以它**显式关掉 `-e` 再取回状态**：

```bash
set +e
"${python_argv[@]}" "$checker" "$@"      # :133
status=$?                                # :134
set -e                                   # :135
...
exit "$status"                           # :144
```

`:128-131` 的注释把这个动作的理由写死了：`set -e` 本来也会因非 0 中止，但**显式转发才把契约写进代码**，而不是留给一个 shell 选项；并警告"Do not 'improve' this by swallowing the code: the day this hook returns 0 on a violation is the day it stops being a gate."

## 七、文件系统基础操作

### 7.1 只读位：`os.chmod` 与 `stat.S_IREAD`

```python
os.chmod(frozen, stat.S_IREAD)     # 03_filesystem.py:71 —— 只读位（POSIX 0o444）
os.access(frozen, os.W_OK)         # :72 —— 检查"当前用户能不能写"
```

`stat` 的三个常量 `S_IREAD`(0o400) / `S_IWRITE`(0o200) / `S_IEXEC`(0o100) 只管 **owner 那一段**；完整权限是 owner/group/other 三段（如 `0o644`）。

`03_filesystem.py:77-87` 的实测结论：设只读后再写 → `PermissionError`（`:80` 提示**以管理员/root 运行会被绕过**，root 无视权限位）；`:84-87` 的结论是重点——**只读位挡"手滑"，不挡"有心人"或提权进程**；真正需要强制力的场合，强制力来自版本控制 + CI。

**Windows 差异（`:13-18`）**：没有 owner/group/other 三段模型，只有一个**文件只读标志**（`FILE_ATTRIBUTE_READONLY`）。所以 `os.chmod(p, 0o444)` 在 Windows 上**只有"把只读标志置上"生效**；`os.access(p, os.W_OK)` 返回的是这个标志的状态，不是"我这个用户能不能写"；真正的权限机制是 **ACL**（`pywin32` / `icacls`）。因此**跨平台脚本不能假设 `chmod` 有 POSIX 语义**——`IS_WINDOWS = os.name == "nt"`（`:34`）这类判断必须写出来。

### 7.2 用 mtime 做增量构建，以及为什么它不可靠

```python
target.stat().st_mtime < source.stat().st_mtime   → 需要重建    # :60 的判定公式
```

`03_filesystem.py:37-60` 的演示很讲究：`:46` 先 `time.sleep(1.1)`，因为**很多文件系统时间戳精度只有 1 秒**——这一行本身就是第一个注脚。

五个真实原因：

1. **时钟回拨 / NTP 校时** → 漏建或反复重建。make 历史上最著名的"莫名其妙不编译"。
2. **编辑器"保存但不改内容"**：`Ctrl-S` 更新 mtime（内容一样）→ 无谓重建；"格式化又格式化回来"同理。
3. **`git checkout` / `git clone` 重设 mtime**：切分支后所有文件都是"刚刚"，增量信息全失效——CI 里"缓存命中仍全量重建"的常见原因。
4. **网络文件系统（NFS/SMB）**：客户端/服务端时钟不一致、精度更粗，跨机比较基本不可信。
5. **同一秒内的两次修改**：秒级精度下只留一个时间点。

替代物：**内容哈希**（最可靠，代价是读全量内容）；**构建系统的依赖记录**（`make` 的 `.d`、Bazel 的 action cache）；**显式强制**（CI 缓存 key 用 lockfile 哈希）；用 mtime 时**同时比 `st_size`**，能挡住一部分"改了但 mtime 没变"。

### 7.3 文件锁的三种思路，与锁文件的经典缺陷

| 思路 | 平台 | 机制 | 备注 |
|---|---|---|---|
| **`O_CREAT \| O_EXCL` 原子创建锁文件** | 跨平台 | `open()` 的**创建失败**就是"抢锁失败" | 实验台用的就是这个（`03_filesystem.py:100-108`） |
| **`fcntl.flock`** | Unix | 对已打开 fd 加建议锁，**进程退出时内核自动释放** | 崩溃不留残骸；NFS 语义有历史坑 |
| **`msvcrt.locking`** | Windows | 对文件区域加字节范围锁 | 更完整的是 `LockFileEx`（需 `pywin32`） |

```python
def acquire() -> bool:                                              # 03_filesystem.py:100
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)     # :103 原子创建
    except FileExistsError:
        return False                                                # :107-108 已有人持锁
    try:    os.write(fd, str(os.getpid()).encode())
    finally: os.close(fd)
    return True
```

`:119-122` 是最重要的一句结论：**必须用 `O_CREAT | O_EXCL` 一次调用原子完成"检查并创建"；先 `os.path.exists()` 再 `open()` 是竞态**——两个进程可以同时通过 `exists()` 检查，然后双双创建成功。

**经典缺陷**：进程崩溃（`kill -9`、CI 超时强杀）时**没机会删锁文件** → 锁永久残留 → 后续所有运行都被挡在门外，而且表现为"莫名其妙的超时/跳过"，不是报错。缓解手段（可靠度递增）：① 锁里写 pid + 启动时间，失败时 `kill -0 $pid` 探活（坑：pid 会被回收，跨机器无意义）；② 加 TTL 过期抢占（坑：持锁方慢 ≠ 死了）；③ **用有自动释放语义的锁**（`flock` / `LockFileEx` / 数据库行锁，进程死亡由内核或服务端释放，最省心）；④ **不用锁**：改成"幂等 + 唯一命名"（输出到以内容哈希命名的目录，最后原子改软链接指向它），CI 里最稳的往往就是这条。

> 锁文件是"用文件系统当互斥量"；文件系统没有所有权概念，所以它缺的正是"持锁者死了怎么办"这个答案。

## 八、Python 子进程要点

| 姿势 | 代码 | 用途 |
|---|---|---|
| 只要它跑完 | `subprocess.run(cmd)` | 不关心结果（**失败也不抛异常**） |
| 要结果且要校验 | `subprocess.run(cmd, check=True)` | CLI 的默认选择 |
| 要 stdout/stderr | `capture_output=True, text=True` | 需要解析输出 |
| 要流式输出 | `Popen(..., stdout=PIPE)` + `-u` | 长时间运行、实时日志 |

**`returncode` 语义**（`04_subprocess.py:39-47`）：

```python
proc = subprocess.run([sys.executable, "-c", "import sys; print('ok'); sys.exit(7)"],
                      capture_output=True, text=True)          # :39-43
proc.returncode                                                # == 7（:46-47）
```

- `0` = 成功，非 0 = 失败。**`< 0` 表示被信号杀死**（Python 用负号：`-9` = SIGKILL）。注意这与 shell 的 `137` 是**两套表示**：shell 做 `128+9`，Python 给 `-9`——写"透传退出码"逻辑时必须处理这个转换。
- **`run()` 不检查 returncode**（`:46-47` 的注释点明了）：它把子进程失败当成普通返回值。**忘了 `check=True` 就等于忘了检查。**

`check=True`（`:57-62`）：非 0 就抛 `subprocess.CalledProcessError`，异常里带着 `exc.returncode`（`:61`）和 `exc.cmd`（`:62`）。**这是"让失败无法被忽略"的 Python 版**——和 `docs/01-TDD与契约测试.md` 第五节讲的是同一件事：把"看起来是返回值"的东西变成"必须处理的异常"。

**透传退出码是 CLI 的生命线**（`04_subprocess.py:66-76`，`sys.exit(proc.returncode)` 见 `:75`；`:69` 构造了"2 passed, 1 failed"的假测试并 `sys.exit(1)`）：

> `:76` —— pytest / ruff / git 能被 CI 理解的原因：它们都说同一种语言。
> `:124-125` —— 一个 CLI 的生命线：读参数 → 调子进程 → 判定 returncode → 用自己的退出码汇报。中间任何一步把失败吞掉，上层（CI）就失去了拦截能力。

**为什么不要 `shell=True` 拼用户输入**（`:81-95`）：

```python
evil = "a; echo 我被注入了"                     # :81
subprocess.run(f"echo {evil}", shell=True)     # :84  ❌ 会执行两条命令
subprocess.run(["echo", evil])                 # :87-91 ✅ 原样传给 echo 一个参数
```

`shell=True` 把字符串交给 `/bin/sh -c`（Windows 上是 `cmd.exe /c`，`:95`），于是**分号、`&&`、反引号、`$()`、重定向全都成为语法**，用户输入里任何一个这样的字符都变成"执行指令"。这不是"要注意的事"，这是**注入漏洞的定义**。正确姿势：传 **list**；需要 shell 特性时只让写死的命令走 shell，把变量通过 `env=` 或位置参数传入；`shell=True` + `shlex.quote()` 仍容易出错，Windows 上更甚（两套转义规则）。spec-kit 把这条纪律**升级成 CI 门禁**：`spec-kit/pyproject.toml:87-95` 用 ruff 的 `S602/S604/S605` 锁死，注释写明"任何重新引入 `shell=True`（或 `os.system` / `popen2`）都必须用显式 `# noqa` 承认，让偏离在评审中可见"。

**为什么 `Popen` 要配 `python -u`**（`:100-106`）：

```python
subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE, text=True)
```

`-u` = unbuffered（作用于 stdin/stdout/stderr）。子进程 stdout 连到**管道**（不是 tty）时 Python 改用**块缓冲**（通常 4–8KB）：子进程"打了很多日志但不到 4KB"时日志**卡在缓冲区**里，父进程什么都读不到，直到进程退出才一次性涌出（`:112` 的注释就是这句）。等价开关：`PYTHONUNBUFFERED=1`、`flush=True`。**同类问题在 CI 里非常常见**：一个"看起来卡住"的 job 往往只是**缓冲**——诊断顺序是"先加 `-u`/`flush`，再怀疑死锁"。

## 九、编码是一个真实故障源

Windows 控制台默认代码页是 **GBK / cp1252**，不是 UTF-8。后果分两级：

- **一级**：`print("✓")` 直接抛 `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'`——**程序在打日志时崩溃**，纯粹的输出问题变成真实失败。
- **二级（更隐蔽）**：错误被捕获或 `errors` 设置不当时，**输出会从中间被截断**。spec-kit 踩过：`spec-kit/scripts/python/check_prerequisites.py:168-177` 的 docstring 记录，Windows 上 stdout 非控制台（管道/重定向）时回退到 ANSI 代码页，`✓` 在 cp1252 里不可编码，**报告从 "AVAILABLE_DOCS:" 那行开始被截断**——前半截看起来完全正常，后半截静默消失。**二级才真正危险**：不报错，你拿到的是"看起来完整"的输出。

三层防护：

#### ① 显式把 stdout 设成 UTF-8（能设就设）

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

`lab/module1-tdd/run_red_green_refactor.py:51-58` 的 `_force_utf8()` 对两个流都做。`errors="replace"` 保证**"编不出来的字符变成 `?`，而不是抛异常"**：用可读性换"绝不会因为日志而崩溃"，这是正确的交换。局限：`reconfigure` 要求 Python 3.7+ 且 stdout 是 `TextIOWrapper`，已被别的库包过或不是控制台时可能无效——所以还有下一层。

#### ② 探测 `sys.stdout.encoding` 后**降级字符集**（最实用）

`spec-kit/scripts/python/check_prerequisites.py:167-183`：

```python
def _status_marker(ok: bool) -> str:
    """✓ 能安全输出就输出 ✓，否则退回 [OK] / [FAIL]。"""
    glyph = "✓" if ok else "✗"                                          # :178
    try:
        glyph.encode(getattr(sys.stdout, "encoding", None) or "utf-8")   # :180
    except (LookupError, UnicodeEncodeError):                            # :182
        return "[OK]" if ok else "[FAIL]"
    return glyph
```

价值远超"处理 ✓/✗"：**`sys.stdout.encoding` 是判断"输出是否被重定向到文件/管道"的实用手法**。Python 启动时按"目标是什么"决定该值：交互式控制台 → 控制台代码页（Windows 上 cp936/cp1252）；重定向到文件或管道 → locale 偏好编码（Windows 上常是 cp1252/cp936，无 locale 的 Linux 容器里可能是 `ascii`）。因此 `isatty()` 判"是不是终端"，`encoding` 判"这个通道能编出什么字符"，从而决定**用不用花哨符号**。两者结合最好：终端上给 ✓/✗，管道里给纯 ASCII 的 `[OK]`/`[FAIL]`（下游解析器也更希望它是 ASCII）。

注意 `:180` 的 `or "utf-8"`：`encoding` 可能是 `None`（被某些包装器替换过），此时按 UTF-8 试——UTF-8 能编码 `✓`，所以结果是"乐观通过"。这是刻意默认：**能编就编，编不了才降级**。

另一个同源手法：`lab/module2-git/scripts/check_tests_touched.py:115-128` 的 `configure_streams()` **只改 `errors="replace"`、保留流自己的编码**（GBK 控制台仍能正常显示中文），并写下理由 "A guard that crashes is worse than a guard that prints '?'"。而 `:411-413` 的 `json.dumps(..., sort_keys=True)` 让 `ensure_ascii` 保持默认 True——**机器读的载荷保持纯 ASCII**，在任何控制台/管道/CI 日志里都能活。

#### ③ 跨平台脚本干脆只用 ASCII

最省事的一层：**不用 ✓ / ✗ / emoji / box-drawing**，改用 `[OK]` / `[FAIL]` / `->` / `==`。理由不止编码：各终端和日志聚合器对宽字符处理不同（对齐会乱）；日志会被 grep、被 `awk` 切列、被正则解析——ASCII 让这些简单。这与 `docs/02-Git工作流与钩子.md` 里路径 C-quote 的坑同理：**给程序看的东西不要用给人看的花样**。

优先级：**③ 作为默认；② 在必须好看的地方用；① 作为兜底。** 三者可以共存于同一个项目。

## 十、退出码设计原则

| 码 | 含义 | 谁用 |
|---|---|---|
| **0** | 成功 | 所有程序 |
| **1** | **业务失败**：请求处理了，结论是"不通过"/"没找到"/"不满足不变量" | 校验器、测试、检查脚本 |
| **2** | **用法错误 / 环境误用**：参数不对、缺依赖、用错了方式 | argparse、git、pytest、检查脚本 |
| 其他 | 具体失败类别 | 按需，且写进文档 |

现成例子：`spec-kit/.github/scripts/check_extension_version_bump.py:99-102` 参数个数不对 → stderr + `return 2`，不变量不满足 → `return 1`（`:106-109`），docstring 明说 "Exits 0 when all invariants hold, 1 otherwise"（`:31-35`）；`01_exit_codes.py:43-45` 业务失败用 **3**（刻意与"未捕获异常 → 1"区分开）；`lab/module2-git/scripts/check_tests_touched.py:13-20` 的三段契约完全同构（0 ALLOW / 1 BLOCK / 2 USAGE）。

**1 与 2 的分工为什么有价值**：调用方可据此分流——`1` 说明"检查跑了，结果是不通过"，该把人叫来看业务；`2` 说明"检查根本没跑对"，该修流水线。没有这个分工，运维面对"一直红"的 PR 只能靠读日志判断该找谁。

### 10.1 为什么"给每个失败原因分配一个退出码"常常是过度设计

- **空间小且不可扩展**：只有 0–255，`126/127/128+N` 已被含义占用；新增原因就要新增码，而**码一旦被 CI 依赖就再也改不了**（改码 = 破坏兼容），于是你会得到一份没有任何工具能校验的"退出码字典"。
- **信息量太差**：`exit 7` 无法携带"哪个文件、哪一行、期望什么、实际什么"——而这些恰好是人类和 LLM 修复问题所需的全部。需要粒度时，正确载体是**结构化输出**（JSON 报告、`::error::` 注解、SARIF）；退出码只承担一件事：**给机器一个二值（或三值）判定**。
- **反模式识别**：若一个脚本的文档需要一张"退出码对照表（1=缺文件、2=格式错、3=版本不匹配…）"，这张表**几乎从来不会被调用方完整实现**——调用方只会写 `if rc != 0`。你付出了复杂度，却没换来分流能力。

默认设计：`0` 成功 / `1` 业务失败 / `2` 用法或环境错误 / 其他只在调用方真的会区分时才引入。加分项（比多给退出码有用得多）：**失败时把结构化诊断写到 stderr**，一行一条、带字段——`check_tests_touched.py:354-359` 的 4 行 stderr 报告和 `:136-144` 的 `a, b, c (+7 more)` 摘要就是这个思路。

### 10.2 最后一条纪律

> **退出码是契约的一部分，和函数签名一样。** 改它、或者让它偶尔不返回，都是在破坏调用方——而调用方（CI）不会给你任何提示，它只是安静地变绿。

## 十一、自检清单

1. `126`、`127`、`130`、`137` 各是什么？为什么"命令没跑起来"要返回**非 0** 而不是 0？
2. 为什么"只有 0 是成功"比"非 0 表示失败"更有用？`if [ $? -ne 1 ]` 为什么是错的？
3. `cmd > file 2>&1` 与 `cmd 2>&1 > file` 的结果分别是什么？用 fd 展开顺序解释。
4. `false | tee log` 的退出码是多少？`set -o pipefail` 之后呢？`pipefail` 会带来什么新的假失败？
5. `set -e` 在 `if` 条件、`&&` 链、`!` 取反里分别怎样？为什么"我加了 `-e` 所以不会漏错"是错的？`pre-commit:48` 为什么故意把赋值写进 `if` 条件？
6. `local x=$(false)` 之后 `$?` 是多少？为什么？正确写法是什么？
7. `$(...)` 吃掉哪两样东西？`printf x` 哨兵修的是哪一样？`check-prerequisites.sh:186-187` 的 `exit "$status"` 修的是哪一样？`pre-commit:132-135` 为什么要 `set +e` / `status=$?` / `set -e`？
8. 为什么"先 `os.path.exists()` 再创建锁文件"是错的？`O_CREAT | O_EXCL` 解决了什么？锁文件的经典缺陷是什么，四种缓解手段的可靠度顺序如何？
9. 用 mtime 判断"要不要重建"会在这五种情况下出错——至少说出三种，并给一个替代方案。
10. `subprocess.run("cmd", shell=True)` 与传 list 在处理用户输入时有什么本质区别？`returncode == -9` 与 shell 的 `137` 是什么关系？
11. 管道里跑 `python script.py` 时日志为什么会卡住？加什么能修好？
12. 为什么 `sys.stdout.encoding` 能用来判断"输出是否被重定向"？据此降级字符集解决了什么问题（举 spec-kit 那个截断的例子）？为什么 `check_tests_touched.py` 的 JSON 载荷坚持纯 ASCII？
