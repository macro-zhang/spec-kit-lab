# spec-kit 架构拆解

> 拆解对象：`spec-kit/`（github/spec-kit 的 main 分支浅克隆，放在仓库同级目录，不入库）
> 所有结论都带 `文件路径:行号`，你可以逐条去核对。

---

## 〇、先纠正三个认知偏差

你在提问里给了三个前提。**其中两个和代码事实不符**，如果带着它们去拆解会走偏，所以放在最前面。

### 偏差 1：spec-kit 的核心是「把写测试的权力收归人类」

**部分成立，但机制不是测试。**

代码事实：

- `templates/commands/tasks.md:147` 白纸黑字写着：
  > `**Tests are OPTIONAL**: Only generate test tasks if explicitly requested in the feature specification or if user requests TDD approach.`

  也就是说，**默认根本不生成测试任务**。
- 测试只有在「项目宪法把它升格」之后才变成硬约束。而宪法模板里的 TDD 条款是 **HTML 注释**，默认不生效：
  - `templates/constitution-template.md:17` → `<!-- Example: III. Test-First (NON-NEGOTIABLE) -->`
  - `templates/constitution-template.md:19` → `<!-- Example: TDD mandatory: Tests written → User approved → Tests fail → Then implement; Red-Green-Refactor cycle strictly enforced -->`
- 最像"硬要求"的两句都在叙述性文档里，不在可执行门禁里：`spec-driven.md:312`（"This is NON-NEGOTIABLE: All implementation MUST follow strict Test-Driven Development."）与 `spec-driven.md:350`。

**修正后的说法**：spec-kit 收归的是**「什么叫做对了」的定义权**，而不只是"写测试的权力"。这个定义权落在四样东西上：

| 收归的产物 | 载体 | 谁说了算 |
|---|---|---|
| 需求边界 | `spec.md` + `[NEEDS CLARIFICATION]` 标记 | 人类回答 clarify 提问 |
| 项目级不可协商原则 | `.specify/memory/constitution.md` | 人类手写 |
| 需求文本质量 | `checklists/*.md`（CHK### 问句） | 人类勾选，**Agent 禁止勾** |
| 跨制品一致性 | `analyze` 报告（CRITICAL/HIGH/…） | 严重度判定 |

Agent 的自由度被压缩在"把 spec/plan/tasks 翻译成代码"这一段里。测试只是**可选的一种**把契约固化下来的手段。

### 偏差 2：spec-kit 用 Git Hooks / pre-commit 作为规范落地的核心抓手

**不成立，而且这是最容易误读的地方。**

- spec-kit **不为被生成的项目提供任何 git hook**。全仓 `templates/`、`scripts/`、`src/specify_cli/` 里没有任何写 `.git/hooks`、设 `core.hooksPath`、或执行 `pre-commit install` 的代码。
- 全仓唯一的 `.pre-commit-config.yaml` 在 spec-kit **自己的仓库根**，而且只有 4 条通用文件卫生规则，零条领域规则：
  - `.pre-commit-config.yaml:3-4` 引用 `pre-commit/pre-commit-hooks` `rev: v6.0.0`
  - `.pre-commit-config.yaml:6` `check-executables-have-shebangs`
  - `.pre-commit-config.yaml:7-8` `check-yaml`（`exclude: \.lock\.yml$`）
  - `.pre-commit-config.yaml:9-10` `end-of-file-fixer`
  - `.pre-commit-config.yaml:11-12` `trailing-whitespace`
- 没有任何 CI workflow 调用 pre-commit；`CONTRIBUTING.md` 全文不出现 "pre-commit"。职责与 `lint.yml:33-51` 的 `git diff --check` 重叠 → 它是**可选的本地卫生工具**，贡献者不装也不影响评审。
- `.git/hooks` 在代码里唯一一次出现是作为**被拒绝的路径**：`tests/specify_cli/integrations/test_installed_adapters.py:2915` 把 `".git/hooks"` 和 `"../outside"`、`".SPECIFY/scripts"` 并列为非法安装目标。

**那 spec-kit 语境里的 "hook" 是什么？** 是**提示词级 agent 生命周期钩子**：
`before_specify` / `after_tasks` 之类，声明在 `.specify/extensions.yml`（结构见 `docs/reference/extensions.md:292-344`，条目见 `:346`）。它们是在 Agent 流程的特定时点插入提示词，**不是 git 钩子，不具备本地强制力**。

**唯一做 git 边界的是第三方社区扩展** spec-gates（`docs/community/extensions.md:138` = `extensions/catalog.community.json:2402`），需要用户自己装。

### 偏差 3（这个成立）：退出码是真正的通用语言

`check-prerequisites.sh` / `check_prerequisites.py` 把「成功/失败」全部编码成退出码，而不是让人去读日志：

- 成功 `exit 0`（`scripts/bash/check-prerequisites.sh:135,243`）
- 失败先往 **stderr** 写 `ERROR: ...`，再 `exit 1`：
  - 缺 feature 目录 `:139-143`
  - 缺 plan `:145-149`
  - `--require-spec` 未满足 `:152-156`
  - `--require-tasks` 未满足 `:159-163`
- Python 镜像同契约：`scripts/python/check_prerequisites.py:223-229 / 231-237 / 239-245 / 247-253`，统一 `return 1`

CLI 层也一样：项目解析咽喉 `_require_specify_project`（`src/specify_cli/__init__.py:436-463`）往 `err_console` 打 `Not a Spec Kit project (no .specify/ directory)` 后 `raise typer.Exit(1)`。

---

## 一、全局地图：仓库分四层

```
spec-kit/
├── templates/          ← 【提示词层】Agent 的行为脚本 + 制品模板
│   ├── commands/*.md        10 个 slash 命令的完整指令（specify/plan/tasks/…）
│   ├── spec-template.md     制品模板：spec / plan / tasks / checklist / constitution
│   └── tasks-template.md
├── scripts/            ← 【确定性脚本层】bash / powershell / python 三份镜像实现
│   ├── bash/*.sh            check-prerequisites / setup-plan / setup-tasks / create-new-feature
│   ├── powershell/*.ps1
│   └── python/*.py
├── src/specify_cli/    ← 【CLI 层】Typer 应用，负责 init 项目、装模板、装扩展
├── workflows/          ← 【工作流引擎层】spec-kit 自研的本地 YAML 工作流引擎
└── .github/            ← 【自身工程层】只服务 spec-kit 这个仓库自己
```

**关键分层洞察**：前三层是"发给用户的"，`.github/` 是"给自己用的"。你原始清单里的 Git Hooks 与 CI 门禁，属于**第四层**，对 spec-kit 的用户侧能力没有直接影响。

---

## 二、命令链路：一条从需求到代码的流水线

### 2.1 全链路

```
constitution（每项目一次）
      ↓
   specify ──→ clarify?（有 [NEEDS CLARIFICATION] 才跑）
      ↓
    plan ──→ checklist?
      ↓
   tasks ──→ analyze?
      ↓
  implement
      ↓
   converge
```

链路关系还有一层硬证据：各命令文件的 frontmatter `handoffs:` 声明了下一步是谁 ——
`templates/commands/constitution.md:3-6`、`specify.md:3-10`（指向 clarify）、`plan.md:3-10`（指向 checklist）、`tasks.md:3-11`（指向 analyze / implement）。

### 2.2 逐阶段：输入 / 输出 / 门禁

| 阶段 | 输入 | 输出（确切路径） | 门禁 |
|---|---|---|---|
| **constitution** | `resolve-template.sh constitution-template --json`；既有宪法 | `.specify/memory/constitution.md`（覆写），顶部插 Sync Impact Report | 解析器 "It MUST succeed before continuing. If it fails, stop and report the resolution error"（`constitution.md:85-87`）；缺信息写 `TODO(<FIELD_NAME>)`（`:144`）；不许碰应用代码（`:26-32`） |
| **specify** | `$ARGUMENTS`；spec-template；宪法 IF EXISTS | `specs/<前缀>-<短名>/spec.md`、同目录 `checklists/requirements.md`、`.specify/feature.json` | `ERROR "No feature description provided"`（`specify.md:119`）；`ERROR "Cannot determine user scenarios"`（`:131`）；`[NEEDS CLARIFICATION]` **上限 3 个**；质量校验最多重跑 3 轮（`:196-197`）；**marker 残留必须停下等人类回答**（`:199-232`） |
| **clarify** | `check-prerequisites.sh --json --paths-only` → FEATURE_DIR / FEATURE_SPEC | 原地重写 `spec.md`，追加 `## Clarifications` + `### Session YYYY-MM-DD`；回写 requirements.md 勾选 | **一次只问 1 题并等回答**（`clarify.md:141`）；全程 ≤5 题（`:130`）；spec 缺失时禁止新建，要求先跑 specify（`:232`） |
| **plan** | `setup-plan.sh --json`；spec + 宪法 | `plan.md`、`research.md`(Phase 0)、`data-model.md`、`contracts/`、`quickstart.md`(Phase 1) | `plan-template.md:41` `*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*`；`plan.md:69` `Evaluate gates (ERROR if violations unjustified)`；`plan.md:164` `- ERROR on gate failures or unresolved clarifications`；违约必须填 Complexity Tracking 表（`plan-template.md:106-113`） |
| **tasks** | `setup-tasks.sh --json`；plan.md **必需** | `FEATURE_DIR/tasks.md` | plan.md 缺失直接 `ERROR: plan.md not found in {feature_dir}`（`scripts/python/setup_tasks.py:110`）；任务必须严格匹配 checklist 格式（`tasks.md:149-155`） |
| **analyze** | `check-prerequisites.sh --json --require-spec --require-tasks --include-tasks` | **零写入**，只出报告 | 只能在 tasks.md 完成后跑（`analyze.md:54`）；缺文件即 abort（`:72`）；**宪法冲突自动 CRITICAL**（`:60`） |
| **checklist** | `check-prerequisites.sh --json --template checklist-template` | `FEATURE_DIR/checklists/<domain>.md`，ID 从 CHK001 递增，已存在则追加 | 只生成：`it MUST NOT mark generated items [x]`（`checklist.md:35`） |
| **implement** | `check-prerequisites.sh --json --require-tasks --include-tasks`；tasks.md / plan.md 必需 | 代码；把 tasks.md 勾成 `[X]`（`implement.md:169`）；补 `.gitignore`/`.dockerignore` | checklist 全勾 ✓ PASS；有未勾 ✗ FAIL → **STOP** 并问 `Some checklists have unchecked items. Do you want to proceed with implementation anyway? (yes/no)`（`implement.md:76-84`）；非 `[P]` 任务失败即 halt（`:165`） |
| **converge** | 同 implement | **append-only**，只往 tasks.md 追加 `## Phase N: Convergence`（`converge.md:73-80`） | 判定语 `**"✅ Converged — the implementation satisfies the spec, plan, and tasks."**`（`converge.md:231`） |

---

## 三、制品是怎么串起来的

这是整个设计里最容易被忽略、但最关键的部分。

### 3.1 编号只活在目录名里

特性目录形如 `specs/003-user-auth/`。编号策略来自 `.specify/init-options.json` 的 `feature_numbering`：

- `sequential` → 扫描 `specs/` 取下一个 3 位数
- `timestamp` → `YYYYMMDD-HHMMSS`

（`templates/commands/specify.md:87-91`；旧键 `branch_numbering` 已废弃并会告警。）

### 3.2 唯一的硬链接是 `.specify/feature.json`

```json
{ "feature_directory": "specs/003-user-auth" }
```

写入见 `specify.md:99-105`。下游解析顺序（`scripts/python/common.py:149-174`）：

1. 环境变量 `SPECIFY_FEATURE_DIRECTORY`
2. `.specify/feature.json`
3. 都没有 → 报错退出

**为什么这很重要**：spec-kit **不靠 git 分支名定位当前特性**。它靠一个显式的状态文件。这意味着你在任何分支上都能被正确路由，也意味着这个文件损坏时整条链路会立刻硬失败。

固定文件名（`scripts/python/common.py:183-189`）：`spec.md` / `plan.md` / `tasks.md` / `research.md` / `data-model.md` / `quickstart.md` / `contracts/`。

### 3.3 各阶段之间传什么

- **spec → plan**：`plan-template.md:3-5` 只填 `**Branch**` 和 `**Input**: Feature specification from /specs/[###-feature-name]/spec.md`，**不引用 FR 号**。
- **spec → tasks**：靠**优先级**和 Given/When/Then 场景。spec 里的 `### User Story N (Priority: P1)` → tasks 里每个故事一个 Phase 3+ 阶段 + `[US1]` 标签（`tasks.md:73,183-190`）。
- **FR### / SC### 编号要到 analyze 才被当主键用**：`analyze.md:110` — `For each Functional Requirement (FR-###) and Success Criterion (SC-###), record a stable key`。

### 3.4 任务行的格式

`tasks.md:153-155`：

```
- [ ] [TaskID] [P?] [Story?] Description with file path
```

- `T001` 递增 = 执行序
- 描述**必须含确切文件路径**
- `[P]` = 可并行（不同文件、且不依赖未完成任务），并在 Dependencies / Parallel Example 段落成组列出
- Setup / Foundational / Polish 阶段**不加** story 标签

> 这一条是整份规范里最"可执行"的部分：任务的原子性、依赖关系、并行度都被编码进了文本格式，所以后续 `implement` 能逐条机械地推进。

---

## 四、门禁的真实形态：三层，没有一层是 git hook

| 层 | 机制 | 强制力 | 证据 |
|---|---|---|---|
| **提示词级门** | `[NEEDS CLARIFICATION]` 标记、`GATE:` 字样、MUST NOT 措辞 | 软 —— 靠 LLM 遵守指令 | `specify.md:199-232`、`plan-template.md:41`、`checklist.md:35` |
| **工作流 gate 步骤** | spec-kit 自研引擎的 `gate` 步骤，交互式人工审批 | 中 —— 会真的暂停等人 | `workflows/ARCHITECTURE.md:164`；实例 `workflows/speckit/workflow.yml:39-74` |
| **CI 门禁** | GitHub Actions 看到非 0 退出码就标红 | 硬 —— 阻断合并 | `.github/workflows/*.yml` |

### 4.1 工作流引擎（最被低估的一层）

`workflows/ARCHITECTURE.md` 描述的是 **spec-kit 自研的本地 YAML 工作流引擎**，和 GitHub Actions **毫无关系**：

- `specify workflow run` 加载 YAML：`WorkflowDefinition.from_yaml()`
- 经 `STEP_REGISTRY` 顺序派发 **13 种内建步骤**：`command / prompt / shell / init / slot / gate / if / switch / while / do-while / fan-out / fan-in / workflow`（`workflows/ARCHITECTURE.md:155-171`）
- 每步把 `RunState` 落盘到 `.specify/workflows/runs/{run_id}/state.json` 以支持 resume（`:270-281`）
- **`gate` 步骤是交互式人工审批**，"pauses in CI"（`:164`）

实例 `workflows/speckit/workflow.yml:39-74`：

```
specify → gate(review-spec) → plan → gate(review-plan) → tasks → implement
```

`gate` 用 `options: [approve, reject]` + `on_reject: abort`。

**这才是"把权力收归人类"的硬机制** —— 一个会真的卡住流程的审批点，而不是一句写在提示词里的 MUST。

### 4.2 CI 门禁（只服务 spec-kit 自己）

| workflow | 触发 | 门禁性质 |
|---|---|---|
| `.github/workflows/test.yml` | push main + 所有 PR（`:6-9`） | **是**。`ruff` job（`:12`）跑 `uvx ruff@0.15.0 check src tests`（`:27`）；`pytest` job（`:29`）matrix = 3 OS `[ubuntu, windows, macos]` × Python `["3.13","3.14"]` = 6 组合（`:32-34`），`uv sync --extra test`（`:48`）→ `uv run pytest`（`:55`） |
| `.github/workflows/lint.yml` | push main + PR（`:5-8`） | **是**，四道关：`git diff --check`（`:43-50`，按事件分三路）；`DOC_GLOBS` 逐 glob 检空匹配 → `exit 1`（`:58-87`，`:86-87`）；`shellcheck --severity=error`（`:104`）；禁 bash 4+ 大小写改写 → `exit 1`（`:110-117`） |
| `.github/workflows/extension-version-guard.yml` | **仅** `pull_request:`（`:17-18`） | **是**。`fetch-depth: 2`（`:31`）取 merge commit 双父；`git rev-parse --verify --quiet HEAD^2` 失败即 `echo "::error::..."` + `exit 1`（`:53-56`）；否则跑 `python .github/scripts/check_extension_version_bump.py HEAD^1`（`:56`）。注释解释为何**不加** `paths:` 过滤 —— 被跳过的必需检查会停在 "Expected" 阻塞所有 PR（`:13-16`） |
| `.github/workflows/security.yml` | push main、PR、`cron: "17 4 * * 1"`、dispatch（`:6-13`） | **是**（非 schedule 时）。先跑 `check_security_requirements.py`（`:39`），再 `pip-audit==2.10.0 --disable-pip --require-hashes`（`:42`） |
| `.github/workflows/release-trigger.yml` | 仅 `workflow_dispatch`（`:3-9`） | 否，是发布入口 |

### 4.3 守卫脚本：退出码的教科书用法

**`check_extension_version_bump.py`**

- 输入：`BASE_REF [HEAD_REF]`，`HEAD_REF` 默认 `HEAD`（`:31-32`, `:100-104`）
- 输出：每条违规 `print(f"::error::{error}")`（`:224-225`）；全过 `print("Extension version guard: all invariants hold.")`（`:227`）
- 退出码：参数个数不对 → `return 2`（`:100-102`）；catalog 在 HEAD 缺失 → `return 1`（`:106-109`）；**`return 1 if errors else 0`**（`:228`）；入口 `sys.exit(main(sys.argv))`（`:231-232`）
- 两条不变量：① 动过 `extensions/<id>/` 就必须按 PEP 440 让 `extension.yml` 的 `version:` 严格变大（`:172-177`）；② `catalog.json` 每个 version 可 parse 且等于 manifest 版本（`:184-222`）
- 细节讲究：`git diff` 用 `-z` + surrogateescape，防止非 ASCII 路径被 C-quote 后绕过前缀判断（`:56-78`）

**`check_security_requirements.py`**

- 输入（环境变量）：`DEPENDENCY_DIFF_BASE` / `DEPENDENCY_DIFF_HEAD` / `GENERATED_REQUIREMENTS`（`:16-26`）
- 逻辑：输入未变 → `return 0`（`:75-76`）；env 未设 → stderr + `return 1`（`:78-84`）；重新生成后**逐字比对**，不等 → `return 1`（`:109-119`）
- 有意 fail-safe：`git merge-base/diff` 抛 `CalledProcessError` 时**视作"输入已变"继续审计**，而不是静默跳过（`:56-63`）

> 最后这条是安全工程的重要姿态：**门禁脚本自己出错时，默认按"有风险"走，不按"没问题"走**。

### 4.4 硬门禁其实写在 CONTRIBUTING 里

小节 `### Testing deterministic behavior`（`CONTRIBUTING.md:227`），逐字：

> "Behavioral changes to repository-maintained code or configuration that runs or controls execution without an LLM require tests for both intended behavior (positive cases) and relevant invalid inputs, failures, or prevented behavior (negative cases). This includes Python, shell, and PowerShell code in the CLI, core scripts, extensions, presets, and tooling; workflow step types; and execution wiring such as script selection, workflow shell steps, and CI `run:` steps. Existing tests count when they cover the changed behavior."
> —— `CONTRIBUTING.md:229-235`

> "Bug fixes also need a regression test that fails before the fix and passes afterward. If a baseline or an execution path cannot be tested automatically, explain the limitation and provide reproducible evidence for the affected success and failure paths. Prompt-only and other non-behavioral edits do not require invented tests."
> —— `CONTRIBUTING.md:237-241`

配套硬门禁在 `### Evidence gate`（`CONTRIBUTING.md:81`）：有效证据之一必须是 "A regression test that fails on `main` and passes with your change"（`:90`），"理论上可能失败"不算证据（`:89`），评审维度 D4 同此（`:96-108`）。

**这两段话是你原始清单里"测试驱动"的真实位置**：它不是 spec-kit 的运行机制，而是 spec-kit **这个项目自己的贡献纪律**。区别很重要。

---

## 五、三镜像与 parity 测试（spec-kit 最精妙的一处工程）

### 5.1 问题

同样一套前置检查，spec-kit 提供了 **bash / PowerShell / Python 三份实现**（`scripts/{bash,powershell,python}/`）。三份手写实现必然漂移 —— 但用户在不同平台上会得到不同行为，这是不可接受的。

### 5.2 解法：把 bash 当 oracle

`tests/parity_helpers.py:34` 的 `install_scripts()` 把三份脚本拷进**同一个临时仓库**的 `.specify/scripts/{bash,powershell,python}/`，然后用 `bash_cmd`(`:54`) / `py_cmd`(`:58`) / `ps_cmd`(`:67`) 跑**同一个场景**，以 **bash 为基准**。

三层断言：

1. **退出码相等**
2. **JSON 先 `json.loads` 再比 dict**（`tests/test_check_prerequisites_python_parity.py:121-122,247`）—— 不比字节，所以忽略键序和空白差异
3. **文本先归一化**：`normalize_status_text:337`（`✓`→`[OK]`、CRLF→LF）、`normalize_script_names:329`、`normalize_repo_paths:321`

失败态测**双通道**（这才是完整契约）：`returncode == 1` + `stderr` 含关键词 + **`stdout.strip() == ""`**（`:399-401`, `:559-562`, `:175`）。

参数名差异显式映射：`--json` ↔ `-Json`、`--include-tasks` ↔ `-IncludeTasks`（`:405-414` 的 parametrize）。

### 5.3 连"环境"本身都要被验证

这是最值得偷师的部分：

- `collation_range_locale():190` —— 不信 `locale` 变量，**直接跑 sed 判断排序行为**
- `make_yaml_less_venv():102` —— 建 `--without-pip` 的 venv，然后 **assert 真的 import 不到 yaml**
- `make_python3_path_shim():156` —— 造一个确定性的 `python3`

守卫：`tests/conftest.py:65` 的 `requires_bash` 由 `_has_working_bash()`（`:18-62`）实现 —— `SPECKIT_TEST_BASH=1` 强制；否则实跑 `bash -c "echo ok"`；win32 上再要求 `uname` ∈ `MSYS|MINGW|CYGWIN` 以**拒绝 WSL**（WSL 处理不了原生 Windows 路径）。

> 对应到 `test.yml:50-53` 的注释：Windows 上 bash 测试会自动 skip，除非检测到 Git-for-Windows 的 bash。

---

## 六、契约测试的真相：spec-kit 不用 jsonschema / pydantic

这是一个反直觉的发现。`tests/contract/` 下 9 个文件：

- **jsonschema：全仓 0 命中**
- **pydantic：只在 MCP 模块的字面量里出现**（如 `src/specify_cli/artifacts/mcp_list.py:12`），不用于契约校验
- schema 本体是 **markdown 文档**：`contracts/*.schema.md`（见 `tests/contract/test_manifest_schema.py:2-4` docstring："Mirrors contracts/bundle-manifest.schema.md"）
- **测试就是唯一的执行器**

校验调用形态：

- `BundleManifest.from_dict(data).structural_errors()` → 返回 `list[str]` 错误清单（`tests/contract/test_manifest_schema.py:16-19,25-26,68-71`）
- 构造期类型错抛异常，用 `pytest.raises(BundlerError, match="priority must be an integer")`（`:99`）
- catalog 侧：`CatalogEntry.from_dict` / `load_catalog_payload` / `load_source_stack`（`tests/contract/test_catalog_schema.py:29-31,54-55,131-132`）

三类高价值用例（可以直接搬进你自己的项目）：

1. **`or {}` 把 falsy 非映射吞掉** → 参数化 `[[], "", 0, False]` 必须仍然 raise（`test_manifest_schema.py:197-214`、`test_catalog_schema.py:408-419`）
2. **YAML 显式 null（`author:`）必须读成 `""`**，而不是字符串 `"None"`（`:29-51`、`:272-300`）
3. **id 与字典键不一致必须报错**（`:357-362`）

另一类契约 = **产物与声明互校**：

- `tomllib` 解析 `pyproject.toml`，断言 hatch 的 force-include 配置正确（`test_catalog_schema.py:219-242`）
- 断言每个脚本变体都进了 core_pack（`test_wheel_core_pack_scripts.py:23`）
- 扩展目录 / manifest / catalog 三方互校（`test_bundled_extension_versions.py:47,70`，用 `packaging.version.Version`）

> **给你的启示**：契约测试的重点不是"用了多先进的 schema 库"，而是**是否有独立的执行器去验证承诺**。用 markdown 写 schema + 手写校验器，比用 jsonschema 但没人跑要强得多。

---

## 七、CLI 层

- 框架：**Typer ≥0.24 + Click 8.2.1 + Rich**
- 根 app：`src/specify_cli/__init__.py:90-96`
  ```python
  typer.Typer(name="specify", help=…, add_completion=False,
              invoke_without_command=True, cls=BannerGroup)
  ```
- 注册手法：每个模块导出 `register(app)`，根 `__init__.py:393-401, 407-491` 统一 import + 调用
- 子命令：`init`（`command_init.py:267`）、`check`（`command_check.py:108`）、`version`（`command_version.py:154`）、`mcp`（`command_mcp.py:17`）
- 命令组：`self`（`__init__.py:407`）、`extension`（`extensions/_commands.py:690`）、`integration`（`integrations/_commands.py:47`）、`event`、`preset`（`presets/_commands.py:99`）、`artifact`（`artifacts/_commands.py:100`）、`bundle`（`bundles/_commands.py:163`）、`workflow`（`workflows/_commands.py:1598`）
- 失败退出码：`_require_specify_project`（`__init__.py:436-463`）→ `raise typer.Exit(1)`；`version --json` 失败规范化成 `{"error":{"code":"internal_error","message":…}}` 写 stderr 再 `Exit(1)`（`command_version.py:86-94`）
- Windows 兜底：`main()`（`:502-517`）在 win32 先把 stdout/stderr `reconfigure(encoding="utf-8", errors="replace")` 再 `app()`

### `pyproject.toml` 要点

- `requires-python = ">=3.11"`（`:6`）
- runtime deps（`:7-18`）：`typer>=0.24.0`、`click>=8.2.1`、`rich`、`readchar`、`pyyaml>=6.0`、`packaging>=23.0`、`pathspec>=0.12.0`、`json5>=0.13.0`、`mcp>=2.2.0,<3.0.0`、`pydantic>=2.13.0,<3.0.0`
- **只有一个 optional 组**：`test = ["pytest>=7.0", "pytest-cov>=4.0"]`（`:61-65`）—— 没有 dev / lint 组
- 构建后端：`hatchling`（`:23-25`），wheel 只打 `src/specify_cli`（`:27-28`），但有 **40+ 条 `force-include`**（`:30-59`）把 templates / scripts / extensions / workflows / presets / bundles 映射进 `specify_cli/core_pack/**`，以支持 **air-gapped 的 `specify init`**
- 入口点：`[project.scripts] specify = "specify_cli:main"`（`:20-21`）
- pytest 配置：`testpaths=["tests"]`、`addopts=["-v","--strict-markers","--tb=short"]`（`:67-76`）
- ruff 的 `extend-select=["S602","S604","S605"]`（`:91-95`）把 `shell=True` 锁成**必须显式 `# noqa` 才能合入** —— 用 lint 规则固化安全姿态，很值得偷师

---

## 八、这张图对你「掌握前置知识」的意义

| 你原以为的重点 | 实际的重点 |
|---|---|
| TDD 是 spec-kit 的心脏 | 契约**定义权**是心脏；TDD 是可选手段，且默认关闭 |
| Git Hooks 是规范落地的抓手 | 抓手是**工作流 gate 步骤**（会真暂停）+ CI 退出码；git hook 只在 spec-kit 自己仓库里做卫生 |
| 契约测试 = 用 JSON Schema / Pydantic | spec-kit 用 markdown schema + 手写校验器 + **独立执行器**；工具不重要，独立验证才重要 |
| 学 CLI 是为了看懂子进程 | 更值得学的是**三镜像 parity 测试**：怎么写一份测试，让三份手写实现无法漂移 |

下一份要读的是 [`05-知识点映射表.md`](05-知识点映射表.md) —— 把你清单里的每个知识点，精确钉到上面的文件和行号。
