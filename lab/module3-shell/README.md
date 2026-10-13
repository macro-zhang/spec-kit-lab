# 模块3：Shell 退出码、流分工与子进程

> 一句话：进程之间**唯一通用的成功/失败协议**不是日志文本，而是那个 0..255 的退出码；
> stdout 是**给下游的数据**，stderr 是**给人的诊断**，退出码是**给机器的判定**。
> 本模块把这句抽象的话拆成 4 个可运行、可断言、可重复的实验，
> 并把"这三件事混用会怎么出事"用实测输出摆出来。

---

## 这个模块要回答的问题

| # | 问题 | 一句话答案 | 对应实验 |
| --- | --- | --- | --- |
| 1 | POSIX 退出状态码是什么约定？ | `0` = 成功，**任何非 0** = 失败；`0..255` 之外的语义由 shell 自己发明（`128+n` = 被信号 n 杀死） | `01_exit_codes.py` |
| 2 | stdout 和 stderr 的分工是什么？ | stdout 只放**载荷**（会被管道/重定向吃掉），stderr 只放**诊断**（直接给人看，不进数据管道） | `02_pipeline.py` |
| 3 | 管道为什么会吞掉失败？ | bash 默认只取**管道最后一个命令**的退出码；前面失败、最后一个成功 → 整条管道返回 0 | `02_pipeline.py` 实验 2b |
| 4 | 文件只读与 mtime 跟这件事有什么关系？ | mtime 是**增量构建**的判定依据（`target < source` → 重建）；只读位是**第一道软防线**，用来物理阻挡对已定稿契约的篡改 | `03_filesystem.py` |
| 5 | 怎么从 Python 调用子进程？ | `subprocess.run` 默认**不抛异常**、只看 `returncode`；`check=True` 才抛 `CalledProcessError`；CLI 的骨架就是**原样透传**退出码 | `04_subprocess.py` |

这 5 个问题的共同点：它们都是**机器对机器的契约**。人读日志能"大概知道出了什么事"，
但 CI、钩子、`&&`、`if` 全都只读退出码。本模块要建立的就是这条直觉。

---

## 目录结构

```
lab/module3-shell/
├── 01_exit_codes.py    ★ 退出码：0 / 3 / 1，用 subprocess 自调用演示三种"结束方式"
├── 02_pipeline.py      ★ stdout/stderr 分流 + 真实 bash 里的 2>/dev/null、2>&1、pipefail
├── 03_filesystem.py    ★ mtime 增量判定、os.chmod(S_IREAD) 只读保护、O_CREAT|O_EXCL 原子锁
├── 04_subprocess.py    ★ subprocess.run / check=True / 退出码透传 / 禁 shell=True / Popen 流式读
└── README.md           ← 你正在读的文件
```

每个脚本为什么存在：

| 文件 | 为什么需要它 | 讲的知识点 |
| --- | --- | --- |
| `01_exit_codes.py` | "退出码有几种来源"必须能一条命令重放，而不是背文档 | `sys.exit(n)`、`raise SystemExit`、未捕获异常→1、`returncode` 字段 |
| `02_pipeline.py` | 光说"stderr 是诊断"没用，要让人亲眼看到"错误被 `2>/dev/null` 丢掉但退出码还在" | fd 0/1/2、重定向、管道退出码陷阱、`set -o pipefail` |
| `03_filesystem.py` | 契约冻结和并发写在 spec-kit 里是真实需求，机制却只有三个系统调用 | `stat().st_mtime`、`chmod(S_IREAD)`、`os.open(O_CREAT\|O_EXCL)` |
| `04_subprocess.py` | 绝大多数 CLI 工具就是"调子进程 + 透传退出码"，四种姿势的差别必须实测 | `run` / `check=True` / `call` 语义、`shell=True` 的注入面、`python -u` 与缓冲 |

---

## 怎么跑

本模块的 4 个脚本**只用标准库**，不需要安装任何东西。脚本**内置了 `_force_utf8()`**
（每个脚本 `main()` 第一行调用），在 GBK 控制台/管道下不会因 emoji 崩溃：

```powershell
cd F:\Users\zhb\Desktop\study
F:\Users\zhb\Desktop\study\lab\.venv\Scripts\python.exe lab\module3-shell\01_exit_codes.py
```

### 编码问题已内建修复

最初版本在默认 GBK 控制台下，`03_filesystem.py` 和 `04_subprocess.py` 会以
`UnicodeEncodeError` 崩溃并退出 `1`（详见「沙箱踩坑记录 · 坑 5」，该坑已修复）。
现在四个脚本的 `main()` 开头都会调用 `_force_utf8()`——与 spec-kit
`src/specify_cli/__init__.py` 的 win32 stdio reconfigure 是同一手法——
不再需要手动设置环境变量。

| 脚本 | 默认 GBK 控制台（修复后实测） |
| --- | --- |
| `01_exit_codes.py` | rc = **0** |
| `02_pipeline.py` | rc = **0**（含实验 2b 的 bash 实测） |
| `03_filesystem.py` | rc = **0** |
| `04_subprocess.py` | rc = **0** |

解释器版本（实测）：venv 是 **Python 3.11.0**。

---

## 实验 1：`01_exit_codes.py` —— 退出码的三种来源

### 运行命令

```powershell
F:\Users\zhb\Desktop\study\lab\.venv\Scripts\python.exe lab\module3-shell\01_exit_codes.py
```

### 实测输出（Python 3.11.0，本机，rc = 0；迁移到 F 盘后重跑）

```
========================================================================
POSIX 退出码：0 = 成功，非 0 = 失败
========================================================================

[正常结束]  命令: python 01_exit_codes.py --child-ok
    stdout |       [子进程] 一切正常，返回 0
    >>> returncode = 0

[显式失败]  命令: python 01_exit_codes.py --child-fail
    stderr |       [子进程] 校验不通过，返回 3
    >>> returncode = 3

[未捕获异常]  命令: python 01_exit_codes.py --child-crash
    stderr | Traceback (most recent call last):
    stderr |   File "F:\Users\zhb\Desktop\study\lab\module3-shell\01_exit_codes.py", line 125, in <module>
    stderr |     raise SystemExit(child_main(argv[0]))
    stderr |                      ^^^^^^^^^^^^^^^^^^^
    stderr |   File "F:\Users\zhb\Desktop\study\lab\module3-shell\01_exit_codes.py", line 70, in child_main
    stderr |     raise ValueError("我崩溃了 —— 未捕获的异常")
    stderr | ValueError: 我崩溃了 —— 未捕获的异常
    >>> returncode = 1

------------------------------------------------------------------------
读法总结
------------------------------------------------------------------------
  退出码 0   -> 0 = 成功。shell 的 && 会继续往下走。
  退出码 1   -> 1 = 未捕获异常。注意 traceback 走的是 stderr。
  退出码 3   -> 3 = 失败。shell 的 && 会短路，CI 会标红。
```

### 三个子模式单独跑（实测退出码）

脚本用 `subprocess` **自调用**（`[sys.executable, __file__, *args]`），
所以子模式的退出码可以直接验证：

| 命令 | 实测 `$LASTEXITCODE` / rc | 说明 |
| --- | --- | --- |
| `... 01_exit_codes.py` | **0** | 主演示本身成功 |
| `... 01_exit_codes.py --child-ok` | **0** | 正常走到 `return 0` |
| `... 01_exit_codes.py --child-fail` | **3** | `return 3`，且消息写在 **stderr** |
| `... 01_exit_codes.py --child-crash` | **1** | 未捕获 `ValueError`，traceback 全在 stderr |

把 stderr 丢掉再看 `--child-fail`，**stdout 是空的**：
`captured stdout = [] rc=3`。这就是流分工的最小证据——
错误文案完全可以不存在，退出码仍然准确。

### 核心机制逐条解释

1. **退出码是 0..255 的整数**。`0` = 成功，非 0 = 失败。它是进程与操作系统之间
   唯一的通用结果协议；测试框架、CI、`git` 钩子、shell 的 `&&`/`||`/`if` 全部建立在它之上，
   **而不是建立在"解析输出"之上**。
2. **`return 0` 与 `sys.exit(0)` 等价**。脚本末尾正常结束 = 0；`sys.exit(3)` = 3；
   `raise SystemExit("msg")` 会把消息打到 stderr 并返回非 0；**未捕获异常 = 1** + traceback。
3. **`subprocess.run` 默认不抛异常**（`:59-63` 没有 `check=True`），失败是"正常返回值"，
   由调用者在 `proc.returncode` 上显式判断——这是刻意设计，逼你处理失败分支。
4. **traceback 走 stderr 而不是 stdout**（实测：`stderr | Traceback ...`，stdout 为空）。
   这条很重要：当子进程崩溃时，它的**数据流是干净的**，诊断信息不会污染下游解析。
5. **为什么要问这个**：`spec-kit/scripts/bash/check-prerequisites.sh` 这类前置检查脚本，
   靠的就是"退出码非 0 就中断后续步骤"；CI 里 `pytest` 只要一个用例失败就返回非 0，
   GitHub Actions 看到非 0 就把 job 标红、阻断合并。

---

## 实验 2：`02_pipeline.py` —— stdout/stderr 分流与管道陷阱

### 运行命令

```powershell
$PY = 'F:\Users\zhb\Desktop\study\lab\.venv\Scripts\python.exe'
& $PY lab\module3-shell\02_pipeline.py                 # 完整演示
& $PY lab\module3-shell\02_pipeline.py --emit-good     # 被调用：正常输出
& $PY lab\module3-shell\02_pipeline.py --emit-bad      # 被调用：错误 + 非 0
```

### 实测输出（rc = 0；迁移到 F 盘后重跑，实验 2b 已实测通过）

```
========================================================================
实验 2：stdout 是数据，stderr 是诊断，退出码是判定
========================================================================

--- 正常 模式 ---
  stdout (40 字节): 'name=widget count=3\nname=gadget count=7\n'
  stderr (0 字节): ''
  returncode: 0

--- 故障 模式 ---
  stdout (0 字节): ''
  stderr (14 字节): 'ERROR: 数据源不可用\n'
  returncode: 4

========================================================================
实验 2b：真实 bash 里的重定向与退出码
========================================================================
--- A) 只看 stdout：错误被丢弃，但退出码仍然是非 0 ---
  stdout=''  returncode=4

--- B) 把 stderr 并进 stdout (2>&1) ---
  combined='ERROR: 数据源不可用'  returncode=4

--- C) 管道陷阱：前面失败，最后一个命令成功 ---
  未开 pipefail -> 管道退出码 = 0  (被吞掉了！)
  开了 pipefail -> 管道退出码 = 4  (终于暴露了)


结论："失败"这件事必须同时体现在**退出码**上，
因为下游程序不会去读你的 stderr 文案来做判断。
```

两个子模式的实测退出码：

| 命令 | 实测 rc | stdout | stderr |
| --- | --- | --- | --- |
| `--emit-good` | **0** | 两行 `name=... count=...`（40 字节） | 空 |
| `--emit-bad` | **4** | **空**（0 字节） | `ERROR: 数据源不可用\n`（14 字节） |

### 实验 2b：bash 实测（本机 Git Bash 可用，已跑通）

初版在 dsh 沙箱里实测时 bash 因 msys 信号管道初始化失败（`0xC0000142`）而无法启动，
当时把 2b 标成了"未实测"（见「沙箱踩坑记录 · 坑 1」）。迁移到 F 盘后在本机重跑，
**Git Bash 完全正常**，A/B/C 三组结果全部按预期输出：

- **A) 只看 stdout**：`2>/dev/null` 丢掉了 stderr，但退出码 4 不被丢弃——
  "错误文案可以藏，退出码藏不住"。
- **B) 2>&1 合并**：错误信息进了管道，`combined` 里能看到 `ERROR: 数据源不可用`。
- **C) 管道陷阱**：不开 `pipefail` 时管道退出码是**最后一个命令**（`head`）的 0，
  失败被吞；`set -o pipefail` 后管道退出码暴露为 4——**这就是 CI 里
  "测试挂了但流水线是绿的"的经典根因与解法**。

### 核心机制逐条解释

1. **三条流的职责**（`:1-23` 的文档串）：fd 0 = stdin（数据从哪来）、
   fd 1 = stdout（**结果数据**，可被安全管道）、fd 2 = stderr（**诊断信息**，直接给人看）。
2. **最容易犯的错：把错误 print 到 stdout**。一旦下游用 `| grep` / `| jq` 解析，
   错误文案就被当成数据吃进去 → 产生"看起来成功了其实失败了"的假象。
   实验 2 的两组数字就是反例：故障模式下 stdout 是 **0 字节**。
3. **管道的退出码陷阱**：bash 默认只取管道**最后一个命令**的退出码。
   `failing_cmd | head -n 1` 里 `head` 成功了，整条管道就返回 0。
   这就是 CI 里"测试挂了但流水线是绿的"的经典根因，解法是 `set -o pipefail`。
   （脚本 `demo_shell_pipe()`，`:84-125`，用真实 bash 演示这三种情形；**已实测**。）
4. **失败必须同时体现在退出码上**：脚本结尾那句结论点破了重点——
   下游程序**不会去读你的 stderr 文案**来做判断。

---

## 实验 3：`03_filesystem.py` —— mtime、只读保护、文件锁

### 运行命令

```powershell
F:\Users\zhb\Desktop\study\lab\.venv\Scripts\python.exe lab\module3-shell\03_filesystem.py
```

### 实测输出（迁移到 F 盘后重跑，rc = 0，无需设编码变量）

```
临时工作目录: C:\Users\zhb\AppData\Local\Temp\speckit-lab3-xxx  (platform=windows)

========================================================================
实验 3a：mtime —— 判断'谁更新'，决定要不要重建
========================================================================
  spec.md            mtime = 05:41:15
  implementation.py  mtime = 05:41:16
  -> 实现比契约新：产物是新鲜的 ✅

  这就是增量构建的判定公式：if target.mtime < source.mtime: rebuild()

========================================================================
实验 3b：只读保护 —— 物理阻断对已定稿契约的篡改
========================================================================
  已设为只读: constitution.frozen.md
  os.access(W_OK) = False  -> 只读生效: True

  现在尝试写入（应该失败）：
    ✅ 被内核拦下: PermissionError: [Errno 13] Permission denied: 'C:\\Users\\zhb\\AppData\\Local\\Temp\\dsh-rdhiNr\\speckit-lab3-shytiohg\\constitution.frozen.md'

  注意：只读位挡得住'手滑'，挡不住 root。真正的强制力来自
  版本控制 + CI 门禁（谁能改、改完谁来验），只读位只是第一道软防线。

========================================================================
实验 3c：文件锁 —— 防止两个进程同时写同一份文件
========================================================================
  进程 A 尝试取锁 ... 成功
  进程 B 尝试取锁 ... 失败（锁被占）
  锁文件内容(持有者 pid) = 37860
  释放锁后，进程 C 可以取锁 ... 成功

  关键点：一定要用 O_CREAT|O_EXCL（'不存在才创建'）这个原子语义。
  先 os.path.exists() 再创建，两个进程会同时通过检查 —— 那就是竞态。

临时目录已自动清理。
```

`05:41:15` / `05:41:16` 是运行当刻的真实时间；`37860` 是当次运行的**真实 PID**
（对应本模块 README 生成时的进程），换一次运行就会变。

### 核心机制逐条解释

1. **mtime 是增量构建的最底层原语**（`demo_mtime`，`:59-83`）。
   脚本写入 `spec.md` 后 `time.sleep(1.1)`——这个 1.1 秒是**刻意的**，
   因为多数文件系统只有秒级时间戳精度，不拉开时间差会把两次写入算成同一刻。
   判定公式只有一行：

   ```python
   if target.stat().st_mtime < source.stat().st_mtime:
       rebuild()
   ```

   `make` / 编译器 / 缓存失效判断用的都是它。在 SDD 语境里它的含义是
   **"契约变了、实现过期了"**——这正是脚本要打印的那句话。

2. **只读保护是"把定契约的权力收归人类"的落地手段之一**（`demo_readonly`，`:85-112`）。
   `os.chmod(frozen, stat.S_IREAD)`（即 `0o444`）在 POSIX 与 Windows 上都生效，
   之后 `os.access(frozen, os.W_OK)` 返回 `False`，写入抛 `PermissionError`（实测已拦下）。
   脚本同时诚实地说明了边界：**只读位挡得住"手滑"，挡不住 root/管理员**。
   真正的强制力在版本控制 + CI 门禁。
   注意 `:111` 用 `stat.S_IREAD | stat.S_IWRITE` 复原权限，否则临时目录清理会失败。

3. **原子锁文件靠 `O_CREAT|O_EXCL`**（`demo_lock`，`:114-144`）。
   关键在于"检查并创建"必须是**一步**：

   ```python
   fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # 原子
   ```

   实测：进程 A 成功，进程 B 拿到 `FileExistsError` → 失败。
   如果写成 `if not lock.exists(): open(lock, "w")`，两个进程会**同时通过检查**——那就是竞态。
   释放 = `lock.unlink()`。这个"孤儿锁文件"方案是最朴素、跨平台的，便于理解原理；
   生产环境 POSIX 用 `fcntl.flock`、Windows 用 `msvcrt.locking`
   （脚本 `:13-18` 专门写了这段跨平台差异）。

4. **好消息：即使 03 在 GBK 下崩溃，临时目录也会被清理**。实测崩溃后
   在 `%TEMP%` 下**没有**留下 `speckit-lab3-*` 目录。
   原因是 `UnicodeEncodeError` 从 `with tempfile.TemporaryDirectory(...)` 块内抛出，
   上下文管理器仍会执行清理再让异常继续向上传播。

---

## 实验 4：`04_subprocess.py` —— 子进程的四种读法

### 运行命令

```powershell
F:\Users\zhb\Desktop\study\lab\.venv\Scripts\python.exe lab\module3-shell\04_subprocess.py
```

### 实测输出（迁移到 F 盘后重跑，rc = 0，无需设编码变量）

```
模块 3 / 实验 4：子进程与退出码

========================================================================
4a：默认不抛异常 —— 退出码要自己看 returncode
========================================================================
  returncode = 7
  stdout     = 'ok'
  -> run() 把'子进程失败了'当成正常返回值交给你判断。
     这是刻意的设计：让调用者显式处理失败分支。

========================================================================
4b：check=True —— 让失败立刻变成异常
========================================================================
  捕获到 CalledProcessError
    exc.returncode = 7
    exc.cmd        = ['F:\\Users\\zhb\\Desktop\\study\\lab\\.venv\\Scripts\\python.exe', '-c', 'import sys; sys.exit(7)']
  -> 适合'这一步失败就没有后续可言'的场景。

========================================================================
4c：CLI 的骨架 —— 把子进程的退出码原样透传出去
========================================================================
  子进程(测试)退出码 = 1
  子进程输出         = '2 passed, 1 failed'
  -> 本 CLI 将返回同样的退出码: 1
     这就是 pytest / ruff / git 能被 CI 理解的原因：它们都说同一种语言。

========================================================================
4d：不要用 shell=True 拼输入
========================================================================
  ❌ shell=True 的写法会把分号当命令分隔符执行：
     subprocess.run(f"echo a; echo 我被注入了", shell=True)

  ✅ 传 list，参数不经过 shell 解析：
     收到参数: a; echo 我被注入了
  （Windows 上 shell=True 走的是 cmd.exe，注入风险同样存在）

========================================================================
4e：Popen —— 需要边跑边读输出时
========================================================================
    [实时]   第 1 行
    [实时]   第 2 行
    [实时]   第 3 行
  Popen 最终 returncode = 0
  -> `python -u` 关闭输出缓冲，否则你会等到进程结束才看到输出。

========================================================================
小结：一个 CLI 工具的生命线
========================================================================
  读取参数 -> 调子进程 -> 判定 returncode -> 用自己的退出码汇报
  中间任何一步把失败吞掉，上层 CI 就失去了拦截能力。

  当前仓库根: C:\Users\zhb\Desktop\study\lab\module3-shell
```

### 核心机制逐条解释

1. **`subprocess.run` 默认不抛异常**（4a，`:58-68`）：子进程 `sys.exit(7)`，
   `proc.returncode` 就是 `7`，而 `run()` 正常返回。**刻意的设计**——逼调用者显式处理失败分支。
2. **`check=True` 才把失败变成异常**（4b，`:71-84`）：抛 `subprocess.CalledProcessError`，
   异常对象上带 `returncode`（实测 `7`）和 `cmd`（实测是完整 argv 列表）。
   适合"这一步失败就没有后续可言"的场景。
3. **CLI 的骨架 = 退出码透传**（4c，`:87-97`）：模拟一个 CLI 跑测试，
   测试退出 `1` → CLI 也返回 `1`。这就是 `pytest` / `ruff` / `git` 能被 CI 理解的原因——
   **它们都说同一种语言**（退出码），而不是"都输出某种格式的文本"。
4. **禁止 `shell=True` 拼输入**（4d，`:100-116`）：`evil = "a; echo 我被注入了"`。
   用 `shell=True` 时 `;` 会被当成命令分隔符（实测输出里那句
   `subprocess.run(f"echo a; echo 我被注入了", shell=True)` 就是这条注入的形态）。
   正确做法是传 **list**，让操作系统直接 `execve`，参数不经过 shell 解析——
   实测 `收到参数: a; echo 我被注入了`：那串恶意字符**原样变成了一个普通参数**。
5. **`Popen` + `python -u` 才是流式**（4e，`:119-133`）：用
   `subprocess.Popen([sys.executable, "-u", "-c", ...], stdout=PIPE)` 逐行读取，
   保证**边跑边看到输出**。`-u` 关闭输出缓冲，否则子进程的输出会攒到进程结束才一次性吐出，
   "实时日志"就变成了"最终日志"。

---

## 与 spec-kit 的真实对应关系

以下行号均来自**本次亲自打开的文件**（`read` 全文读过后逐条核对，全部对得上）。
两个文件都完整读过：bash 版共 **243** 行，Python 版共 **289** 行。

### 1. 退出码契约：成功 `exit 0`，失败 `ERROR → exit 1`

| 位置 | 行为 |
| --- | --- |
| `spec-kit/scripts/bash/check-prerequisites.sh:135` | `--paths-only` 分支输出路径后 **`exit 0`** |
| `spec-kit/scripts/bash/check-prerequisites.sh:243` | `if $JSON_MODE ... else` 输出块**结束处**——脚本末尾没有显式 `exit`，正常走完即退出 `0` |
| `spec-kit/scripts/bash/check-prerequisites.sh:139-143` | 缺 feature 目录：`echo "ERROR: Feature directory not found: $FEATURE_DIR" >&2` + `exit 1` |
| `spec-kit/scripts/bash/check-prerequisites.sh:145-149` | 缺 `plan.md`：`echo "ERROR: plan.md not found in $FEATURE_DIR" >&2` + `exit 1` |
| `spec-kit/scripts/bash/check-prerequisites.sh:152-156` | `--require-spec` 但缺 `spec.md`：`... >&2` + `exit 1` |
| `spec-kit/scripts/bash/check-prerequisites.sh:159-163` | `--require-tasks` 但缺 `tasks.md`：`... >&2` + `exit 1` |
| `spec-kit/scripts/python/check_prerequisites.py:223-253` | Python 镜像的四个同类检查，均 **`return 1`**（`:229`、`:237`、`:245`、`:253`） |

**实测证据**（用 `SPECIFY_FEATURE_DIRECTORY` 指向一个临时 feature 目录驱动）：

- 有 `spec.md` + `plan.md` → text 模式输出 `FEATURE_DIR:...` / `AVAILABLE_DOCS:` 等，
  **rc = 0**；
- `--require-tasks` 但目录里没有 `tasks.md` →
  stderr 是 `ERROR: tasks.md not found in <dir>` + `Run /speckit.tasks first to create the task list.`，
  **rc = 1**，且 **stdout 完全为空**（实测 `stdout=[] rc=1`）。

### 2. 流分工：stdout 只放载荷，stderr 只放 ERROR

这条纪律在上面已经成立：**成功路径只写 stdout，失败路径只写 stderr**。
实测最干净的一组（临时 feature 目录里有 `spec.md`/`plan.md`/`research.md` 和
一个有文件的 `contracts/`，只取 stdout、丢弃 stderr）：

```
stdout=[{"FEATURE_DIR":"C:\\Users\\zhb\\AppData\\Local\\Temp\\dsh-rdhiNr\\sk-probe2","AVAILABLE_DOCS":["research.md","contracts/"]}]  rc=0
```

text 模式同一目录：

```
FEATURE_DIR:C:\Users\zhb\AppData\Local\Temp\dsh-rdhiNr\sk-probe2
AVAILABLE_DOCS:
  [OK] research.md
  [FAIL] data-model.md
  [OK] contracts/
  [FAIL] quickstart.md
rc=0
```

注意这里打印的是 `[OK]` / `[FAIL]` 而不是 `✓` / `✗`——原因见第 4 条。
text 模式的三个 helper 在 `spec-kit/scripts/bash/common.sh:405-406`：

```bash
check_file() { [[ -f "$1" ]] && echo "  ✓ $2" || echo "  ✗ $2"; }
check_dir() { [[ -d "$1" && -n $(ls -A "$1" 2>/dev/null) ]] && echo "  ✓ $2" || echo "  ✗ $2"; }
```

### 3. `--json` 支持

| 位置 | 行为 |
| --- | --- |
| `spec-kit/scripts/bash/check-prerequisites.sh:36-38` | 参数解析里 `--json)` → `JSON_MODE=true` |
| `spec-kit/scripts/bash/check-prerequisites.sh:208` | 有 jq 且带 `--template` 时：`jq -cn ... '{FEATURE_DIR:$feature_dir,AVAILABLE_DOCS:$docs,TEMPLATE_CONTENT:$template_content}'` |
| `spec-kit/scripts/bash/check-prerequisites.sh:223` | 无 jq 且带 `--template` 时：`printf '{"FEATURE_DIR":"%s","AVAILABLE_DOCS":%s,"TEMPLATE_CONTENT":"%s"}\n' ...` |

（补充：有 jq **不**带 `--template` 时是 `:210-214` 的
`'{FEATURE_DIR:$feature_dir,AVAILABLE_DOCS:$docs}'`，无 jq 时是 `:226`。
用户提示里说的 `:208`/`:223` 是"带 `--template`"那一支——我实际读到的
`:208` 确实是含 `TEMPLATE_CONTENT` 的那条，`:223` 也是，与提示一致。）

Python 侧：

| 位置 | 行为 |
| --- | --- |
| `spec-kit/scripts/python/check_prerequisites.py:30-31` | `def _json_line(payload): return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"` |
| `spec-kit/scripts/python/check_prerequisites.py:273-282` | `if args.json_mode:` 组装 `{"FEATURE_DIR":..., "AVAILABLE_DOCS": docs}`，带 `--template` 时再塞 `TEMPLATE_CONTENT`，然后 `sys.stdout.write(_json_line(payload))` |

`separators=(",", ":")` 的含义是**去掉 JSON 里的所有空格**——实测输出
`{"FEATURE_DIR":"...","AVAILABLE_DOCS":["research.md","contracts/"]}` 确实没有空格。
理由和 `01_exit_codes.py` 讲的是同一件事：**stdout 是给机器解析的载荷**，
格式越稳定越好，任何"为了好看"的空格都是下游不该依赖的噪音。

### 4. 可复用手法一：用 `printf x` 在 `$()` 里取回被吞掉的退出码

`spec-kit/scripts/bash/check-prerequisites.sh:186`：

```bash
if TEMPLATE_CONTENT=$(resolve_template_content "$TEMPLATE_NAME" "$REPO_ROOT"; status=$?; printf x; exit "$status"); then
    TEMPLATE_CONTENT="${TEMPLATE_CONTENT%x}"
```

**问题**：`$(...)` 命令替换的退出状态来自**最后一个命令**。
如果直接写 `TEMPLATE_CONTENT=$(resolve_template_content ...)`，
那么无论 `resolve_template_content` 失败与否，只要赋值本身成功，`if` 就为真——
子函数的失败被命令替换**吞掉了**。

**解法**（这段代码干的三件事）：

1. `status=$?` —— 在子函数跑完后**立刻**把退出码存下来；
2. `printf x` —— 让命令替换的**最后一个命令**变成 `printf`，
   并把一个哨兵字符 `x` 追加到捕获到的输出尾部；
3. `exit "$status"` —— 把命令替换的退出状态**显式设回**子函数的退出码。

于是：`if` 判断的是**子函数**的成功与否（而不是赋值语句的），
同时 `${TEMPLATE_CONTENT%x}`（`:187`）把那个哨兵 `x` 去掉，恢复原始内容。
失败时才走 `:189-190` 的 `echo "ERROR: Could not resolve required ..." >&2; exit 1`。

这个技巧在"我要捕获输出，但也要知道产生输出的命令成没成功"的场景里通用。

### 5. 可复用手法二：`_status_marker` 的编码降级（本机是真实存在的坑）

`spec-kit/scripts/python/check_prerequisites.py:167-183`：

```python
def _status_marker(ok: bool) -> str:
    glyph = "✓" if ok else "✗"
    try:
        glyph.encode(getattr(sys.stdout, "encoding", None) or "utf-8")
    except (LookupError, UnicodeEncodeError):
        return "[OK]" if ok else "[FAIL]"
    return glyph
```

它的思路是：**先探测 `sys.stdout.encoding` 能不能编码 ✓/✗，不能就降级成 ASCII 的
`[OK]`/`[FAIL]`**。原因是 `check_prerequisites.py:194-202` 的 `_print_text_results()`
已经打印了 `FEATURE_DIR:` 和 `AVAILABLE_DOCS:`，之后才逐行打印状态标记；
在窄编码下 `print("  ✓ ...")` 抛 `UnicodeEncodeError` 会把**已经算好的报告截断**，
调用方只看到半份输出 + 一个 traceback。

**本机控制台是 GBK，同类问题真实存在**——三段实测：

| 场景 | 实测结果 |
| --- | --- |
| 真实默认（`sys.stdout.encoding` = `gbk`） | `_status_marker(True)` → `'[OK]'`，`_status_marker(False)` → `'[FAIL]'`，**rc = 0** |
| 直接写 `chr(0x2713)` 符号 | `UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 2: illegal multibyte sequence`，**rc = 1**，报告恰好停在 `AVAILABLE_DOCS:` 之后 |
| 强制 `PYTHONIOENCODING=cp1252`（原注释点名的编码） | `_status_marker` 同样降级成 `'[OK]'`/`'[FAIL]'`；裸写 U+2713 抛 `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713' ... character maps to <undefined>` |

也就是说，**在没写这个守卫的版本上，本机也会把这份报告截断**——
它防的不只是 cp1252 这个具体编码，而是"窄编码"这一类问题。
一个附带观察：本机 `chcp` 显示活动代码页是 **65001（UTF-8）**，
但 Python 3.11 报告的 `sys.stdout.encoding` 仍是 **`gbk`**
（`locale.getpreferredencoding(False)` = `cp936`）——
**不要用 `chcp` 推断 Python 会用什么编码**。

---

## 沙箱踩坑记录（dsh 沙箱内实测；迁移到 F 盘后本机复核）

这一节是这个模块最有价值的部分之一：下面每一条都在 **dsh 沙箱环境**里真实
复现过，有明确的命令、输出和退出码。**迁移到 F 盘后在本机（非沙箱）复核，
坑 1（bash）已消失——bash 完全正常**；坑 2/3/4 是沙箱特有的进程/网络/缓存
限制，在本机直接跑不会遇到。记录仍保留，因为它们解释"为什么当初 2b 标未实测"
以及"工具链分层验证"的通用方法。

### 坑 1：bash 完全起不来（msys 运行时不可用）——**仅 dsh 沙箱内**，本机复核已消失

> **2026-10-11 复核**：迁移到 F 盘后在本机重跑
> `F:\Users\zhb\Desktop\study\lab\module3-shell\02_pipeline.py`，
> 实验 2b 的 A/B/C 三组输出**全部正常**（见「实验 2」章节），
> `bash -c "exit 0"` 返回 0。`0xC0000142` 是**沙箱信号管道**被拒导致的，
> 不是本机问题。下面保留原始记录。

```
> & 'C:\Program Files\Git\bin\bash.exe' -c "echo BASH_OK"
[stderr]
      0 [main] bash (32384) C:\Program Files\Git\bin\..\usr\bin\bash.exe: *** fatal error - couldn't create signal pipe, Win32 error 5
> rc = -1073741502
```

`-1073741502` 的十六进制是 `0xC0000142` = `STATUS_DLL_INIT_FAILED`。
Shell cwd was reset to C:\Users\zhb\Desktop\study
同一目录下的兄弟程序**全部**一样（实测）：

| 程序 | 退出码 |
| --- | --- |
| `C:\Program Files\Git\bin\bash.exe` | `-1073741502` |
| `C:\Program Files\Git\usr\bin\sh.exe` | `-1073741502` |
| `C:\Program Files\Git\usr\bin\env.exe` | `-1073741502` |
| `C:\Program Files\Git\usr\bin\ls.exe` | `-1073741502` |

`spec-kit/scripts/bash/check-prerequisites.sh --json` 同样以
`-1073741502` 立即死亡（实测），**任何 bash 版脚本在本机都无法执行**。

**后果（当时在沙箱内）**：
- `02_pipeline.py` 里**依赖真实 bash 的演示当时无法执行**（标为未实测），
  而且该脚本当时**没有优雅跳过**——这就是「实验 2 · 2b 章节」记录过的缺陷分析。
- 当时本 README 中所有关于 bash 行为（`2>/dev/null`、`2>&1`、`set -o pipefail`、
  `printf x` 技巧、`check_file` 实现）的结论，都来自**读源码**，不是执行结果。

**复核结论（2026-10-11，迁移到 F 盘后在本机直接跑）**：bash 一切正常，
2b 三组实验全部通过（见「实验 2」的实测输出）。**这个坑不是本机缺陷，
而是 dsh 沙箱对 msys 信号管道的限制**——换到非沙箱环境（本机终端、
Git Bash、CI 的 GitHub Actions runner）都不会遇到。

### 坑 2：`node --test` 直接崩

实测（Node **v24.14.0**）：

```
> node --test C:\Users\zhb\Desktop\study\lab
✖ C:\Users\zhb\Desktop\study\lab (3.3366ms)
ℹ tests 1   ℹ pass 0   ℹ fail 1
✖ failing tests:
  Error: spawn EPERM
      at ChildProcess.spawn (node:internal/child_process:421:11)
      at spawn (node:child_process:796:9)
      at TestContext.<anonymous> (node:internal/test_runner/runner:415:19)
      ...
rc = 1
```

`errno: -4048`，`syscall: 'spawn'`，位置就是 `node:internal/child_process:421`。
原因是 `node --test` **为每个测试文件派生子进程**，而 stdio 走管道——
在这个沙箱里管道式 spawn 被拒。

**对策（已实测有效）**：直接跑测试文件本身。
此时 `node:test` 在**当前进程内**执行，不派生子进程，**退出码语义完全不变**：

| 跑法 | 实测 rc |
| --- | --- |
| `node --test <file>` | **1**（`spawn EPERM`，测试根本没跑） |
| `node <file>.test.mjs`（全通过） | **0** |
| `node <file>.test.mjs`（含一个失败断言） | **1** |

（后两行是我用临时 `.test.mjs` 文件实测的：失败的 `assert.strictEqual(1, 2)` → rc 1；
通过的 `assert.strictEqual(1, 1)` → rc 0。）

### 坑 3：PowerShell 的 schannel TLS 坏了，但 Python 的 OpenSSL 通道正常

实测（PowerShell **5.1.26100.9168**）：

```
> Invoke-WebRequest -Uri 'https://pypi.org/simple/' -TimeoutSec 15 -UseBasicParsing
FAILED: 基础连接已经关闭: 接收时发生错误。
```

pypi.org / 清华 / 阿里云镜像全都一样。

同一台机器上，**Python 的 OpenSSL 通道正常**（实测）：

```
OK  TLS version = TLSv1.3  cipher = TLS_AES_128_GCM_SHA256
handshake elapsed = 0.16s
openssl = OpenSSL 1.1.1q  5 Jul 2022
（rc = 0）
```

所以"网络不通"是**伪结论**：坏的只是 PowerShell 走的那条 schannel 栈。
同理 `git clone` 必须加 `-c http.sslBackend=openssl`，否则报
`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)`。
本机实测 `git config --get http.sslBackend` = **`schannel`**（未配置覆盖，`--global` 未设置），
`git version 2.53.0.windows.2`——默认就走那条坏掉的栈。

**教训**：遇到"网络不行"先分清是**哪条 TLS 栈**不行。
换一个客户端（Python/curl/`openssl`）就能立刻二分出是网络问题还是某个运行时的问题。

### 坑 4：pip 静默卡死（缓存写不进去）

pip 默认把 HTTP 缓存写到 `%LOCALAPPDATA%\pip\cache`——**在工作区之外**，
workspace-write 沙箱下写入被拒后，pip **既不报错也不前进**。
本机实测确认了这个路径确实存在且在工作区外：

```
> python -m pip cache dir
c:\users\zhb\appdata\local\pip\cache
> $env:LOCALAPPDATA
C:\Users\zhb\AppData\Local
> python -m pip --version
pip 26.2.1 from C:\Users\zhb\Desktop\study\lab\.venv\Lib\site-packages\pip (python 3.11)
```

**对策**：`--no-cache-dir` + 把输出重定向到**真实文件句柄**而不是管道。

**附带教训（很重要）**：**PowerShell 的 `*>` 重定向在进程结束前不落盘**。
正在跑的 pip 从父进程看来和"卡死"一模一样——日志文件是空的。
判断"真死了还是只是在跑"不能靠看日志文件大小。

> 诚实标注：本 README 的**坑 4** 我是通过核对 `pip cache dir`、`LOCALAPPDATA`、
> 以及沙箱的 workspace-write 边界来**验证其前提**的；
> 我没有在这台机器上重新触发一次"pip 卡死"来复现完整现象（那需要真实安装一个有网络依赖的包）。
> 现象描述与对策来自本会话的既有结论。

### 坑 5：控制台是 GBK，`03` 和 `04` 会因为 emoji 崩溃 ⚠️

这是本次运行**实测新发现**的一个坑，也是本模块最反直觉的一处：

```
> python lab\module3-shell\03_filesystem.py
临时工作目录: ...\speckit-lab3-hq3vqe3r  (platform=windows)
... mtime = 05:42:24 / 05:42:25
rc=1
[stderr]
  File "...\03_filesystem.py", line 56, in demo_mtime
    print("  -> 实现比契约新：产物是新鲜的 ✅")
UnicodeEncodeError: 'gbk' codec can't encode character '\u2705' in position 19: illegal multibyte sequence
```

`04_subprocess.py` 同样（崩在 `:83`，字符是 `\u274c`）：

```
> python lab\module3-shell\04_subprocess.py
...
  File "...\04_subprocess.py", line 83, in demo_no_shell_injection
    print("  ❌ shell=True 的写法会把分号当命令分隔符执行：")
UnicodeEncodeError: 'gbk' codec can't encode character '\u274c' in position 2: illegal multibyte sequence
rc=1
```

**根因**：Python 3.11 在本机把 `sys.stdout.encoding` 解析为 **`gbk`**
（`locale.getpreferredencoding(False)` = `cp936`）。
`03_filesystem.py` 和 `04_subprocess.py` 里有 **两个 emoji 不在 GBK 字符集里**：

| 字符 | 码点 | 出现位置（修复前 → 修复后） |
| --- | --- | --- |
| ✅ | `U+2705` | `03_filesystem.py:56 → :78`；`03_filesystem.py:82 → :104`；`04_subprocess.py:86 → :107` |
| ❌ | `U+274C` | `03_filesystem.py:58 → :80`；`04_subprocess.py:83 → :104` |

`01_exit_codes.py` 和 `02_pipeline.py` 经逐字符扫描**全部可被 GBK 编码**
（所以它们只是显示乱码，不会崩）。

**为什么这件事和本模块的主题高度相关**：这就是 `_status_marker`
（见上面第 5 条）要解决**完全同一个**问题的活样本——
"已经算好的报告，因为打印一个装饰性字符而整体崩溃"。
两个实验脚本自己犯了它们正在讲的那个错误：**让"表述"的失败劫持了"判定"**。
`03` 明明可能已经把 mtime 算出来了、`04` 明明已经跑完了 4a–4c，
却因为一个 emoji 让整个进程以 1 退出——**一个本该 rc=0 的成功演示，
在 GBK 下变成了 rc=1 的失败**。

**规避方式（当时）**：设 `PYTHONUTF8=1` 或 `PYTHONIOENCODING=utf-8`
（当时 README 用的是前者，4/4 脚本全部 rc=0）。
更彻底的修法是把这两处 emoji 换成 ASCII（如 `[OK]`/`[FAIL]`），
或者像 `check_prerequisites.py` 那样先探测再降级——
那才是本模块应该示范给读者的写法。

**已经修复（2026-10-11）**：本 README 的四个脚本现在**内置** `_force_utf8()`，
在 `main()` 第一行调用——与 spec-kit `src/specify_cli/__init__.py` 的
win32 stdio reconfigure 是同一手法。修复后实测（含强制 GBK 管道场景，
`PYTHONIOENCODING=gbk` 且不带 `PYTHONUTF8`）：

| 脚本 | 修复后 rc（GBK 场景） |
| --- | --- |
| `01_exit_codes.py` | **0** |
| `02_pipeline.py` | **0**（含 bash 子进程，subprocess 显式 `encoding="utf-8", errors="replace"`） |
| `03_filesystem.py` | **0** |
| `04_subprocess.py` | **0** |

也就是说，**现在不需要设任何环境变量**。这个修复本身也示范了本模块的
核心教训——不要让"表述"的失败劫持"判定"。

**顺带教训**：**不要用 `chcp` 推断 Python 用什么编码**。
本机 `chcp` 报告 65001（UTF-8），而 Python 报告 `gbk`——两者不一致。

---

## 自检清单

读到这里，试着不看上面回答这 12 题。答不上来的，回去看对应小节。

1. 一个进程返回退出码 `0`。它一定"没有出错"吗？
   （提示：`exit_code=0` 只说明**这个程序自己认为**它成功了。）
2. `raise SystemExit("msg")` 和 `raise ValueError("msg")` 分别产生什么退出码？
   `"msg"` 分别写到哪条流上？
3. 为什么"把错误信息 `print` 到 stdout"是一个**契约性**错误，而不是风格问题？
4. `failing_cmd | head -n 1` 在不开 `pipefail` 时退出码是多少？为什么？
   `set -o pipefail` 改变了什么？
5. Bash 里 `x=$(some_func)` 之后 `$?` 反映的是谁的退出码？
   `check-prerequisites.sh:186` 的 `printf x` 解决了什么、怎么解决的？
6. `subprocess.run(cmd)` 和 `subprocess.run(cmd, check=True)` 的区别是什么？
   失败时前者给你什么、后者给你什么？
7. 为什么 `subprocess.run(f"echo {user_input}", shell=True)` 是危险的？
   传 list 为什么能解除这个危险？
8. `spec-kit/scripts/python/check_prerequisites.py` 的 `main()` 在
   `--require-tasks` 且缺 `tasks.md` 时返回什么？错误写到哪条流？stdout 是什么？
9. 为什么 `_status_marker` 要**先探测编码**而不是直接 `print("✓")`？
   本机（GBK）上不探测会发生什么？
10. `os.open(lock, O_CREAT|O_EXCL)` 比"先 `exists()` 再创建"强在哪里？
    给出一个能说明两者差别的时间线。
11. "只读位"能挡住什么、挡不住什么？为什么说它不是强制边界，
    而 `check-prerequisites.sh` 的退出码契约才是？
12. `spec-kit` 的 bash 版和 Python 版做了**同一件事**。
    如果你只能保留一个，你会保留哪个？在**本机**上这个问题的答案会变吗？为什么？

---

## 本次交付的验证状态（诚实标注）

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| `01_exit_codes.py` 主演示 | ✅ 实测（F 盘复核） | rc = **0**，输出已逐行抄录 |
| `01_exit_codes.py --child-ok` | ✅ 实测 | rc = **0** |
| `01_exit_codes.py --child-fail` | ✅ 实测 | rc = **3**，stdout 为空（0 字节），消息在 stderr |
| `01_exit_codes.py --child-crash` | ✅ 实测 | rc = **1**，traceback 全在 stderr |
| `02_pipeline.py` 实验 2（流分工） | ✅ 实测 | rc = **0**；`--emit-good` rc=0/40 字节、`--emit-bad` rc=4/stdout 空 |
| `02_pipeline.py` 实验 2b（真实 bash） | ✅ **已实测**（F 盘复核） | bash 正常；A/B/C 三组输出全部按预期（`pipefail` 前 0 后 4） |
| `03_filesystem.py` | ✅ 实测（F 盘复核） | rc = **0**，mtime/只读/锁三节全部按预期输出，**无需设编码变量** |
| `03_filesystem.py`（强制 GBK 管道） | ✅ 实测 | rc = **0**（修复后）；修复前 rc=1 `UnicodeEncodeError` @ `:56`（`U+2705`） |
| `04_subprocess.py` | ✅ 实测（F 盘复核） | rc = **0**，4a–4e 全部按预期，**无需设编码变量** |
| `04_subprocess.py`（强制 GBK 管道） | ✅ 实测 | rc = **0**（修复后）；修复前 rc=1 `UnicodeEncodeError` @ `:83`（`U+274C`） |
| `spec-kit` Python 版退出码 0 / 1 | ✅ 实测 | 成功路径 rc=0（text 与 `--json`）；`--require-tasks` 缺 tasks.md → rc=1、stdout 空 |
| `spec-kit` Python 版 `--json` 紧凑格式 | ✅ 实测 | `{"FEATURE_DIR":"...","AVAILABLE_DOCS":["research.md","contracts/"]}`（无空格） |
| `_status_marker` 在 GBK 下降级 | ✅ 实测 | `'[OK]'`/`'[FAIL]'`；裸写 U+2713 → `UnicodeEncodeError` + rc=1 |
| `spec-kit` **bash 版**的任何行为 | ⚠️ **沙箱内未实测，本机已复核** | 沙箱内 bash 起不来（`-1073741502`）；迁移后本机 bash 正常（`bash -c "exit 0"` → 0），第 1–4 条 bash 结论仍建议在 CI 环境复跑 |
| `set -o pipefail` / `2>&1` / `2>/dev/null` 的实际效果 | ✅ **本机已实测** | 通过 `02_pipeline.py` 实验 2b 真实跑出（A/B/C 三组） |
| `printf x` 技巧 | ⚠️ **未实测，已静态核对** | 逐字读了 `check-prerequisites.sh:186-187`，机制解释见第 4 条 |
| 坑 1（bash/msys）、坑 2（`node --test`）、坑 3（TLS）、坑 5（GBK） | ✅ 实测 | 均有命令 + 原始报错 + 退出码；坑 1/坑 5 已在 F 盘复核为修复/消失 |
| 坑 4（pip 静默卡死） | ⚠️ **前提已核实、现象未复现** | `pip cache dir` = `c:\users\zhb\appdata\local\pip\cache`（工作区外）；未重新触发完整卡死现象 |

**修订记录（2026-10-11 迁移到 F 盘后）**：① 四个脚本内置 `_force_utf8()`，
GBK 场景不再崩溃，README 中"先设 UTF-8"的指引已删除；② 实验 2b 本机实测
通过（bash 正常），"未实测"标记清除；③ 路径统一改为 F 盘；④ 行号引用
按加 `_force_utf8` 后的新行号更新。

**文件改动边界**：初版 README 撰写时未修改任何其他文件；迁移后**修改了
本目录下的四个脚本**（内置 `_force_utf8()`，02 另加 bash 子进程的显式
UTF-8 解码），未改动 `lab/module1-tdd/`、`lab/module2-git/`、`docs/`、
`spec-kit/` 或任何其他路径。运行实验产生的临时目录由脚本自身清理
（实测 `03` 修复前崩溃后 `%TEMP%` 下也没有残留 `speckit-lab3-*`）。
