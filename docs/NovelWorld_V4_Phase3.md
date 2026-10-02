# V4 Phase 3：ConversationSession

基于已审查的 `v4-phase2`（`b231a9fc9047c326356de299ea261c04c783f372`），在独立 `v4-phase3` 分支实现持续双人交流。没有修改 main，没有开始后续 Phase。

## 真实说话调用链与职责

`create_initial_agent_state` → LangGraph 模型决策 → `execute_pending_tools`（保持每 Tick 最多一个成功行动）→ `execute_tool` 校验当前 actor → RemoteWorld MCP `execute_world_tool` → Java WorldMcpTools / WorldRules 校验 actor、双方同地点、消息与说话者体力 → Java 保存 talk event → RemoteWorld 刷新世界与补写本人可见 Memory → Scheduler 根据真实 talk event 维护 Conversation。

LLM 决定想对谁说什么，以及是否希望结束；Python 程序创建 ID、决定 participant 集合、排序消息和维护生命周期；Java 校验并结算真实说话。普通文本回复不会自动作为消息发送，也不能成为世界事实。没有新增 world action 或绕过 Java 的 speak 通道，原 talk、perceived_by、Event、Memory、RAG 保留。

## 唯一状态来源与结构

唯一活动会话来源为当前世界 `WORLD_STATE["active_conversations"]`，内容是 `agent/conversation.py` 的 ConversationSession 对象。角色 runtime_state 和 Scheduler.pending 不保存第二份会话，也没有 active_conversation_id 字段或跨世界角色名注册表。

ConversationSession 包含 id、participants（两人）、location、status、messages、started_tick、last_activity_tick、next_speaker。ConversationMessage 包含 speaker、content、tick、event_id。轮数直接等于 messages 长度，不复制一个容易不同步的计数。event_id 是程序内部用于真实事件校验与去重的引用，不展示给 NPC。

时间与 Agenda、busy_until 同用 scheduler.tick_count。实际消息登记使用当前 Tick 开始的计数；随后推进 Java 世界时间和累计 Tick。状态支持 active / ended，ended 会立即移出活动列表。active 会话最多保留 12 条当前实际消息，结束后不保留全文运行状态，也不建立 Conversation Archive。长期历史继续在 Event / Memory。

## 调度优先级

1. Event Reaction（包括按旧策略恢复的 legacy 队列）。
2. Active Conversation Turn。
3. Due Agenda。
4. bootstrap / 原 Skill 兼容机会。
5. Idle。

Conversation 选择按 last_activity_tick 最早，再按稳定会话顺序，不随机；同 Tick 平局仍按稳定顺序，更新活动 Tick 后另一个较旧会话优先。会话轮次不读取 Skill 的 next step、不追加 Skill workflow 续排；Prompt 仍使用原有 Skill 上下文。Director 保留，Director=None 也可继续会话。

Conversation 的参与者不会因普通 Agenda 额外唤醒；busy 原因通过活动会话成员判断，不改写 busy_until。会话轮次使用 depth=0，不由普通 talk reaction 链维持。

## 创建、回复、去重、结束

Scheduler 收集新事件时，只有当前双方仍可行动、仍在事件地点且消息对应已提交 talk 时，才纳入 Conversation；不适合会话的 talk 仍保留普通事件处理。第一条消息创建系统 UUID，会话下一轮指向 listener。同一对角色已有活动会话时追加真实消息并切换 next_speaker，不创建重复会话。

同一角色不能同时参加冲突会话。若 Java 已经允许并提交了与新对象的 talk，程序结束冲突旧会话，再建立新会话；不因会话占用增加新的 Java 行动限制。

talk event 不删除或改写，Memory 与 timeline 继续读取原事件。成功纳入会话的 talk 不再给 listener 增加普通 event pending；如已有其他事件反应则保留，其优先级仍高于会话。其他允许的知情者按原事件规则处理。消息按 event_id 去重，Scheduler 的原 event_cursor 随保存恢复，避免已处理 talk 重复追加。

`MAX_REACTION_DEPTH = 3` 继续保护普通世界事件连锁；Conversation 无论从哪一层反应开始，都不受此深度截断。独立 `MAX_CONVERSATION_TURNS = 12` 限制实际消息数，达到上限后移出活动状态，最后一条 talk event / Memory 仍保留。

以下条件结束会话：

- 模型明确提出 `continue_conversation=false`。
- 会话轮次没有成功提交 talk，包括等待、工具失败后选择等待、改做调查或其他行为；不给同一空回复无限续排。
- 任一参与者离开地点或 unconscious。
- 消息达到 12 条安全上限。
- 连续 8 个累计 Tick 没有新实际消息（CONVERSATION_TIMEOUT）。

外部事件反应本身不因没有 talk 就结束会话。事件处理后条件仍满足且没有显式结束时，原 next_speaker 保留，后续可继续。普通事件不新增紧急程度或复杂中断策略。

Conversation 结束不等于 Agenda completed。会话行动机会沿用 Phase 2 的非 Agenda 续排规则：到期提醒保持 pending 并顺延冷却；有目标且无 pending 时可建立下一自主提醒。会话结束释放占用，随后仍按普通 Agenda 规则获得机会。

## 模型协议、感知与知识边界

模型可以在普通回复中输出：

```json
{"continue_conversation": false, "answer": "我需要先处理其他事情，结束这次交流。"}
```

字段必须为布尔值并有 answer 文字。它只表达意愿，由 WorldSession 的 DecisionResult 携带到 Scheduler 决定生命周期；不直接修改 Session。调用 talk 表示实际继续，true 不能在没有真实 talk 的会话轮次强迫续排。即使返回 false，已经由 Java 提交的 talk 也必须先登记，然后才结束。

cognition 白名单仍只有 active_goal、current_intention、current_plan；Agenda、busy_until 和 Conversation 结构都不可由模型修改。当前 LangGraph 的 `conversation` 字段仍是一次模型工具循环的 API 消息上下文，与持久 ConversationSession 是不同概念。

Prompt 只展示本人的活动会话对方、your_turn、最近 6 条 speaker/content/tick，不展示 Session ID、event_id、其他会话或其他角色私有认知。非 participant 只能通过原 perceived_by / witness 和 Memory / Perception 知道实际 talk；没有因全局会话列表扩展知识。没有实现会话摘要、social memory 或 belief extraction。

## 保存恢复与异常

snapshot_world / restore_snapshot 增加根字段 active_conversations。旧快照缺少字段时恢复为空，不根据历史全部 talk 自动补建会话。先验证会话字段、时间与顺序、成员不冲突、消息匹配本世界 event，再一次替换当前世界。ended 的兼容输入验证后丢弃。恢复后下一 Tick 检查地点、行动能力和 inactivity，决定是否仍可续轮。

同世界 Java 行动刷新保留未保存的 Python 活动会话；不同世界不继承。本地存档与 MCP save_agent_state 都包含同一来源的会话序列化。Java 内部保存接口校验每条消息的 event_id、speaker、content、参与者、location、事件顺序和消息上限，只有匹配本世界已提交 talk 才保存。新字段写入已有 WorldStore / MySQL JSON snapshot，没有新数据库表、Redis 或另外的存储服务。Java 验证在修改保存字段前执行；旧客户端未携带会话字段时不清空会话，明确空列表则解除活动状态。

行动前模型异常：会话 next_speaker / messages 不变，不将会话轮次插入普通 pending，可重试。

talk 已提交、模型总结失败：在推进时钟前收集 talk、追加一次消息并切换轮次；原 event_cursor 和会话一起保存。时钟推进随后失败也不重新给已说话者同一轮次。Java 刷新可能重建会话对象，处理始终从当前世界获取会话，不修改过期对象。WorldSession finally 保留原有保存链与累计 Tick 对齐逻辑。

没有新增事务层：Java action、时钟和 runtime save 仍是分开的调用，保存失败或进程在保存前硬退出不保证跨调用 exactly-once。此次测试覆盖正常异常处理与已保存状态恢复，未请求真实 LLM / 在线 MySQL 验收。

## 文件与测试

| 文件 | 改动 |
| --- | --- |
| agent/conversation.py（新增） | 最小模型、生命周期、真实事件接收、去重、感知投影、恢复验证 |
| agent/tick.py | 会话轮次优先级、talk listener 去重、结束和占用处理 |
| agent/state.py、agent/graph.py、agent/session.py | 轻量交流意愿协议与结果传递，保持原 Agent Loop 行动预算 |
| characters/prompt.py | 本人当前会话与模型只读边界 |
| world/state.py、world/persistence.py | 当前世界唯一活动列表及快照恢复 |
| tools/remote_world.py | 同世界刷新保留会话、内部 MCP 保存载荷 |
| WorldMcpTools.java | 保存和导入时核对会话真实 talk 引用 |
| tests/test_conversation.py（新增） | mocked Agent / backend 的完整会话边界与调度测试 |
| tests/test_agent_state.py | 更新交流意愿字段断言 |
| ConversationPersistenceTest.java（新增） | H2 保存恢复、隔离、消息不可伪造、上限、结束清理和 Java talk 校验 |
| 本文（新增） | Phase 3 实际语义、唯一来源与限制 |

验证：Python 全部 119 项测试通过，Java 全部 25 项测试通过，git diff --check 通过。保留原 Agenda 的 1000 Tick 有界增长、Event、知识隔离、Skill、world switch 和单成功行动回归。新测试包含真实会话续轮超过普通反应深度、100 次会话创建/结束的 runtime 无历史堆积、消息保存恢复、总结/时钟失败不重复说话、角色刷新后的当前对象更新，以及 WorldController 切换世界失败时的会话回滚。

## 已知限制与未实现内容

- 仅双人会话，不实现群聊、邀请/拒绝协议或事件中断严重程度；真实新对象 talk 直接取代冲突旧会话。
- 无 talk 的会话轮次即结束，尚未区分礼貌暂停、思考或长期等待；8 Tick inactivity 是简单程序阈值。
- 严格事件优先可能让会话超时；12 条消息上限只用于安全保护，不是正常剧情长度目标。
- UI 沿用现有 talk timeline / SSE，没有新增会话展示组件或玩家聊天框。
- Event / Memory 历史仍沿用原保存方式，本阶段只限制活动会话数据，不重构全部历史存储。
- 未实现 Player Actor、Object Model、take/put、拓扑和 travel_time、Belief、Conversation summary、Social memory、Relationship evaluator、Reflection / Skill 全面重构、Voice/WebSocket 体系或其他后续 Phase。

没有新 Workflow、PlanStep、TaskGraph 或 Planner Executor。
