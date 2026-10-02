# V4 Phase 1：角色认知状态

本阶段建立可持续保存的目标、意图、方向性计划和活动安排。事件调度器仍按原规则运行，没有实现 Agenda 双驱动调度。

## 数据结构与唯一来源

`agent/runtime.py` 的 `AgentRuntimeState` 通过 `Character.runtime_state` 关联到当前世界的角色，生命周期与本人 Memory 相同。

| 字段 | 表达 |
| --- | --- |
| active_goal | 本人 goals 中的一个目标，或无目标时的 null |
| current_intention | 此刻想达成什么，文字或 null |
| current_plan | 一段可重新考虑的方向性文字，或 null；没有步骤列表和执行器 |
| agenda | 系统维护的 AgendaEntry 列表：id、character、due_tick、intention、status；模型只读 |
| busy_until | 系统维护的世界累计 Tick 序号或 null；模型只读 |

Agenda 状态为 pending、completed、cancelled。due_tick 与 busy_until 使用 scheduler.tick_count 的同一累计 Tick 坐标，不使用系统时间，也不使用会跨午夜回绕的世界 HH:mm。它们当前只表达安排，不自动修改状态、唤醒角色或阻塞事件反应；将来长期行为的真实忙碌结算仍应由 Java 规则决定。

模型可写认知与系统调度状态通过不同入口处理：`AgentRuntimeState.revised` 的白名单只允许 active_goal、current_intention、current_plan；`from_dict` 解析程序持久化的完整 runtime_state，保留 Agenda 和 busy。Prompt 分别展示本人认知和只读系统调度状态。

模型不能生成或覆盖 AgendaEntry.id、due_tick、status，也不能创建、替换、清空 Agenda，或设置、清空 busy_until；即使值在结构上合法，cognition 更新也整次拒绝。completed/cancelled 与真实忙碌状态必须由程序根据执行结果和调度规则维护，模型的完成或忙碌声明不能成为依据。本阶段没有实现这些状态转换逻辑，也不自动把成功行动映射为 Agenda 完成。

模型可以在 intention / plan 中表达“希望明早继续调查”等活动与时间愿望，但愿望不会自动成为规范化 AgendaEntry。活动提议的结构化协议、程序生成 ID、安排时间及状态转换留待 Phase 2，本次没有新增 Scheduler。旧快照的完整调度字段继续无损恢复，不根据历史模型文本补算执行结果。

首次选择按 goals 的设定顺序，之后保留显式 active_goal，包括第二项或其他项。目标不再属于本人 goals 时才回退，并清空旧目标下的 intention / plan。模型切换目标时也清空旧意图与计划，除非同次回复明确提供新的内容。空 goals 可以等待。

没有独立全局角色名注册表，没有 scheduler 中的第二份认知状态。LangGraph 的 goal 和 runtime_context 仅为一次决策的上下文快照，后续 Tick 从当前角色读取。

## 模型决策与世界行为

`create_initial_agent_state` 使用 active_goal 检索本人 Memory 和可见 Lore，并加入本人感知与认知状态。现有 investigation / concealment 保持兼容，但采用当前 active_goal；新 Plan 不读取 Skill 步骤来生成或执行工具序列。

模型可在现有回复文字中提供 JSON：

```json
{
  "cognition": {
    "active_goal": "调查失踪案",
    "current_intention": "确认客栈方向的线索",
    "current_plan": "继续调查客栈相关情况，根据获得的信息调整调查方向。"
  },
  "answer": "等待。\n原因：需要先评估新线索。"
}
```

认知更新仅允许 active_goal、current_intention、current_plan，是部分更新，省略字段保留原值，null 可以清空意图和计划。未知字段、目标越界、非文字计划，以及任何 agenda / busy_until 字段等会原子拒绝，保留原认知和调度状态。有效认知修订也不会改动已有 Agenda 或 busy。普通文字回复仍能结束本轮并保留认知；不强制模型每轮改变计划。没有额外规划 API 请求，不改变生成模型或向量模型。

同一次回复可以伴随现有 function_call，工具仍走 `execute_pending_tools → execute_tool → RemoteWorld.execute → MCP execute_world_tool → WorldRules → WorldStore`。认知修订不会获得额外行动额度，每 Tick 最多一个成功 world action。新事件的 observation 与工具结果可使模型修订 Plan；模型文本本身不会写入位置、体力、物品、关系、事件或 known_facts。

结构上拒绝工具步骤列表，但不尝试以关键词规则判断自然语言是否写成了步骤；方向性约束由 Prompt 明确表达，计划从不被程序执行。JSON 采用兼容的文字协议，没有依赖服务商的强制结构化输出；格式不合要求时不会自动提取认知。单元测试验证协议与边界，不验证真实模型遵循率。

## 保存、刷新与恢复

每 Tick：`WorldSession.next_tick` 的 finally 调用 `RemoteWorld.save_agent_state`，把每名角色的 memory、semantic_memory、runtime_state 和 scheduler 通过已有 MCP 保存到 Java 的按 world_id 隔离的快照；再写本地恢复副本、同步 Chroma。

Java `saveAgentState` 先校验所有新增 runtime_state，随后仅更新记忆、认知和调度进度。它不接受认知中夹带业务字段，也不根据 Plan 或 Agenda 执行世界行为。MySQL 表结构无需迁移，仍使用既有 JSON snapshot 与 revision。Java 新开局以及旧快照允许没有 runtime_state，Python 恢复时创建空对象并选择初始目标；旧客户端不携带 runtime_state 时不清空已有认知。

`save_agent_state` 是 Python 内部 Runtime 的完整持久化入口，不提供给 NPC 模型工具集；因此仍允许保存程序维护的 Agenda 状态和 busy_until。模型文本进入 `revised` 时先经过可写字段白名单，不会被原样转发到 Java 保存入口。Java 在此校验完整数据结构和角色归属，真实世界业务状态仍由 WorldRules 结算；持久化调度字段不等于新增了行为结算能力。

Java 工具提交后，`RemoteWorld._refresh_business_state` 读取权威业务状态，并保留同一世界中尚未保存的 Python 记忆与认知，然后重建 Character。跨世界恢复不会合并旧世界认知。世界切换及失败回滚沿用原 WorldController 保存恢复链。

Java 仍是业务状态权威来源；Python 内存是当前认知工作副本，Java 快照是其持久副本，本地 JSON 是恢复副本。Chroma 仍仅为可重建检索索引，认知不被另存为语义事实或跨角色检索资料。

已有逐 Tick 保存的限制继续存在：进程在认知修订后、finally 保存前被强制终止，可能丢失该次未提交认知；本阶段不引入跨 Python / Java 事务或第二套状态库。

## 验证与后续范围

实际修改文件如下（没有修改 AGENTS.md，也没有修改既有 Skill Workflow 文件）：

| 文件 | 改动 |
| --- | --- |
| agent/runtime.py（新增） | 认知和 Agenda 数据模型、校验、goal selection |
| characters/model.py | 每名角色独立 runtime_state |
| agent/state.py | 显式目标与本轮认知上下文 |
| agent/graph.py | 现有模型回复中的认知修订协议 |
| characters/prompt.py | 本人认知上下文与方向性 Plan 约束 |
| agent/tick.py | 原调度器采用当前目标的 Skill |
| skills/router.py | Skill 路由与展示采用 active_goal |
| web_api.py | Director 的目标摘要采用 active_goal |
| world/persistence.py | runtime_state 快照、恢复与旧存档兼容 |
| tools/remote_world.py | 现有 MCP 保存载荷和同世界刷新保留认知 |
| world-service/src/main/java/org/novelworld/world/WorldMcpTools.java | 新增认知字段的保存边界校验 |
| tests/test_agent_runtime.py（新增） | 16 个 Phase 1 测试，包括模型可写与系统只读边界 |
| tests/test_agent_state.py | 更新本轮状态字段断言 |
| tests/test_world_switch.py | 在真实控制器切换及失败回滚测试中核对认知隔离 |
| world-service/src/test/java/org/novelworld/world/WorldMcpToolsTest.java | 数据库保存恢复、隔离与权威边界测试 |
| docs/NovelWorld_V4_Phase1.md（新增） | 本阶段实现、协议、边界与限制说明 |

Python 新测试位于 `tests/test_agent_runtime.py`，原字段断言在 `tests/test_agent_state.py` 调整；覆盖显式目标、模拟模型修订、Agenda / busy 文件恢复、Java 刷新、保存载荷、同名角色多世界隔离、旧快照、私有认知、原事件行为、单行动限制及总结失败后的保存。

边界修正新增验证：模型创建/替换/清空 Agenda、声明 pending/completed/cancelled、设置/清空 busy 均被拒绝；混合有效目标切换也不能部分落地；活动愿望仅修改认知，程序维护的三种 Agenda 状态与 busy 可恢复；Prompt 明确区分可写与只读上下文。Java 测试补充程序维护的 completed/cancelled 与 busy 清空的保存恢复和多世界隔离。

Java `WorldMcpToolsTest` 使用 H2 测试现有 WorldStore 快照的持久化与重新连接、两个世界隔离、旧客户端兼容、业务字段不可覆盖及无效认知拒绝。测试不请求真实 LLM API，也不连接运行中的 MySQL 世界。

初版验证：仓库 `.venv` 运行 Python 全部 53 个测试通过；离线 Maven 运行 Java 全部 20 个测试通过；`git diff --check` 通过。Java 编译在沙箱内遇到本地 JAR 的 AccessDeniedException，经获准的沙箱外离线执行后通过。MySQL 生产配置和表结构保持原状，本次持久化自动测试使用 H2，未运行真实模型或真实世界的在线验收。

模型与系统调度状态边界修正后：Python 全部 56 个测试通过，Java 全部 20 个测试通过，`git diff --check` 通过。本次仅修改 runtime 模型更新白名单、Prompt、对应 Python / Java 测试及本文，没有修改 Scheduler、世界规则或持久化格式。

尚未实现：Agenda Scheduler、完整 Goal Manager、ConversationSession、Player Actor、新 Object Model、通用 take / put、Location 拓扑、travel_time、Belief System、Reflection / Social / Relationship 重构、经济和天气系统。没有开始 Phase 2，也没有新增 deterministic Skill Workflow。
