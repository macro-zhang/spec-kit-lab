# 模块1：TDD 与契约测试

## 这个模块要证明什么

一句话：**把「什么叫做对了」从人的主观判断，变成一段会返回非 0 退出码的程序。**

具体拆成三个可验证的命题：

1. **红灯必须是有效的红灯** —— 测试失败的原因必须是"断言不成立"，而不是"模块根本没实现好到能跑"。
   两者在 pytest 里都显示红色，但只有前者能证明测试有效。
2. **绿灯只证明"契约被满足"** —— 不证明代码漂亮，也不证明它没被别的输入打穿。
3. **契约是双向的、并且可以被"冻结"** —— 冻结的那一份必须和代码里的定义保持一致，
   而"保持一致"这件事本身也要有测试来守。

---

## 目录结构

```
module1-tdd/
├── pyproject.toml                     pytest 配置（pythonpath / testpaths / addopts / markers）
├── contracts/
│   └── user-profile.schema.json       【冻结的契约】跨语言、跨进程的对外承诺
├── src/calc/
│   ├── __init__.py                    公开出口（只导出 parse_duration 与 UserProfile）
│   ├── contracts.py                   【代码化的契约】Pydantic 模型
│   └── core.py                        ⚠️ 由驱动器生成/覆盖，是三个变体之一的副本
├── variants/
│   ├── core_red.py                    红灯版：只有骨架，调用即抛 NotImplementedError
│   ├── core_green.py                  绿灯版：最笨但正确
│   └── core_refactored.py             重构版：行为不变，结构更直接
├── tests/
│   ├── test_duration.py               行为测试：8 正例 + 10 负例 + 非字符串
│   ├── test_contract_pydantic.py      契约测试（代码侧）
│   └── test_contract_schema.py        契约测试（JSON Schema 侧）+ 防漂移
├── run_red_green_refactor.py          【驱动器】把三阶段跑一遍，并自检
└── node/                              Node 补充：零依赖，等价的 Red-Green-Refactor
```

---

## 怎么跑

```powershell
# 一次性准备
python -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install --no-cache-dir pytest pydantic jsonschema

# 跑全部测试
..\.venv\Scripts\python.exe -m pytest -q

# 跑 Red-Green-Refactor 演示（推荐先跑这个）
..\.venv\Scripts\python.exe run_red_green_refactor.py
```

Node 补充（不需要 `npm install`，零依赖）：

```powershell
cd node
node run-rgr.mjs                       # 三阶段演示
node test/duration.test.mjs            # 行为测试
node test/contract.test.mjs            # 契约测试
```

> **注意**：上面用 `node test/xxx.test.mjs` 而**不是** `node --test`。
> 原因见文末「沙箱踩坑记录」——`node --test` 在本环境会 `spawn EPERM`。

---

## 三个变体在讲什么

| 变体 | 它证明的事 | 关键代码 |
|---|---|---|
| `variants/core_red.py` | **测试真的在测东西**。它抛 `NotImplementedError("RED：尚未实现")`，19 个测试全红。如果这里就是绿的，说明测试是空的 | 整个函数体一行 `raise` |
| `variants/core_green.py` | **达成契约的最短路径**。正则 `(\d+)([dhms])` 抓片段，再拼回原文比对 —— 朴素，但正确 | `reconstructed != text` 这一票否决 |
| `variants/core_refactored.py` | **结构手术不伤行为**。用 `\A(?P<segments>(?:\d+[dhms])+)\Z` 一次判定整串合法，再 `finditer` 累加 | 不合法即压根匹配不上 |

重构那一步的意义在于：**改完之后你不需要重新论证正确性**，跑一遍测试就知道了。
这就是"有测试兜底"和"没有测试兜底"在心理成本上的差别。

---

## 契约的两侧

契约在这份实验台里被写了**三遍**，这是刻意的：

| 形态 | 位置 | 谁消费它 |
|---|---|---|
| 机器可读文件 | `contracts/user-profile.schema.json` | 跨语言 / 跨进程的调用方 |
| 代码类型 | `src/calc/contracts.py` 的 `UserProfile` | Python 代码内部 |
| 可执行断言 | `tests/test_contract_*.py` | CI |

三个最关键的设计点：

### 1. `extra="forbid"` —— 这是压制幻觉的核心开关

```python
model_config = ConfigDict(extra="forbid", strict=True)
```

- `extra="forbid"`：Pydantic 默认是 `ignore`，也就是**静默丢弃**你没声明的字段。
  模型幻觉最典型的形态之一就是"自作主张多写一个字段"（`nickname` 而不是 `username`），
  默认行为会让它一声不吭地通过，错误被推迟到消费端才爆。
  改成 `forbid` 之后，多余字段变成一条硬错误 `extra_forbidden`。
- `strict=True`：Pydantic 默认是 lax 模式，会把 `"42"` **静默强转**成 `42`。
  在"模型生成的数据"这个语境里，强转是敌人而不是朋友 —— 它把"类型不对"
  这个明确信号抹平成"看起来没问题"。

### 2. 冻结的那份必须和代码不漂移，而这件事要有测试

`tests/test_contract_schema.py::test_schema_does_not_drift_from_code`
把 JSON Schema 和 `UserProfile.model_json_schema()` 对比，**只比语义骨架**：

- `required` 集合
- 每个字段的 `type`
- `role` 的 `enum`
- 两边的 `additionalProperties is False`

**刻意不做逐字比对**。逐字比对会因为 `title` / `$defs` / 键顺序这些无关噪音天天报红，
最后大家就把这个测试删掉了 —— 那才是真正的失败。契约测试要盯的是**承诺**，不是**排版**。

### 3. 契约测试和单元测试不是一回事

| | 单元测试 | 契约测试 |
|---|---|---|
| 验收对象 | 实现的行为对不对 | 接口的**形状**对不对 |
| 依赖实现吗 | 依赖 | **不依赖** |
| 重构后要不要改 | 可能要 | 不应该 |
| 典型的失败信息 | "期望 5400，实际 3600" | "多了个字段 / 类型不对 / 少了必填项" |

---

## 📌 一次真实的红灯：本实验台自己抓到的事故

这个模块第一次跑 `pytest` 时是 **2 failed**，而且两个都是**真问题**，不是环境噪音。
留在这里当作最有说服力的教学材料：

### 事故 1：冻结的 schema 和代码漂移了

```
AssertionError: 必填字段集合漂移了：
  schema=['email', 'id', 'role', 'tags', 'username'] vs code=['email', 'id', 'username']
```

原因：`UserProfile` 里 `role` 和 `tags` **有默认值**，所以 Pydantic 认为它们对调用方是可选的；
而冻结的 `user-profile.schema.json` 却把它们列进了 `required`。
更荒谬的是它同时给 `required` 的 `role` 写了 `"default": "member"` —— **required 和 default 自相矛盾**。

修法：让 schema 跟随代码（有默认值 = 可省略），`required` 收敛为 `["id", "username", "email"]`。

> 注意修的方向：**不是删掉那条断言**。断言是对的，代码库是错的。
> 一个"红了就删"的团队，最后会得到一套全绿但什么都没保证的测试。

### 事故 2：Pydantic 的 lax 模式放过了 `"42"`

```
Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>
```

`tests/test_contract_pydantic.py` 里有一条用例断言 `id="42"` 必须被拒绝，
但 Pydantic v2 默认把 `"42"` 强转成了 `42`，于是根本没有异常。

修法：给 `model_config` 加 `strict=True`。

> 这条正好是本模块最想传达的观点：**类型系统的价值取决于它有多严**。
> 一个会自动替你"修好"错误输入的类型系统，恰恰是最危险的那种 ——
> 它让你误以为校验发生了。

---

## 与 spec-kit 的对应关系（⚠️ 别误引）

| 本实验台 | spec-kit 实际做法 |
|---|---|
| 用 `jsonschema` 库校验 JSON Schema | **不用 jsonschema**。实测 `spec-kit/tests/contract/` 里搜 `jsonschema` / `Draft` / `check_schema` **零命中** |
| schema 是机器可读的 `.json` | schema 本体是 **markdown 文档**（`contracts/*.schema.md`），见 `spec-kit/tests/contract/test_manifest_schema.py:2-4` |
| 校验失败抛 `ValidationError` | 校验入口返回错误清单 `list[str]`：`BundleManifest.from_dict(data).structural_errors()` |
| 用 Pydantic 做运行时守卫 | pydantic 只在 MCP 模块出现，不用于契约校验 |

**两条路线唯一重要的共同点**：都必须有一个**独立的执行器**。
没有执行器的 schema，无论是 markdown 还是 JSON，都只是一份没人遵守的愿望。
这也是本实验台故意走"另一条路"的原因 —— 让你看清格式不是重点，执行才是。

可以直接从 spec-kit 搬走的三类契约用例（`tests/contract/`）：

1. **`or {}` 把 falsy 非映射吞掉** → 参数化 `[[], "", 0, False]` 必须仍然报错
   （`test_manifest_schema.py:197-214`、`test_catalog_schema.py:408-419`）
2. **YAML 显式 null（`author:` 后面留空）必须读成 `""`**，而不是字符串 `"None"`
   （`test_manifest_schema.py:29-51`、`:272-300`）
3. **id 与字典键不一致必须报错**（`test_catalog_schema.py:357-362`）

第 1 条在 Node 侧也有对应实现，见 `node/test/contract.test.mjs` 里对
`[[], "", 0, false, null, undefined, 42]` 的参数化。

---

## Node 补充：为什么零依赖

`node/` 下**没有 `npm install` 这一步**，用的是 Node 内置的 `node:test` + `node:assert/strict`。
理由：

- 想让你先看清**测试框架的原生能力边界**，再决定要不要引入 jest/vitest。
  `node --test` 已经能收集用例、参数化、报告、返回退出码 —— 这些是全部必需品。
- 避免 `node_modules` 的版本噪音盖住真正要学的东西。

Node 侧同时演示了三个 JS 特有的坑：

1. **全局正则是有状态的**。`/(\d+)([dhms])/g` 带 `g` 标志后 `lastIndex` 会跨调用残留，
   导致同一个输入时对时错。测试里专门有一条回归用例守这个
   （`node/test/duration.test.mjs` 的 `回归：连续调用不受全局正则 lastIndex 残留影响`）。
2. **`typeof null === "object"`**。所以判"是不是普通对象"必须显式排除 `null` 和数组，
   见 `node/src/profile.mjs` 的 `isPlainObject`。
3. **参数化循环里用 `assert.ok(errors.some(...))` 而不是 `assert.equal(errors[0], ...)`** ——
   前者不依赖错误清单的顺序。顺序依赖会让测试在无关重构后假红。

---

## 沙箱踩坑记录（本机特有，但值得知道）

本实验台所在环境禁止创建**命名管道**。这导致两个看起来毫不相干的报错，其实是同一个病根：

| 表现 | 真实原因 |
|---|---|
| `node --test` → `Error: spawn EPERM  errno: -4048` | `node --test` 为每个测试文件派生**子进程**，子进程 stdio 走命名管道 |
| Git Bash 启动即 `fatal error - couldn't create signal pipe, Win32 error 5` | Cygwin/MSYS 启动时建信号管道 |
| `pip install` 静默卡死、日志 0 字节 | pip 把 HTTP 缓存写到**工作区之外**的 `%LOCALAPPDATA%\pip\cache`，写入被拒后既不报错也不前进 |

三个对策（都已经写进代码）：

1. 直接跑测试文件 `node test/duration.test.mjs`，**不用** `node --test`。
   直接跑时 `node:test` 在**本进程内**执行，不派生任何子进程，退出码语义完全一样。
2. 子进程输出重定向到**真实的文件描述符**，而不是默认的 `stdio: 'pipe'`。
   见 `node/run-rgr.mjs` 里用 `openSync` + `stdio: ["ignore", fd, fd]` 的那段。
3. pip 加 `--no-cache-dir`。见 `../_pip_install.py`。

> 顺带一提，PowerShell 的 `*>` 重定向在进程结束前**不会落盘**，
> 所以一个正在跑的 `pip install` 从父进程看起来和卡死一模一样。
> 排查这类"假死"时，先确认你到底有没有真的看到输出通道。

---

## 自检清单

答得上来就说明这个模块掌握了：

1. 一个红的测试，在什么情况下是"无效红灯"？举两个具体例子。
2. 为什么 `--strict-markers` 值得开？它和"测试是否通过"有关系吗？
3. Pydantic 的 `extra="ignore"`（默认）为什么会放大模型幻觉的危害？
4. `strict=True` 和 `extra="forbid"` 分别拦的是哪一类错误？
5. 为什么 `test_schema_does_not_drift_from_code` 只比语义骨架，不做逐字比对？
6. 契约测试和单元测试的边界在哪里？重构实现后，哪一个通常**不该**改？
7. spec-kit 用什么执行它的契约？为什么说"格式不重要、执行器才重要"？
8. 本模块的 `role` 字段为什么不在 JSON Schema 的 `required` 里？
9. Node 侧那条 `lastIndex` 回归测试，防的是一个什么样的 bug？
10. 如果一个测试断言 `assert parse_duration("abc")` 不抛异常，它能证明什么？不能证明什么？
