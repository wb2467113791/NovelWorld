请先完整阅读当前仓库，尤其是：

- AGENTS.md
- agent/
- characters/
- skills/
- memory/
- tools/
- world/
- world-service/
- tests/

不要只根据 README 判断项目架构。

当前任务是开始 NovelWorld V4 重构。

目标不是推翻现有项目，而是把当前偏“事件驱动任务/剧情执行器”的上层 Agent 行为，逐步升级成“持续运行的 AI 角色世界”。

## 必须保留的现有架构

以下原则不能破坏：

- Java `world-service` 继续作为 authoritative world state 和 authoritative rules layer。
- Python/LangGraph 继续负责 Agent 决策。
- Python 通过 MCP 请求 Java 执行世界行为。
- 所有真实世界状态修改必须经过 Java 校验。
- 保留角色知识隔离和 `perceived_by`。
- 保留角色视角的 Memory / RAG。
- 保留 Chroma 作为可重建检索索引。
- 保留 MySQL 世界持久化。
- 保留多世界隔离。
- 保留 React + SSE Observatory。
- 保留“一 Tick 最多一个成功 world action”原则。
- 保留 Event Reaction 机制。
- 保留现有测试，并给新行为补测试。

核心职责：

LLM 决定：
“角色想做什么。”

Java World Engine 决定：
“这个行为是否允许，以及世界实际发生什么。”

禁止让 LLM 直接修改 World State。

---

# V4 总体方向

后续 V4 会逐步实现：

1. Goal / Intention / Plan / Agenda
2. Event Reaction + Agenda 双驱动调度
3. ConversationSession
4. 更通用的 World Object Model
5. 通用 world primitives
6. Skill 去 Workflow 化
7. 普通生活场景测试

但是本次不要一次全部完成。

## 本次只执行 Phase 1

Phase 1 目标：

建立 Agent 的基础自主计划状态，为后续 Agenda Scheduler 做准备。

### 当前问题

目前角色行为过度依赖：

- `character.goals[0]`
- Event 唤醒
- Skill Workflow 推荐具体下一步行为

需要增加一层更高层的自主认知状态。

### Phase 1 需要支持

至少能够表达：

- active_goal
- current_intention
- current_plan
- agenda
- busy_until

必要时可以设计独立的运行时 Agent 状态对象，不要求把所有字段永久写入 Character dataclass。

请根据当前代码结构选择最小且清晰的方案。

### Plan 的设计要求

Plan 是粗粒度方向，不是 Tool 步骤列表。

正确例子：

Goal:
调查失踪案

Intention:
确认客栈方向的线索

Plan:
继续调查客栈相关情况，根据获得的信息决定是否询问相关人员或前往其他地点。

错误例子：

1. move 客栈
2. inspect 登记簿
3. talk 苏晚
4. move 县衙

不要创建：

- PlanWorkflow
- PlanStepExecutor
- 固定 Tool sequence

Plan 必须能够在新 observation / event 出现后被重新考虑。

### active_goal

不要继续永远固定：

`character.goals[0]`

需要让 Agent State 可以明确保存当前 active_goal。

本阶段可以采用简单、可解释的 goal selection，不需要设计复杂 Goal Manager。

重点是为未来动态 goal 切换留下正确的数据结构。

### Agenda

本阶段只建立 Agenda 的数据模型和基础持久化/恢复能力。

不要提前完成完整双调度器。

Agenda 至少应该能表达：

- 某个角色
- 预计执行时间
- 对应的 intention / activity
- status

具体结构请保持简单。

不要设计复杂日历系统。

### busy_until

为未来 Conversation、travel、长期行为预留 busy 状态。

本阶段只建立合理的数据表达和持久化支持，不需要实现完整 busy scheduler。

---

# 本阶段暂时不要做

不要提前实现：

- 完整 ConversationSession
- Player Actor
- take / put / 新 Object Model
- Location 拓扑
- travel_time
- Belief System
- Reflection 重构
- Social Evaluator
- Relationship 重构
- 经济系统
- 天气系统
- Redis
- 新的大型框架

也不要删除现有 Event Scheduler。

---

# Skill

本 Phase 不需要彻底重写 Skill。

但请避免新增任何新的 deterministic Skill Workflow。

现有 investigation / concealment 先保持兼容。

如果新的 Plan 状态需要和 Skill 交互，Skill 只能作为决策上下文，不能变成 Plan 的固定步骤生成器。

---

# 持久化

新的：

- active_goal
- current_intention
- current_plan
- agenda
- busy_until

需要考虑当前：

- Python scheduler/session state
- Java snapshot / save_agent_state
- restart restore
- multi-world isolation

请先理解现有持久化调用链，再决定数据放在哪里。

不要制造第二套权威业务状态。

Java 仍然是 World State 的权威来源。

Agent cognition/runtime state 可以按照当前 scheduler/memory 的方式合理持久化。

---

# 测试

至少增加或调整测试验证：

1. active_goal 不再只能隐式等于 `goals[0]`
2. Agent runtime state 可以保存并恢复 intention / plan
3. Agenda 数据可以保存并恢复
4. 多世界之间 Agent runtime state 不串
5. 原有 Event Scheduler 行为不被破坏
6. 原有知识边界不被破坏
7. Java authoritative world state 原则不被破坏

不要使用真实 LLM API 做单元测试。

使用 deterministic/mocked behavior。

---

# 执行流程

开始修改前，先输出：

1. 当前 Agent / Scheduler / persistence 的实际调用链
2. Phase 1 预计修改的文件
3. 每个文件为什么需要改
4. 哪些现有结构会保留
5. 你计划如何避免把 Plan 做成新的 Workflow

然后再开始修改。

完成 Phase 1 后：

1. 运行相关 Python tests
2. 运行相关 Java tests
3. 总结实际修改文件
4. 总结新增数据结构
5. 明确说明仍未实现哪些 V4 Phase
6. 检查是否出现重复状态源
7. 不要自动开始 Phase 2

如果发现 Phase 1 某个设计与当前代码严重冲突，请优先保持现有正确架构，并采用更小的兼容性方案，而不是为了严格照搬本文而大面积重写。