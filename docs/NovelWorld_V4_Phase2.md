# V4 Phase 2：Event Reaction + Agenda 双驱动

本阶段从已审查的 `v4-phase1`（`46d949c8273785f393d883b8195331ab1ad25609`）建立 `v4-phase2`。延续 Phase 1 的认知与调度状态边界，只增加未来自主行动机会，不生成 Tool sequence。

## 调用链与职责

`WorldSession.next_tick` → `WorldTickScheduler.run_tick` → 同步 Java 事件 → 根据 `perceived_by` 和原有知识边界收集反应 → 选择一个行动机会 → Agent Loop 根据本人目标、认知、感知、Memory/RAG 和 Skill 上下文决策 → MCP 请求 Java 校验、结算世界行为 → 程序消费机会、维护未来提醒 → Java 推进世界时间 → 处理新事件与原有 Reflection → 保存 Agent 状态。

一个 Tick 仍最多一个成功 world action；此限制由已有 Agent Loop / Tool 调用边界保持。Scheduler 不因 Agenda intention 直接调用具体工具。零体力的原有程序休息行为保留。

模型可修订 `active_goal / current_intention / current_plan`。模型不能写 Agenda、ID、状态、到期 Tick 或 `busy_until`。自然语言中的完成、忙碌或时间声明不自动成为运行时事实。

## 调度优先级与时间

1. Event Reaction：保留事件接收者、队列去重和 `MAX_REACTION_DEPTH`。
2. Due Agenda：仅扫描本人 runtime 中 pending、`due_tick <= tick_count` 且可行动的条目。
3. 原有 bootstrap / Skill 兼容机会：明确标记来源，保留旧行为。
4. Idle：没有上述机会才空转，Director 仍可按原规则注入事件。

旧存档 pending 缺少 source，恢复为 `legacy`。因无法可靠区分旧事件与开局队列，保留其顺序并采用事件优先级，避免降低已保存 Event Reaction 的优先级；新存档明确记录 event/bootstrap/skill。

多个 Agenda 按最早 due_tick、世界中稳定角色顺序、条目顺序选择，无随机调度。Agenda 只在被选中后消费；因此同时到期的其他角色仍保留更早提醒，随后获得机会。

`due_tick / busy_until / scheduler.tick_count` 使用相同累计 Tick 坐标，不使用会在午夜回绕的 HH:mm。选择时使用本 Tick 开始的计数；正常完成后计数加一，下一提醒从完成后的计数加三。例如开始计数为 0，机会完成后计数为 1，新提醒 due_tick 为 4。

`current_tick < busy_until` 时 Agenda 不能唤醒，等于 busy_until 时可唤醒。busy 不改变原有 Event Reaction 和 bootstrap 行为。本阶段不自动设置 busy，也不增加事件紧急程度或复杂中断策略。

## Agenda 创建、消费与去重

沿用 `AgendaEntry(id, character, due_tick, intention, status)`，不增加中间状态、PlanStep 或任务执行器。

程序入口为 `AgentRuntimeState.schedule_next_agenda`：若已有 pending 则返回现有提醒，不重复创建；否则有有效 active_goal 时创建系统 UUID、pending 状态、`current_tick + DEFAULT_AGENDA_DELAY` 的条目。`DEFAULT_AGENDA_DELAY = 3`，文字依次取 current_intention、current_plan、active_goal。调用方过滤失去行动能力的角色。正常运行每个角色最多一个 pending 自主提醒，恢复旧数据不擅自删除额外条目。

bootstrap、reaction、Agenda 或旧 Skill 兼容机会完成后，程序检查是否需要下一提醒。没有目标或处于 unconscious 状态时不创建。固定间隔只决定何时再思考；不会从 Plan 或 Skill workflow 生成工具，也不解析“明早”等愿望的具体时间。

Agenda 机会正常决策后将选中的 ID 标记 completed，包括选择等待、没有生成世界事件的情况。completed 仅表示已消费一次思考机会，不表示完成意图、计划或世界目标。仍有目标时创建冷却后的下一提醒。新观察和事件到来时，角色始终重新决策。

Agenda 是当前调度状态，不是历史日志。`prune_agenda` 删除所有 completed / cancelled 条目，仅保留有效 pending；正常每名角色最多一个 pending，因此自主续排不会使列表增长。消费后立即清理，即使角色失去行动能力或没有下一目标也不保留终态。程序创建下一提醒前、选择 Agenda 时和 `to_dict` 序列化保存前也清理；旧存档经 `from_dict` 完整验证后只恢复 pending，不丢失其 ID、时间、意图或 busy_until。旧存档的多个有效 pending 仍兼容保留，不擅自取消。历史行为继续由 Event / Memory 表达，没有 AgendaHistory 或新数据库表。

Prompt 的只读调度投影只包含 pending Agenda 的 intention / due_tick 和 busy_until，不展示内部 UUID、character、status 或已结束条目，即使传入的是带历史条目的旧 runtime_context 也先过滤。内部 ID 仍用于定位消费条目和保存恢复；模型可写字段白名单不变。Java 内部保存通道继续兼容旧格式，Python 清理后的当前列表在下一次保存时替换对应世界的旧快照列表，不在 Java 追加历史。

事件优先时不会删除 Agenda。同一角色已经因事件获得机会，其到期 pending 提醒顺延到本次完成计数加三，避免下一 Tick 立即重复唤醒；其他角色提醒不受影响。尚未到期的提醒保持原时间。Agenda 被选中时删除同一角色遗留 bootstrap / Skill 兼容机会，避免重复排队。没有自动推断取消或目标完成。

Agenda 来源不读取 Skill current_step，也不追加 Skill workflow 的下一步兼容机会。原有非 Agenda 来源的 Skill 续排保持兼容；Agent Prompt 仍可使用现有 Skill 上下文。本阶段没有重构 Skill。

## 异常与保存恢复

行动发生前抛异常：Agenda 保持 pending，累计 Tick 不推进；原有事件/兼容机会重新入队。等待属于正常完成，并非异常。

Java 行动已提交并产生事件、模型随后总结失败：沿用事件增长判断，机会被消费，避免重放。消费在推进时钟之前完成，因此随后时钟请求或 Director 失败也不会重放该 Agenda。更新时按 ID 查找当前 WORLD_STATE 的 runtime，避免 Java 刷新 Character 或模型 cognition 修订重建 runtime 后修改失效对象。

`WorldSession` 的 finally 将 completed_ticks 对齐 scheduler.tick_count，并保存成功或失败后的状态。Director 失败时不会留下会话与 scheduler 的不同计数。

唯一状态来源仍是当前世界 `Character.runtime_state`；Scheduler 只保存 Tick、事件游标、队列与反应深度，没有第二份 Agenda/认知注册表。原有 `save_agent_state` MCP → Java WorldMcpTools → WorldStore/MySQL 快照保存 runtime 与 scheduler；本地 save_world 继续按原方式留存恢复快照，Chroma 继续是可重建索引。世界切换使用对应世界快照，保留已有隔离规则。

Java 仍是世界事实和规则的唯一权威。成功世界行动不自动改写 Agenda；运行时机会消费由 Python 程序维护，再走现有内部保存接口。NPC 可调用工具列表没有新增 save_agent_state 或调度写入工具。

## 修改文件与验证

- agent/runtime.py：程序创建与去重入口、固定冷却常量、终态清理及旧状态恢复过滤。
- agent/tick.py：机会来源、优先级、busy 过滤、消费与续排、旧队列恢复。
- agent/session.py：异常后对齐会话累计计数，保持原保存链。
- characters/prompt.py：说明 Agenda 提醒和 completed/busy 的实际语义，只投影当前 pending 的 intention / due_tick 与 busy_until。
- tests/test_agent_runtime.py：验证历史快照与保存载荷清理、Prompt 不展示历史或内部 UUID。
- tests/test_agenda_scheduler.py：双驱动、失败、等待、时钟、保存恢复、多世界、Skill 边界和行动预算测试。
- tests/test_current_runtime.py、tests/test_skill_routing.py：适配长期自主提醒和明确来源，保留旧 Event / Skill 验证。
- world-service/src/test/java/org/novelworld/world/WorldMcpToolsTest.java：覆盖 Phase 2 runtime/scheduler 的保存恢复、世界隔离和世界行动不改 Agenda。
- 本文：记录本阶段实际语义与限制。

Python 使用 deterministic / mocked Agent 和 backend，Java 使用测试数据库；不调用真实 LLM。清理修正新增 1000 Tick 多角色循环及周期保存恢复测试、1000 条旧终态恢复与载荷清理测试；Java 验证反复保存当前 pending 列表后快照不会追加历史。Python 全部 86 项 tests 与 Java 全部 20 项 tests 通过；git diff --check 通过。

## 已知限制与后续范围

- 固定间隔提醒，不解析日历、自然语言时间或具体活动耗时；busy 只尊重系统既有值。
- 严格事件优先时，持续反应可能推迟 Agenda；公平选择只覆盖到期 Agenda 之间。
- 旧存档若没有 pending、也没有 Agenda，不凭空重建开局机会；需要一次事件、Director 注入或显式程序安排才能建立后续提醒。
- 当前 action、时钟和 save_agent_state 仍是分开的调用，进程在保存前硬退出时不保证跨调用事务或 exactly-once；本阶段覆盖的是正常异常处理与已保存状态恢复。
- cancelled 旧条目验证后清除，不自动推断取消；目标变化后旧 pending 提醒仍只是重新思考机会。

没有实现 Phase 3 ConversationSession、Player Actor、Object Model、take/put、Location 拓扑、travel_time、Belief、关系/Reflection 重构、全面 Skill 改写、社会/经济/天气系统、Redis 或复杂日历。没有 Planner Executor、Workflow Engine、TaskGraph 或 Quest Engine。
