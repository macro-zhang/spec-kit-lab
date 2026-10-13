# 01 · TDD 与契约测试

> 对应实验台：`lab/module1-tdd/`。文中每个行号都可直接跳到编辑器里核对。
> 实测环境：Python 3.11.0 + pytest 9.1.1 + pydantic 2.14.0 + jsonschema 4.26.0（都装在同一虚拟环境 `lab/.venv` 里）。
> **状态**：本文写完后，实验台里两个真实失败（契约漂移 + lax 模式放行 `"42"`）已被修复，现在全绿。
> §八 保留了那场事故的完整记录——它是本文最有价值的一节，因为它示范了「红了之后该怎么修」。

---

## 一、Red-Green-Refactor 的精确定义

### 1.1 三阶段各自的「什么算完成」

| 阶段 | 这一阶段只做一件事 | 完成判据 | 反例（做了不算完成） |
|---|---|---|---|
| 🔴 RED | 写测试，**让实现留空** | 跑一次，**目标用例因为断言不成立而失败** | 因为 import 报错而失败；因为根本没收集到用例 |
| 🟢 GREEN | 用**最笨但正确**的办法让目标用例变绿 | 目标用例变绿 | 顺手做了抽象、抽了基类（那是 REFACTOR 的事） |
| 🔵 REFACTOR | **行为一字不改**，只改结构 | 重构前后，同一批用例同样地全绿 | 重构时顺手"修了一个 bug"（测试没变而实现变了行为） |

实验台把这三步真的跑了一遍：`lab/module1-tdd/run_red_green_refactor.py` 是驱动器，它把 `variants/<变体>.py` 逐个复制成 `src/calc/core.py`，再开子进程跑 pytest 回收退出码。

- `run_red_green_refactor.py:30` → `CORE_PY = HERE / "src" / "calc" / "core.py"`
- `run_red_green_refactor.py:33-37` → `STAGES` 表，把"期望"写成了数据：
  ```python
  ("🔴 RED      —— 只有骨架，测试必须失败", "core_red.py", False),
  ("🟢 GREEN    —— 最笨的实现，测试必须通过", "core_green.py", True),
  ("🔵 REFACTOR —— 改结构不改行为，仍须通过", "core_refactored.py", True),
  ```
- `run_red_green_refactor.py:89` → `shutil.copyfile(source, CORE_PY)`（变体换入）
- `run_red_green_refactor.py:94` → `passed = proc.returncode == 0`（**唯一判据是退出码**）

三个变体文件本身：
- RED：`lab/module1-tdd/variants/core_red.py:13-21`，`parse_duration` 只有 docstring 加一句 `raise NotImplementedError("RED：尚未实现")`（`:21`）。
- GREEN：`lab/module1-tdd/variants/core_green.py:19-32`。特征是"够用就好"：`_TOKEN = re.compile(r"(\d+)([dhms])")`（`:16`）一次性抓出所有片段，再把片段 `"".join(...)` 拼回原文比对（`:28-30`）——不一致就说明夹了垃圾字符。朴素，但对测试覆盖到的行为是正确的。
- REFACTOR：`lab/module1-tdd/variants/core_refactored.py:20-23` 换成命名分组的 `_DURATION`/`_SEGMENT` 两个正则，`:33` 用 `_DURATION.fullmatch(text) is None` 整体拒绝首尾垃圾，`:36-39` 用 `finditer` 求和。

### 1.2 为什么「先红」是必须的

如果测试在实现之前就是绿的，说明这个测试没在测任何东西（例如断言写成了 `assert True`，或者断言的对象恒等于期望值）。**先跑一次确认它是红的，是在验证「测试有效」这件事本身**。

这条规则的反面价值更大：它排除了"以为在测、其实没测"的测试。这类测试在 CI 里永远是绿的，是最贵的一种技术债。

顺带一个实测细节：RED 阶段**不是全红**。用 `core_red.py` 跑出来是 `21 failed, 22 passed`。那 22 个通过的是契约测试和与 `parse_duration` 无关的用例。判据是**目标用例红**，不是"所有用例红"。

### 1.3 红灯的两种来源 —— 只有一种是有效红灯（重点）

| 现象 | pytest 汇总行 | 退出码（实测） | 有效红灯？ |
|---|---|---|---|
| `assert parse_duration("45s") == 45` 不成立 | `1 failed` | **1** | ✅ 是 |
| 骨架 `raise NotImplementedError` | `1 failed` | **1** | ✅ 是（骨架阶段的标准做法） |
| `from calc import parse_durations`（名字打错） | `ERROR ...` + `Interrupted: 1 error during collection` | **2** | ❌ 否 |
| 语法错误 `SyntaxError` | 同上，collection error | **2** | ❌ 否 |
| marker 未注册 + `--strict-markers` | `ERROR ... not found in markers` | **2** | ❌ 否 |
| 一个用例都没收集到 | `no tests ran` | **5** | ❌ 否 |

**为什么会误判**：三种情况在终端上都是红的。肉眼分不出，连 `if [ $? -ne 0 ]` 也分不出 —— 1 和 2 都是非 0。区别在失败信息的语义：

- **有效红灯**：被测代码**被执行了**，断言做出了否定判断。它证明了「测试 → 实现」这条链路是通的，失败指向业务逻辑。
- **无效红灯**：被测代码**根本没被执行**。这次运行测的是环境。此时去写实现，你是在猜；即使实现写对了，测试依旧红，你还会怀疑实现。

**可操作的判据**：看 pytest 输出的最后一行。`N failed` 才是有效红灯；`N error` / `no tests ran` 都是环境问题——**先修环境，再进 GREEN**。

把这个误判落到实验台上，两个具体触发点：

1. 把 `lab/module1-tdd/tests/test_duration.py:12` 的 `from calc import parse_duration` 改成 `parse_durations`（多一个 s）→ 收集期 ImportError → 退出码 2。屏幕上 19 个 duration 用例"一个都没跑通"，看起来红得不能再红，但它提供的信息量是 0。
2. `lab/module1-tdd/src/calc/__init__.py:3-4` 从 `calc.core` 导入 `parse_duration`；而 `src/calc/core.py` **是驱动器产出的文件**（`run_red_green_refactor.py:30, 89`）。清掉它之后 `import calc` 直接 ImportError → 退出码 2，而不是 1。

### 1.4 驱动器本身也是一次测试

`run_red_green_refactor.py` 把"期望"写进 `STAGES`（`:33-37`），把"实际"从退出码读出来（`:94`），不一致就记账（`:99-102`），有账就 `return 1`（`:105-109`）——**脚本自己遵守同一个契约，所以可以直接挂进 CI**。`:113-119` 的结语是整个实验台的论点：

> 红灯证明测试有效（不是永远为真的空断言）；绿灯证明实现达成了契约；重构仍绿证明结构手术没有伤到行为。三步之间，Agent 只有「填实现」的自由，没有「改判卷标准」的自由。

---

## 二、pytest 的工作模型，与 `pyproject.toml` 逐键对照

### 2.1 收集（collection）

pytest 启动 → 读配置 → 从 `testpaths` 开始扫描 → 按命名约定收 `test_*.py` 里的 `test_*` 函数。

- `lab/module1-tdd/pyproject.toml:12` → `testpaths = ["tests"]`
- 命名约定三项（`python_files` / `python_classes` / `python_functions`）实验台没写，用默认值。spec-kit 把默认值显式写了出来：`spec-kit/pyproject.toml:69-71`。显式写的好处是"约定"从隐式知识变成可见配置。

关键认识：**收集期会执行模块顶层代码**。所以 import 错误在收集期爆、而不是在断言期爆——这正是 1.3 里那两类红灯的物理来源。

### 2.2 `pythonpath` —— 为什么需要它

`lab/module1-tdd/pyproject.toml:11` → `pythonpath = ["src"]`，`:9-10` 的注释写了理由：把 `src/` 加进 import 路径，`import calc` 才能找到源码；等价于旧式在 `tests/` 里塞 `conftest.py` 做 `sys.path` 操作。

为什么是必须的：源码布局是 `src/calc/`，而测试写的是 `from calc import parse_duration`（`tests/test_duration.py:12`）。不加 `pythonpath` 就是 ModuleNotFoundError → 收集错误 → 退出码 2 → 典型的"环境红灯被当成测试红灯"。

替代方案及取舍：`pip install -e .` 也能达到同样效果，但需要构建后端 + 安装步骤；`pythonpath` 是 pytest 原生配置，零安装。实验台选了后者。

### 2.3 fixture 生命周期

`lab/module1-tdd/tests/test_contract_schema.py:36-38`：

```python
@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
```

- `scope="module"`：整个模块只读一次磁盘，模块内所有用例共享同一个 dict（该模块共 10 个用例）。默认 scope 是 `function`（每个用例一次）——对只读操作是纯浪费。
- 生命周期四件事：setup（进入用例前）→ 按参数名注入 → 用例执行 → teardown（`yield` 之后的代码）。这里没有 `yield`，所以没有 teardown。
- 消费方式是**参数名注入**：`:45` `def test_schema_itself_is_valid(schema: dict[str, Any])`、`:50`、`:68`、`:74`。pytest 靠参数名 `schema` 匹配 fixture 名——名字对不上就是 fixture 找不到错误（又是一次收集错误）。

### 2.4 参数化：把「契约条款」写成表

`lab/module1-tdd/tests/test_duration.py:15-37` 正例：`@pytest.mark.parametrize(("text", "expected"), [...8 条...], ids=[...])`。8 条 → 8 个独立用例，一条失败不影响其余——这是它能给出精确失败原因的前提。

`lab/module1-tdd/tests/test_duration.py:42-68` 负例：10 条非法输入，配合 `:76-77` 的 `with pytest.raises(ValueError):`。`:70-74` 的 docstring 说明了为什么负例和正例同等重要：

> 只测"正确输入能得到正确结果"的测试是半个测试：它完全放行"对任何输入都返回 0" 这种荒谬实现。必须同时规定**什么必须失败**。

另外两处手法：`tests/test_contract_pydantic.py:34-46` 用三元组 `(field, bad_value, why)`（`why` 只作文档，给读报告的人看）；`tests/test_contract_schema.py:55-67` 用 `mutate` 函数列表参数化（每个 lambda 改坏一个字段），`:64` 的 `{k: v for k, v in p.items() if k != "email"}` 对应「缺必填」——**负例不止"值错"，还包括"字段缺失"**。

`ids=` 的价值：默认 id 是 `text45s-45` 这种机器串，中文 ids 让 `-ra` 的失败摘要直接可读（pytest 9 会把非 ASCII id 转义成 `[\u4e2d\u95f4\u7a7a\u767d]` 输出，属正常行为）。

### 2.5 marker 与 `--strict-markers`

- 声明处：`lab/module1-tdd/pyproject.toml:16-18` → `markers = ["contract: 契约测试 —— 校验对外承诺的输入输出形状"]`
- 使用处：`tests/test_contract_pydantic.py:10` 与 `tests/test_contract_schema.py:22` 都是模块级 `pytestmark = pytest.mark.contract`
- 用途：`pytest -m contract` 只跑契约，`pytest -m "not contract"` 只跑行为测试。

`addopts` 里的 `--strict-markers`（`pyproject.toml:15`）是关键：**未声明的 marker 直接变成收集错误**。实测对比：

实测：未注册 marker + 不带 `--strict-markers` → `1 passed, 1 warning`，**exit=0**；带上它 → `ERROR ... Failed: 'contract' not found in markers configuration option`，exit=2。

为什么这个开关重要：marker 名字写错（例如 `@pytest.mark.contracts`）时，警告模式下滑稽地"通过"了；而 CI 用 `-m contract` 过滤时那个用例根本不会被选中 —— 你会得到**覆盖率为零的假绿**，而且没有任何一处报警。strict 把这类手滑从"警告"升级成"硬失败"。

### 2.6 `addopts` 逐项

`lab/module1-tdd/pyproject.toml:13-15` → `addopts = "-ra --strict-markers --tb=short"`

| 键 | 作用 | 为什么需要它 |
|---|---|---|
| `-ra` | 结尾打印所有非通过用例的简短原因（含 xfail/skip） | 没有它，skip/xfail 的原因要往上翻日志 |
| `--strict-markers` | 未注册 marker → 收集错误 | 见 2.5，防假绿 |
| `--tb=short` | traceback 只留 `文件:行号` + 异常行 | 让**失败摘要**成为主要读物，决定 CI 里定位问题要 30 秒还是 3 分钟 |

对照：`spec-kit/pyproject.toml:72-76` 用 `-v --strict-markers --tb=short`。多一个 `-v` 是因为它的 pytest job 跑 3 OS × 2 Python = 6 个组合（`docs/04-spec-kit架构拆解.md:214`），verbose 输出便于横向比对。

---

## 三、退出码 0/1 是测试与环境的唯一接口

### 3.1 CI 只看退出码

GitHub Actions 里 `run:` 步骤退出非 0 → 该 step 失败 → job 失败 → 必需状态检查失败 → 阻断合并。**它不读 pytest 的 stdout 来判断"是不是真失败"**。由此推出两个结论：

1. 「测试跑不起来」（收集错误，exit 2）与「测试失败」（exit 1）**对人类是两件事，对 CI 是同一件事**——都是非 0，都是"红"。CI 没有能力也没有义务分辨。所以分辨这件事的责任在**你**，在 1.3 那张表里。
2. exit 5（一个用例都没收集到）同样是非 0。测试目录被误删、`testpaths` 写错，都会以"红"的形式暴露出来——这是好事：**宁可假红，不可假绿**。

反向的危险：**如果测试进程不返回非 0，CI 只能看到绿**。任何"把失败吞掉"的写法（管道取最后一个命令的退出码、`|| true`、`continue-on-error`）都是在拆掉这道门。

spec-kit 的做法是**双通道**：非 0 退出码 + stderr 上的 `ERROR:` 文本。例如 `spec-kit/scripts/bash/check-prerequisites.sh:140-142`：先 `echo "ERROR: Feature directory not found: $FEATURE_DIR" >&2`，再 `exit 1`。文本给人和 agent 看，退出码给机器判定。实验台镜像了同一手法：`lab/module3-shell/01_exit_codes.py:43-45` 在 `CHILD_FAIL` 分支 `print(..., file=sys.stderr)` 后 `return 3`。

### 3.2 「把警告升级成错误」为什么重要

警告的默认语义是"我猜你不在意"。但在门禁语境里，警告是**无声的失败**：

- 警告不改变退出码 → CI 绿 → 问题被合入版本库。
- pytest 里同族开关：`--strict-markers`（2.5）、`-W error`、`filterwarnings` 配置项。

一个同构的、很值得偷师的例子：`spec-kit/pyproject.toml:87-95` 用 ruff 的 `extend-select = ["S602", "S604", "S605"]` 把 `shell=True` 锁成"必须显式 `# noqa` 才能合入"。`:88-90` 的注释说明了设计意图：

> Lock in subprocess security posture: any reintroduction of shell=True (or os.system / popen2) must be acknowledged with an explicit `# noqa` pointing at the rule, making the deviation visible in review.

同一思想的两种落地：**把"默许"变成"必须显式声明"**。默认静默 = 没人会注意；强制显式 = 每次偏离都要留痕。

### 3.3 退出码实测表（pytest 9.1.1）

`0` 全部通过 ｜ `1` 收集成功但有用例失败 ｜ `2` 收集期出错（import / 语法 / marker / 参数） ｜ `4` 命令行用法错误（路径不存在） ｜ `5` 没收集到任何用例（`testpaths` 指向空目录）。

判读规则一句话：**先看最后一行是 `N failed` 还是 `N error` / `no tests ran`**——前者去改实现，后者去改环境。

---

## 四、契约的四种形态：能在什么时点捕获错误

| 形态 | 载体 | 捕获时点 | 表达力 | 典型场景 |
|---|---|---|---|---|
| TypeScript `interface` | `.ts` 源码 | **编译期**（`tsc`、编辑器实时） | 中：结构、可选性、联合类型、泛型；**运行时零校验** | 前端 / Node 内部模块边界；前后端共享类型的首选 |
| JSON Schema | 独立 `.json` 文件 | **校验期**（显式调用校验器时） | 强：`additionalProperties`、`pattern`、`minimum`/`maxItems`、`enum`、`$ref`、`if/then` | 跨语言 / 跨进程边界、配置文件、数据交换格式 |
| Pydantic | Python 类 | **校验期**（构造 / `model_validate`），并进入运行期 | 强：类型 + `Field` 约束 + 自定义 validator + 嵌套模型 + 序列化 | Python 服务内部的数据边界、请求/响应模型 |
| OpenAPI | `.yaml` / `.json` 文档 | **文档期** +（配合工具才有的）校验期 | 最强也最笨重：路由、参数、请求体、响应、错误码 | HTTP API 的对外契约；代码生成与文档 |

三个要点：① **时点越早越便宜**（编译期 > 校验期 > 文档期；一次编译期报错 1 秒解决，一次线上数据错要一天）；② **表达力 ≠ 可执行性**（一份 OpenAPI 文档若没人生成客户端、没人做请求校验，实际捕获能力是 **0**）；③ **只有"有独立执行器"的形态才真正拦得住东西**。

spec-kit 的实证印证了第 ③ 条：它的契约本体是 **markdown**（`spec-kit/tests/contract/test_manifest_schema.py:3` 的 "Mirrors contracts/bundle-manifest.schema.md"），执行器是手写校验函数（`CatalogEntry.from_dict(...)`、`structural_errors()`），详见 `docs/04-spec-kit架构拆解.md:288-315`——**工具不重要，独立验证才重要**。

---

## 五、为什么静态类型与严格 schema 能压制模型幻觉（重点）

### 5.1 失败模式不是「语法错」

LLM 生成的代码几乎不会语法错。它错在**接口漂移**：凭空发明一个字段名、把 `int` 写成 `str`、漏掉必填项、返回一个调用方根本没约定的结构。这些在语法上完全合法，跑起来"看起来也对"，只在消费端炸。

`lab/module1-tdd/src/calc/contracts.py:3-12` 的 docstring 把这条讲得比我短：

> LLM 生成代码时，最大的失效模式不是"语法错"，而是**接口漂移**……语法完全合法，运行到线上才炸。

### 5.2 机制：把「看起来差不多」变成一次确定性报错

契约的作用**不是**让模型更聪明，而是**改变错误的可见性**：

- 没有契约时，错误的表现是"输出怪怪的"——需要人来判断。而人在长会话里最先丧失的就是判断力，也最容易接受模型的自我评价。
- 有契约时，错误的表现是一个**确定性的异常**。确定性意味着它**不可争辩**：模型可以说"我已经正确实现了"，但 `ValidationError` 不会同意。
- 这正是 `contracts.py:10-12` 那句话的意思：把"什么算做对了"从 Agent 的自我评价里剥离出来，交给确定性代码判定。

换个说法：类型/schema 不提高模型一次做对的概率，它**把"做错了但看不出来"这个状态从系统里删除**。

### 5.3 两种用法：约束生成 vs 事后校验

**用法 A：约束生成（schema 进提示词）**

把 schema 贴进 prompt，要求模型"按这个结构输出"。优点是一次成型率高。缺点有三条，且都是结构性的：

- 模型可以**无视**提示词。它没有被强制——schema 在提示词里只是一段自然语言上下文。
- 无法验证"它遵守了"。你只能采样、观察、得出"感觉它遵守得还行"。
- 对长 schema 无效：模型会缩写、会省略深层嵌套字段、会给"合理"的缺省值。

**用法 B：事后校验（生成 → 校验 → 失败重试）**

- 模型可以无视提示词，但**不能无视校验器**。校验器是代码，不是请求。
- 循环有明确的终止条件：校验通过。这是确定性判据，不依赖"模型说它好了"。
- 失败信息是机器生成的（字段路径 + 错误类型），回灌给模型的定位精度远高于"再试试"。

实测（pydantic 2.14.0，对照 `contracts.py:52` 那一行）：

```python
Loose(BaseModel):  username: str
Loose.model_validate({"username": "a", "user_name": "B"}).model_dump()   # -> {'username': 'a'}   多余的 user_name 静默消失
Strict(extra='forbid'):  username: str
Strict.model_validate({"username": "a", "user_name": "B"})               # -> ValidationError: extra_forbidden @ ('user_name',)
```

`strict=True` 演示的是同一件事的另一半——**连"类型差不多"也不放过**：

```python
Lax(BaseModel):     id: int
Lax.model_validate({"id": "42"}).id            # -> 42         字符串被静默强转成整数，校验"通过"了
Strict(strict=True): id: int
Strict.model_validate({"id": "42"})            # -> ValidationError: int_type
```

前者输出**看起来完全正常**，你没有任何理由去查；后者才是能被当作反馈信号的东西。这两条合起来才是完整的"事后校验"：**多余的字段拦掉，类型不对的也拦掉。**

**一句话结论**：约束生成是"请求模型别犯错"，事后校验是"让错误无法隐藏"。前者提高概率，后者保证可见性。工程上必须先有后者，再谈前者。

### 5.4 落地顺序

1. **先定义契约**（schema / Pydantic 模型）。这是人类的工作，也是整个流程里唯一不该交给 Agent 的工作。
2. 写契约测试：正例放行 + 负例拦截。
3. Agent 只在契约允许的空间里生成实现。
4. 校验失败的报错**原样回灌**，且不允许"绕过校验"（比如加 `# type: ignore`、改 schema 去迁就实现）。

---

## 六、Pydantic 与 JSON Schema 的分工

一句话：**同一份承诺的两种载体**。代码内部用 Pydantic（能用 Python 的表达力，校验与类型提示合一）；跨语言 / 跨进程边界用 JSON Schema（任何语言都能读，不依赖 Python 运行时）。

### 6.1 Pydantic 侧：`lab/module1-tdd/src/calc/contracts.py`

| 行 | 内容 | 负责什么 |
|---|---|---|
| `:39`, `:52` | `class UserProfile(BaseModel)` + `model_config = ConfigDict(extra="forbid", strict=True)` | 拒绝多余字段 + 拒绝隐式强转（见 6.2） |
| `:54` | `id: Annotated[int, Field(gt=0, description="用户 ID，必须为正整数")]` | 类型 + 数值下界 + 文档 |
| `:55` | `username: Annotated[str, Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_]+$")]` | 类型 + 长度 + 字符集 |
| `:56` | `email: Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")]` | 形状（正则） |
| `:57` | `role: Literal["admin", "member", "guest"] = "member"` | 封闭枚举 + 默认值 |
| `:58` | `tags: list[str] = Field(default_factory=list, max_length=10)` | 容器类型 + 元素类型 + 长度 |
| `:60-66` | `@field_validator("tags")` → 每个 tag 必须等于其小写形式 | **跨项业务规则** |
| `:69-76` | `class ProfilePage(BaseModel)`：`total: Annotated[int, Field(ge=0)]` + `items: list[UserProfile]` | 嵌套契约，嵌套层同样被校验 |

`model_config` 与 `Field(default_factory=list)` 分别是"模型级配置"与"字段级配置"的范式：能用声明式表达就绝不用命令式代码（原因见 6.3 的表尾）。

### 6.2 `extra="forbid"` 为什么是关键一行

Pydantic 默认是 `extra="ignore"`：**静默丢弃**多余字段。后果具体化：拼错字段名（把 `username` 写成 `fullname`）→ 字段被静默丢弃 → 取默认值或缺失 → 错误推迟到消费端才炸，因果已隔好几层；而幻觉最常见的形态恰好就是"自作主张多写一个字段"（`contracts.py:57-58` 的注释、`tests/test_contract_pydantic.py:53-59` 的 docstring 都点了这条）。**默认行为等于给幻觉一个不会被发现的藏身处**：它的输出看起来完全正常。

打开 forbid（`contracts.py:52`）后，"多塞字段"从静默容忍变成硬错误 `extra_forbidden`（实测见 5.3）。

**同一行上还有第二个开关：`strict=True`**（Pydantic 默认 `strict=False`，即 lax 模式）。它拦的是另一类错误：**看起来对但类型不对**。默认 lax 会把 `"42"` 强转成 `42`、把 `"true"` 强转成 `True`。在"模型生成的数据"这个语境里，强转是敌人不是朋友——它恰好把"类型不对"这个明确信号抹平成"看起来没问题"（这正是 §八 第 2 条那场真实事故）。

实验台对这个开关的测试写得很讲究：`tests/test_contract_pydantic.py:53-65` 不只断言"抛了异常"，还断言错误的具体形状 ——

```python
errors = excinfo.value.errors()
assert errors[0]["type"] == "extra_forbidden"   # :64
assert errors[0]["loc"] == ("nickname",)        # :65
```

**断言错误的身份，而不只是断言"有错"**。这样即使将来 Pydantic 把类型合并了、或者这条错误被别的错误抢先，测试也会红。

JSON Schema 侧的同一个开关：`lab/module1-tdd/contracts/user-profile.schema.json:7` → `"additionalProperties": false`；对应的负例是 `tests/test_contract_schema.py:63` 的 `lambda p: {**p, "nickname": "多余字段"}`（ids 里叫「多余字段」，`:66`）。防漂移测试还专门盯着这个开关必须两侧都为 `False`：`tests/test_contract_schema.py:110-111`。

### 6.3 `Literal` 枚举 vs `field_validator`：各管哪一类校验

| 手段 | 管什么 | 本实验台的例 | 失败时的错误类型 |
|---|---|---|---|
| `Literal[...]` | 取值集合是**有限封闭集** | `role ∈ {admin, member, guest}`，`contracts.py:39` | `literal_error` |
| `Field(pattern=...)` | 单个字符串的**形状**（正则） | `username` / `email`，`contracts.py:37-38` | `string_pattern_mismatch` |
| `Field(gt= / ge= / min_length= / max_length=)` | 数值与长度**边界** | `id`（`gt=0`）、`username`（3..32）、`tags`（`max_length=10`），`contracts.py:36-40` | `greater_than` / `too_short` / … |
| `@field_validator` | 上面三者都表达不了的**业务规则** | `tags` 全部小写，`contracts.py:42-48` | `value_error`（带自定义 msg） |

判断标准：**能用声明式（`Literal` / `Field`）表达的就别写 validator**。原因是硬性的——

> 声明式约束会**自动进入 JSON Schema**（`model_json_schema()` 能导出 `enum` / `pattern` / `minimum` / `maxItems`），而 `@field_validator` 的函数体是**导不出去的**。

这是这个文件里最重要的一条工程取舍，也是 6.5 里那份漂移测试抓不到某些东西的根本原因。凡是希望"跨语言也成立"的规则，都必须用声明式写在字段上。

### 6.4 JSON Schema 侧：`lab/module1-tdd/contracts/user-profile.schema.json`

| 行 | 内容 |
|---|---|
| `:2-3` | `$schema: draft 2020-12`、`$id`（版本化的坐标） |
| `:6-7` | `type: object`、`additionalProperties: false` |
| `:8` | `required: ["id","username","email"]` —— **只有三项**，因为 `role`/`tags` 在代码里有默认值（见 §八 第 1 条） |
| `:10-14` | `id`：`integer` + `minimum: 1` |
| `:15-20` | `username`：`minLength 3` / `maxLength 32` / `pattern ^[a-z0-9_]+$` |
| `:21-24` | `email`：`pattern` |
| `:25-30` | `role`：`enum` + `"default": "member"` + 一句说明——**「可省略；省略时由实现补 'member'。故不在 required 里。」** |
| `:31-39` | `tags`：`array` + `"default": []` + `maxItems 10` + 元素 `pattern ^[a-z0-9_-]+$` |

这份文件自己的合法性也被测了：`tests/test_contract_schema.py:45-47` 调用 `Draft202012Validator.check_schema(schema)`。理由（`:46` 注释）：**schema 首先必须自己合法，否则它校验不了任何东西**。然后才是 `:50-52` 正例放行、`:55-71` 负例拦截、`:74-111` 防漂移。

### 6.5 两份契约会不会漂移：只比语义骨架

> **本节那条"实际是失败的"警告已经过期**——漂移已被修复，测试现在通过。
> 失败的现场记录保留在 §八，因为它是这一节最有力的论据。

`lab/module1-tdd/tests/test_contract_schema.py:74-111` 的 `test_schema_does_not_drift_from_code` 逐条比对的是：

| 行 | 比对内容 |
|---|---|
| `:87` | `generated = UserProfile.model_json_schema()`（从代码生成一份） |
| `:89-92` | `required` 集合必须相等 |
| `:94-95` | generated 的每个必填字段必须存在于 `schema["properties"]` |
| `:98-100` | `role` 的 `enum` 集合必须相等 |
| `:103-107` | 两侧都有 `type` 的字段，`type` 必须相等 |
| `:110-111` | 两侧 `additionalProperties` 都必须是 `False` |

**为什么刻意只比语义骨架、不做逐字比对**——`:77-86` 的注释解释说：Pydantic 生成的 schema 带 `title`、`$defs` 等实现细节，逐字比对会因无关噪音天天报红，最后大家就把这个测试删了 —— 那才是真正的失败；所以只比对**契约的语义骨架**（必填项集合 + 每个字段的类型），骨架一致 = 契约一致，其余是实现细节。

这也是通用的测试设计原则：逐字比对会让任何格式化改动（键顺序、缩进、`title` 文案）甚至 Pydantic 小版本升级都报红 → 报红次数 > 真实问题次数 → **报警疲劳** → 测试被删或被 `skip`。而**一个被忽略的契约测试比没有契约测试更糟**（它提供虚假的安全感）。契约测试要盯的是**承诺**（required 集合 / 字段类型 / 枚举取值 / 是否拒绝多余字段），不是**排版**。同一原则在 spec-kit 里也能看到：它校验的是 catalog / manifest 的**形状不变量**，而非文件字节内容（`docs/04-spec-kit架构拆解.md:295-315`）。

✅ **这条测试曾经真的红过，而且红得很对**——它抓到了一处真实漂移（两份契约对"role/tags 是否必填"的承诺相反）。完整事故记录与修法见 §八 第 1 条。这也是"防漂移测试"价值的最好证明：如果没有它，这条矛盾会一直躺在版本库里，直到某个跨语言的调用方踩上去。

## 七、契约测试 vs 单元测试

| 维度 | 单元测试 | 契约测试 |
|---|---|---|
| 验收对象 | **实现的正确性**（算法、边界、分支、错误路径） | **接口的形状**（字段、类型、必填、枚举、是否容忍多余字段） |
| 依赖实现吗 | 是——断言里直接调用具体函数/方法 | 通常否——只喂数据，看放行还是拦截 |
| 重构后要不要改 | 可能要（调用方式变了就得改） | **不该改**（实现重构不该动形状） |
| 失败说明了什么 | 逻辑错了 | 承诺被破坏，或两侧契约漂移了 |
| 本实验台的对应物 | `tests/test_duration.py`（`parse_duration` 的行为） | `tests/test_contract_pydantic.py`、`tests/test_contract_schema.py` |
| marker | 无 | `pytest.mark.contract`（`test_contract_pydantic.py:10`、`test_contract_schema.py:22`） |

**为什么"不依赖实现"这条很重要**：契约测试是跨团队、跨语言、跨版本可比对的基线——前端按 JSON Schema 生成类型，后端按 Pydantic 校验，两边都不需要知道对方实现细节，只要都不违反形状，所以它能做到"重构后不需要改"。反向的纪律：**不要把业务语义写进契约测试**，"`1h30m` 等于 5400 秒"属于单元测试（`tests/test_duration.py:22`）；契约测试里出现具体数值语义，通常意味着分层放错了位置——那样的契约测试会在每次需求微调时报红，然后被删掉。

---

## 八、一场真实的红灯：实验台自己抓到的事故（已修复）

这是全文最值得读的一节。它示范的不是"如何写测试"，而是**红了之后该怎么办**。

### 8.0 事故现场

实验台第一次跑起来时（当时的 `lab/.venv` 只有 pip/setuptools，依赖后装）：

```
python -m pytest -q                                   -> 2 failed, 41 passed    exit=1
python run_red_green_refactor.py                      -> ❌ 自检失败：core_green.py 期望通过实际失败
                                                                        core_refactored.py 期望通过实际失败   exit=1
```

两个失败都是**真问题**，而且各自代表一类完全不同的错误。逐条给出错误原文、真因、修法，以及「为什么修的方向不是删掉断言」。

### 8.1 漂移：冻结的 schema 和代码互相矛盾（`tests/test_contract_schema.py:89` 失败）

```
AssertionError: 必填字段集合漂移了：schema=['email','id','role','tags','username'] vs code=['email','id','username']
```

真因：`contracts.py:57-58` 给 `role` 默认值 `"member"`、`tags` 默认 `default_factory=list`，Pydantic v2 因此认为两者**非必填**；而 `contracts/user-profile.schema.json:8` 把它们列进了 `required`。更荒谬的是它**同时**给 required 的 `role` 写了 `"default": "member"` —— **required 字段带 default 本身自相矛盾**：既然必须给，默认值永远用不上。

**修法（已落地）**：承认「有默认值 = 可省略」，让 schema 跟随代码。

- `user-profile.schema.json:8`：`required` 收窄为 `["id","username","email"]`
- `:25-30`：`role` 保留 `"default": "member"`，并补一句人话解释 —— `"可省略；省略时由实现补 'member'。故不在 required 里。"`
- `:31-39`：`tags` 补 `"default": []`

> **修的方向不是删掉断言。** 断言是对的，代码库是错的。一个"红了就删"的团队，最后会得到一套全绿但什么都没保证的测试 —— 那比没有测试更糟，因为它提供虚假的安全感。

**边界提醒（这条测试的已知盲区）**：即使修好这里，它的比对范围（required / type / role enum / additionalProperties）仍**覆盖不到** `tags` 元素正则的差异 —— schema 侧是 `^[a-z0-9_-]+$`（`user-profile.schema.json:37`），代码侧只强制"必须小写"（`contracts.py:60-66`）。这是 §6.5 原则的代价：骨架比对**故意**漏细节。所以细节漂移要靠"两侧各跑同一批负例"之类的测试来兜 —— **骨架比对 + 负例比对，缺一不可。**

### 8.2 lax 模式放行了数字字符串（`tests/test_contract_pydantic.py:38` 失败）

```
FAILED tests/test_contract_pydantic.py::test_invalid_fields_rejected[id-42-id ...]
E   Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>
```

用例参数是 `("id", "42", "id 必须是整数，不接受数字字符串")`。真因：Pydantic v2 默认 **lax（宽松）模式**，`Annotated[int, Field(gt=0)]`（`contracts.py:54`）把 `"42"` 静默强转成 `42`，于是"必须抛异常"这条断言根本没机会成立。

**修法（已落地）**：给 `model_config` 加 `strict=True` —— `contracts.py:52`（`UserProfile`）与 `:73`（`ProfilePage`）。嵌套层也必须同样严，否则「外层宽进、内层严出」等于白设。

> 这条事故正好是本模块最想传达的观点：**类型系统的价值取决于它有多严。**
> 一个会自动替你"修好"错误输入的类型系统，恰恰最危险 —— 它让你误以为校验发生了。
> `"42" → 42` 在 Python 里很方便，但在跨语言边界上意味着"后端接受了前端本不该发的类型"。

### 8.3 顺带修掉的两处非测试问题

**出处错误**：`contracts.py:16-17` 与 `tests/test_contract_schema.py:3-8` 原称"spec-kit 用 jsonschema 校验 `extensions/catalog.json` 这类产物的形状"。**实测不成立**：`spec-kit/tests/contract/` 里搜 `jsonschema` / `Draft` / `check_schema` **零命中**；spec-kit 的契约本体是 **markdown**（`spec-kit/tests/contract/test_manifest_schema.py:3` 的 "Mirrors contracts/bundle-manifest.schema.md"），执行器是手写校验函数（`CatalogEntry.from_dict(...)` / `structural_errors()`）。**修法**：两个 docstring 都改写成"两条路线对比"（路线 A：schema 是文档 + 手写校验器 + 测试作执行器；路线 B：机器可读 schema + 现成库），并点明**唯一重要的共同点是"必须有一个独立执行器"**。教学结论不变，但**这处出处曾经是错的，不要当作 spec-kit 的事实引用**；权威版本见 `docs/04-spec-kit架构拆解.md:288-315`。

**环境缺依赖**：`pyproject.toml:5-6` 声明 `requires-python = ">=3.11"`、`dependencies = ["pydantic>=2.0", "jsonschema>=4.0"]`，`run_red_green_refactor.py:63` 用 `sys.executable` 启动 pytest；而 `lab/.venv/Lib/site-packages` 当时只有 pip / setuptools（`pyvenv.cfg` 的 `include-system-site-packages = false`）。后果：用 `lab/.venv/Scripts/python.exe run_red_green_refactor.py` 得到 `No module named pytest`、退出码 1 —— **又一个"环境红灯被当成测试红灯"的活标本**（见 §1.3）。**已解决**：依赖装进同一虚拟环境（pytest 9.1.1 / pydantic 2.14.0 / jsonschema 4.26.0）。注意装包时的沙箱坑：pip 默认把 HTTP 缓存写到工作区之外，被拒后**既不报错也不前进**；对策是 `--no-cache-dir` + 把输出重定向到真实文件句柄（见 `lab/_pip_install.py`）。

### 8.4 修复后的实测结果（全绿）

```
pytest -q                       -> 43 passed                            exit=0
run_red_green_refactor.py       -> RED exit=1 / GREEN exit=0 / REFACTOR exit=0
                                   ✅ 自检通过：红灯确实是红的，绿灯和重构确实是绿的。   exit=0
node test/duration.test.mjs     -> 20 tests all pass                    exit=0
node test/contract.test.mjs     -> 30 tests all pass                    exit=0
node run-rgr.mjs                -> RED exit=1 / GREEN exit=0 / REFACTOR exit=0
                                   SELF-CHECK PASSED                    exit=0
```

### 8.5 这一节真正教的东西

1. **红灯分两种，必须先分类再动手**（§1.3）：`No module named pytest` 是环境红灯，`DID NOT RAISE` 是断言红灯。前者修环境，后者修代码。
2. **修复方向由「谁是错的」决定**，不由「哪边改起来快」决定：8.1 改 schema（代码是对的），8.2 改代码（契约是对的）。两次方向相反，判据是同一个。
3. **事故要写进文档**：这两个 bug 现在是 `lab/module1-tdd/README.md` 和本文的一等公民 —— 真实事故比构造的例子有说服力得多。

## 九、自检清单

1. RED 阶段跑出 `1 error in 0.39s`、退出码 2，这算有效红灯吗？为什么？
2. `NotImplementedError` 与 `ImportError` 在 pytest 里各返回什么退出码？为什么 CI 根本无法靠退出码区分二者，而你必须区分？
3. `lab/module1-tdd/pyproject.toml:11` 的 `pythonpath = ["src"]` 如果删掉，会出现什么样的红灯？它属于哪一类？
4. marker 名字拼错时，`--strict-markers` 开与不开分别会发生什么？最坏的结果是什么？
5. `extra="forbid"` 与默认 `ignore` 在处理"多一个字段"时的行为差异？为什么这是幻觉的藏身处？
6. 为什么 `@field_validator` 里写的规则不会出现在 `model_json_schema()` 的输出里？这对"两份契约"意味着什么工程约束？
7. `test_schema_does_not_drift_from_code` 为什么不做逐字比对？逐字比对的最终后果是什么？
8. 为什么说"约束生成"不如"事后校验"可靠？各自的失效方式是什么？
9. 契约测试和单元测试各自的验收对象是什么？重构实现后，哪一类不该改？
10. 一份 OpenAPI 文档如果没有任何工具去校验，它的实际错误捕获能力是多少？
