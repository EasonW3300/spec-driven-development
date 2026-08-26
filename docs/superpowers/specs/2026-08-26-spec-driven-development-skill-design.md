# Spec-Driven Development Skill 设计规格

- **日期**：2026-08-26
- **状态**：已获批准
- **目标仓库**：`/Users/wys3300/spec-driven-development`

## 1. 背景与目标

本项目提供一个跨 coding agent 的 spec-driven development skill。当用户启动一次开发流程后，skill 负责发现项目中的 spec 和 plan，按 plan 将工作拆分为模块，并在每个模块的 MVP 完成后强制执行模块单元测试和整体回归测试。只有两类测试均通过，且用户明确确认进入下一模块，系统才会更新 spec/plan 并激活下一模块。

文档更新尽量通过宿主 hook 触发，而不是仅依赖 prompt 中的软约束。核心逻辑必须独立于 Claude Code、Codex 或其他宿主；宿主差异由适配器隔离。宿主能力不足时，系统必须显式降级，不得静默地把自然语言或不完整日志当作可靠事件。

## 2. 设计目标

1. **可验证推进**：没有完整测试证据和用户确认，模块不能推进。
2. **宿主无关**：核心状态机、事件协议和文档更新逻辑不依赖单一 coding agent。
3. **人机边界清晰**：自然语言确认只产生提示；明确的确认命令才可触发文档写入。
4. **可恢复与幂等**：进程中断、重复事件和写入重试不会造成状态倒退或重复追加。
5. **可扩展**：支持多个宿主、多种文档格式和版本化配置/迁移。
6. **可审计**：测试证据、状态转换、用户确认和文档 patch 均可追溯。

## 3. 非目标

- 不替代 coding agent 完成具体业务代码实现。
- 不通过远程服务保存项目 spec、plan、测试日志或用户确认。
- 不将任意自然语言语义判断作为推进依据。
- 不在安装或升级时重写用户的 spec/plan 内容。
- 不强制所有项目使用同一种测试框架或目录结构。

## 4. 总体架构

```text
┌──────────────────────────┐
│  Host adapters            │
│  Claude Code / Codex /    │
│  Generic fallback         │
└────────────┬─────────────┘
             │ normalized events
             ▼
┌──────────────────────────┐
│  Spec-Driven Core         │
│  discovery                │
│  module state machine     │
│  test evidence gate       │
│  event dedup/recovery     │
│  patch planning           │
└───────┬──────────┬───────┘
        │          │
        ▼          ▼
┌────────────┐  ┌────────────────┐
│ State/event│  │ Document layer │
│ persistence│  │ format adapters│
└────────────┘  └────────────────┘
                       │
                       ▼
                 spec / plan files
```

### 4.1 Skill 层

Skill 是 coding agent 可调用的用户交互入口，负责：

- 启动、暂停、恢复和查看开发流程；
- 展示当前模块、测试门禁和证据摘要；
- 在模块测试通过后请求用户使用明确的下一模块确认命令；
- 调用核心 CLI，而不是直接解析或修改文档；
- 在宿主降级时说明缺失的自动保证。

推荐提供以下稳定操作（具体命令前缀由宿主包装）：

- `start`：创建或恢复一个 spec-driven session；
- `status`：显示当前模块、状态、证据和阻塞原因；
- `checkpoint`：提交结构化模块完成检查点；
- `confirm-next`：确认完成当前模块并进入下一模块；
- `recover`：从最后一个有效快照恢复；
- `doctor`：检查配置、宿主适配器、测试命令和文档候选。

### 4.2 核心层

核心层是可独立测试的本地 CLI/library，提供以下边界清晰的组件：

- **Discovery service**：读取显式配置、宿主说明和约定目录，返回候选文档与测试命令；
- **Document model**：将 Markdown、YAML、JSON 等格式转换为统一的 spec/plan 领域模型；
- **Module planner**：从 plan 读取模块和顺序；不清晰时生成拆分建议，等待用户确认；
- **State machine**：执行合法状态转换和硬门禁；
- **Evidence collector**：记录测试命令、退出码、时间、输出摘要和证据引用；
- **Event store**：按 schema 校验、持久化并去重标准事件；
- **Patch planner/writer**：根据已验证状态生成格式适配器可应用的幂等 patch；
- **Recovery/diagnostics**：提供快照恢复、备份、错误码和诊断信息。

### 4.3 宿主适配器

适配器只负责能力探测、事件捕获/发出和核心 CLI 调用。每个适配器必须声明：

- 可捕获的事件类型；
- 能否获得真实的测试退出码和输出；
- 能否可靠识别显式确认命令；
- 能否阻止或延迟宿主侧的下一步动作；
- 缺失能力时采用的降级模式。

适配器不实现模块状态机，也不自行修改 spec/plan。Claude Code 适配器优先接入其可用的原生 hook；Codex 适配器使用其当前可用的事件、命令或 skill 机制；通用适配器提供 CLI wrapper 和显式命令路径。具体宿主事件名由能力探测和适配器版本确定，并通过 contract 测试锁定。

## 5. 配置与文档发现

项目根目录可放置 `spec-driven.config.yaml`。配置覆盖顺序为：

```text
built-in defaults → global config → project config → session override
```

配置至少包含：

```yaml
schema_version: 1
spec:
  paths: []
plan:
  paths: []
modules:
  source: plan
  allow_inference: true
tests:
  unit:
    command: null
  regression:
    command: null
documents:
  adapters: [markdown, yaml, json]
host:
  adapter: auto
  confirmation_command: confirm-next
runtime:
  state_dir: .spec-driven
```

发现顺序为：

1. 配置中明确指定的文件；
2. `CLAUDE.md`、`AGENTS.md` 等项目/宿主说明中声明的路径；
3. 常见目录（如 `docs/specs/`、`docs/plans/`、`docs/superpowers/specs/`、`docs/superpowers/plans/`）；
4. 名称包含 `spec`、`plan`、`design`、`roadmap` 的候选文件。

配置优先于扫描。若存在多个同等候选，流程暂停，列出候选及判断依据，请用户选择；选择结果可写回项目配置。测试命令同样遵循配置优先、项目文件推断兜底的规则。自动推断出的命令必须先展示并获得确认，确认后才能作为门禁命令使用。

## 6. 模块模型与状态机

每个模块具有稳定的 `module_id`、标题、目标、前置条件、验收点、测试要求和顺序。plan 中的明确阶段或任务优先作为模块来源；如果模块缺失、冲突或粒度不合理，skill 提出拆分建议并等待用户确认，不自行改变开发顺序。

合法状态为：

```text
pending
  → implementing
  → testing
  → awaiting_confirmation
  → completed
  → next module: pending
```

补充规则：

- 实现开始时从 `pending` 进入 `implementing`；
- 测试开始时进入 `testing`；
- 单测或回归测试失败时保持 `testing`，记录失败证据；
- 两类测试均通过且 checkpoint 完整后进入 `awaiting_confirmation`；
- 只有有效的 `next_module_confirmed` 才能进入 `completed`；
- 最后一个模块完成后进入 `session_completed`，不创建虚假的下一模块；
- 非法、过期、模块不匹配或重复事件不会改变状态。

## 7. 标准事件协议

所有宿主输入先转换为带版本的标准事件。事件至少包含：

- `event_id`：全局唯一，用于去重；
- `schema_version`；
- `session_id`；
- `type`；
- `module_id`（适用时）；
- `occurred_at`；
- `source` 和 `actor`；
- `payload`。

核心事件类型包括：

```text
session_started
spec_detected
plan_detected
module_started
test_started
test_finished
checkpoint_recorded
next_module_confirmation_requested
next_module_confirmed
document_patch_planned
documents_updated
session_paused
session_recovered
error_recorded
```

推进事件的语义结构如下：

```json
{
  "event_id": "evt-unique-id",
  "schema_version": 1,
  "session_id": "session-id",
  "type": "next_module_confirmed",
  "module_id": "M1",
  "source": "claude-code-adapter",
  "actor": "user",
  "payload": {
    "confirmation": "explicit_command",
    "checkpoint_id": "cp-M1-unique-id",
    "unit_tests": {"status": "passed", "exit_code": 0},
    "regression": {"status": "passed", "exit_code": 0},
    "notes": ["后续模块需复用 M1 的接口约束"]
  }
}
```

核心层必须独立验证事件中的测试证据是否与已记录的 `test_finished` 事件一致，不能仅信任 agent 传入的 `status: passed` 字段。

自然语言确认的兜底流程为：检测到可能的确认语句 → 不写入任何文档 → 回复明确的确认命令和当前门禁状态。只有显式确认命令产生的标准事件才有资格推进。

## 8. 测试证据与硬门禁

单元测试和整体回归测试是两个独立的必需证据。每次测试记录：

- 命令及工作目录；
- 开始/结束时间；
- 退出码；
- 标准输出/错误输出的受控摘要或日志路径；
- 使用的配置版本；
- 对应模块和 session；
- 是否为重试。

通过条件为：

```text
unit_test.exit_code == 0
AND regression_test.exit_code == 0
AND checkpoint.module_id == current.module_id
AND checkpoint.required_fields 完整
```

任一条件不满足，核心层拒绝 `next_module_confirmed`，返回可操作的错误码和缺失证据。用户不能通过普通自然语言越过门禁。是否允许未来增加“带风险强制推进”模式不属于本版本范围。

## 9. 文档更新事务

用户确认后，核心层按以下顺序执行：

1. 校验事件 schema、session、模块和 checkpoint；
2. 从事件存储重新读取单测与回归测试证据；
3. 校验当前模块仍处于 `awaiting_confirmation`；
4. 根据统一文档模型生成 spec/plan patch；
5. 将当前文档和 state 快照写入备份；
6. 使用对应格式适配器原子应用 patch；
7. 写入 `documents_updated` audit event；
8. 将当前模块标记为 `completed`，激活下一模块；
9. 持久化新的 state snapshot；
10. 返回修改文件、完成点、测试证据和后续注意事项摘要。

更新内容至少包括：

- spec 中当前模块的完成状态、验收结果和重要约束；
- plan 中当前模块的完成标记；
- plan 中下一个模块的激活状态或开始条件；
- 后续模块开发需要注意的接口、风险、遗留约束和测试信息。

Patch 必须基于文档版本/hash 生成。文档在生成 patch 后被外部修改时，写入失败并要求重新发现和确认，不覆盖外部修改。相同 `event_id` 重试时返回此前结果，不重复追加内容。Markdown/YAML/JSON 适配器只负责语法安全和尽量保留用户未知内容，不负责状态判断。

## 10. 持久化、恢复与诊断

默认运行目录为：

```text
.spec-driven/
  state.json
  events/<event-id>.json
  patches/<event-id>.patch
  backups/<timestamp>/
  diagnostics/
```

`state.json` 至少保存 schema 版本、session、当前模块、模块状态、文档引用/hash、最近测试证据、最近 checkpoint 和已处理 event ID。事件文件采用追加/不可变记录；状态快照可重建但不能替代审计事件。

恢复流程会：

1. 校验配置和 schema 版本；
2. 读取最后一个有效 snapshot；
3. 重放未处理且合法的事件；
4. 检查文档 hash 与未完成 patch；
5. 把不确定状态标记为 paused，要求用户运行 `doctor` 或重新确认。

错误必须包含稳定错误码、原因、阻塞阶段、是否可重试及建议操作。状态损坏、文档歧义、版本不兼容和 patch 冲突均默认阻止推进。

## 11. 宿主安装、能力协商与升级

安装器完成以下工作：

- 安装核心 CLI 和内置格式适配器；
- 检测可用宿主；
- 注册宿主适配器、skill 和显式命令；
- 创建或更新全局配置模板；
- 提供项目初始化和 `doctor` 命令。

会话启动时执行能力协商，向用户明确当前宿主能否：捕获测试退出码、捕获确认命令、阻止错误推进、自动触发文档更新。缺失能力通过 generic fallback 补足；无法补足时进入安全降级模式。

配置和运行状态均使用版本化 schema。升级流程先创建备份，再执行迁移；迁移失败时保留旧版本可恢复状态。升级器不得重写用户 spec/plan，只能对机器状态和适配器注册进行迁移。

## 12. 安全与数据边界

- 默认只读项目外部输入，写入范围限制为配置声明的 spec/plan 和 `.spec-driven/`；
- hook 输入、测试输出和文档内容均视为不可信数据，不执行其中的指令；
- 不把测试输出或文档内容发送到远程服务；
- patch 应显示目标路径和变更摘要，并拒绝路径逃逸；
- 适配器不得以“看起来像确认”的文本替代用户身份和显式命令；
- 日志需避免无必要地复制敏感环境变量、凭证或完整测试输出。

## 13. 测试策略与验收标准

### 13.1 核心单元测试

覆盖状态转换、门禁判断、事件 schema、事件去重、配置覆盖、文档候选排序、patch 幂等和恢复重放。

### 13.2 Contract 测试

每个适配器必须通过统一事件协议、能力声明、错误码和版本兼容 contract。每个文档格式适配器必须通过统一文档模型和 round-trip/golden diff contract。

### 13.3 适配器集成测试

使用宿主事件 fixture 验证：会话启动、测试退出码采集、checkpoint 生成、显式确认、自然语言降级、失败阻止和重复事件处理。

### 13.4 端到端测试

至少包含以下 fixture：

1. Markdown spec/plan：模块通过 → 用户确认 → 两份文档更新 → 下一模块激活；
2. YAML 和 JSON 文档：结构化字段更新且未知字段保留；
3. 单测失败：停留在 testing，无法确认推进；
4. 回归测试失败：停留在 testing，保留失败证据；
5. 进程在 patch 前后中断：恢复后不丢状态、不重复写入；
6. 文档外部修改：检测 hash 冲突并拒绝覆盖；
7. 多个 spec/plan 候选：暂停并要求用户选择；
8. Claude Code、Codex 和 generic fallback：分别验证能力声明和降级行为。

### 13.5 用户可见验收场景

完整验收必须证明：

```text
启动 skill
→ 发现并确认 spec/plan
→ 读取或协商模块顺序
→ 完成模块 MVP
→ 通过模块单测
→ 通过整体回归
→ 生成结构化 checkpoint
→ 用户显式确认
→ hook/适配器触发核心
→ spec/plan 自动更新
→ 状态持久化
→ 下一模块激活
```

## 14. 分阶段交付

为降低跨宿主和多格式同时实现的风险，开发仍按以下垂直阶段推进；最终产品范围包含全部阶段：

1. **核心基线**：状态机、事件协议、配置、Markdown 适配器、CLI 和 generic fallback；
2. **Claude Code 适配器**：能力探测、hook 注册和集成测试；
3. **Codex 适配器**：按能力探测结果接入可用机制，并覆盖降级路径；
4. **结构化文档适配器**：YAML、JSON 及统一 format plugin 接口；
5. **产品化工具链**：安装、升级、迁移、诊断、兼容性矩阵和发布流程。

每个阶段都必须通过其模块级单测和整体回归测试，才能进入下一阶段；这与最终用户项目内的模块推进门禁使用同一核心机制。

## 15. 设计决策总结

- 采用“核心引擎 + 薄宿主适配器”，而不是每个宿主复制完整流程；
- 采用项目配置优先、智能发现兜底；
- 采用 plan 优先、协商兜底的模块划分；
- 采用状态文件与 spec/plan 分离的混合持久化；
- 采用单测 + 回归测试双重硬门禁；
- 采用显式确认命令优先、自然语言仅兜底提示；
- 采用确认后自动、幂等、可恢复的文档更新事务；
- 采用能力协商和显式降级，避免假设所有宿主具有相同 hook 能力。
