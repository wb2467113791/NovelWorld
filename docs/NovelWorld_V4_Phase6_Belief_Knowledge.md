# NovelWorld V4 Phase 6：Belief / Knowledge Model

基于已审查的 `v4-phase5-player` 提交 `8c824b8197c105f9d1ae0c27d18af9a91709dad3`，在 `v4-phase6-belief` 实现。保留作者未提交的 AGENTS.md 测试约定，没有修改或合并 main，没有开始下一 Phase。

## 实际知识来源与职责

| 层 | 当前来源与含义 |
| --- | --- |
| World Truth | Java WorldRules/WorldObjects 校验并保存的角色、物品等业务状态；NPC 无权读取全部真相 |
| Observed Fact / Semantic Knowledge | NPC 通过真实 inspect Event 获得的直接观察；沿用 SemanticFact 与 superseded_event_ids |
| Reported Claim | 某 Actor 在真实 talk 中说过的完整消息；Event 证明说过，不证明内容正确 |
| Belief | NPC 持有的有来源说法和开局认知；影响决策，不结算世界行为 |
| Memory | 本人经历的事件摘要与反思；保存说话经历不等于相信或验证内容 |

`known_facts` 保留原开局模板、存档、UI 和 Skill 兼容职责，解释为“角色原有开局认知”，不强制当作 Java World Truth。每个 NPC 建立 source_type=initial、confidence=1.0、status=active 的对应条目；initial 的高置信标记来自设定，不代表内容已由世界行为证明。

采用推荐的方案 A：semantic_memory 继续只保存已验证观察；新增 belief_memory 保存 subjective reports / initial knowledge。观察的来源类型是 observation，由现有 SemanticFact 表达，并在 Prompt 标为直接观察、confidence=1.0；不把同一观察再复制到 BeliefMemory。未实现 inference 类型和推理引擎。

## 最小数据模型与增长策略

`Character.belief_memory` 是每 NPC 独立的 `BeliefMemory`。PlayerActor 没有该字段。

BeliefEntry 字段：id、owner、content、source_type、source_actor、source_event_id、confidence、status、order、evidence_event_ids。

- source_type 为 report 或 initial；本阶段状态只有 active，不提供模型声明 verified/disproven 的入口。
- report content 是 talk message 原文，source_actor 是实际说话者，confidence 固定 0.5。
- initial 来源是本人 known_facts，source_actor 为本人，confidence 固定 1.0；没有来源 Event 或 evidence。
- order 是最近来源在本世界 Event 列表中的序号，initial 为 0；不是 HH:mm 或 Agenda Tick。
- ID 按 owner、来源类型、来源 Actor 和规范化文字生成；没有跨世界注册表。
- 同一来源 Actor 的同一规范化文字合并。仅折叠空白，不做语义匹配；不同来源的相同/矛盾说法分别保留。
- 每 NPC 总计最多 50 条，保留最近来源，超出丢弃较旧上下文；每条最多 5 个最近证据 Event ID。重复消息不会提高 confidence。
- 被裁剪的说法不建立 Claim Archive；原 Event 和 episodic Memory/RAG 保留。known_facts 兼容字段也不会因为 Belief 裁剪而删除。

## Event → Report 与观察规则

`RemoteWorld.execute` → Java 提交真实 Event → 刷新业务镜像 → `remember_event` → NPC Memory；对 talk，同时以当前世界已提交的来源建立 report。只有事件实际可见的 NPC 接收者获得条目，说话者不因为自己的发言给自己建立 report 或 verified fact。Player 的发言同样可作为来源。

report 不调用任何物理动作，不更新 objects.location/holder、NPC known_facts、关系或 semantic_memory。两个矛盾来源并存，程序不决定谁是真的，不做 NLP 命题提取、欺骗检测或说谎检测。

inspect 继续走 Java WorldObjects，并仅给执行者写入原 SemanticFact。新的本人观察按原地点/对象键取代旧观察，并记录 superseded 来源；旧 Memory 历史保留，现有检索过滤机制继续排除被替代的观察与引用它们的 Reflection。没有读取隐藏 World Truth 来自动纠正 report，也不自动把内容相似的 report 标成 verified/disproven。

## Prompt、RAG 和模型权限

Prompt 明确区分：

1. 开局认知（initial，不等同于 World Truth）。
2. 已验证事实（本人直接观察，也可能过时，附来源时间）。
3. 未验证说法 / Beliefs（来源 Actor、消息原文、未验证和固定 confidence）。
4. 近期经历、检索到的历史经历与现有 Conversation。

已验证区使用本人 semantic facts 和 RAG 原有 `已核实调查` 标签；episodic 检索结果放入历史经历区。Chroma 仍只检索本人可见的 Memory、verified semantic 和 Lore，未修改 collection、向量模型或增加嵌入调用。

当前报告上下文直接从本人最多 50 条 Belief 读取，展示最多 8 条、总计最多 1400 字，避免把全部说法列表送入 Prompt。没有新增向量 Belief collection；更旧说法仍可从带来源的 episodic Memory 找回，始终标为经历而非已验证事实。

模型可以决定如何考虑不同来源，以及据此修订 active_goal/intention/plan；Belief 完全只读。没有新增 belief_updates JSON 协议、置信度更新、mark_verified 或世界状态写入入口。原 cognition 白名单、Agenda/busy 只读和一个 Tick 最多一个成功行动保持原规则。

Reflection 仍是 Memory / salience，不进入 verified semantic 或自动产生 Belief。没有改写 Reflection、Social、Skill、Scheduler 或 Conversation。

## 保存恢复与 Java 校验

belief_memory 与 NPC Memory、semantic_memory、runtime_state 一同进入原 Python snapshot 和 MCP `save_agent_state`。Java 保存到已有 MySQL JSON snapshot 的 NPC Agent 状态，不新增表；WorldRules 和 Player physical rules 不读取它。

Python restore 验证归属、字段、数量、固定 confidence、真实来源与顺序后才替换当前世界。缺少 belief_memory 的旧快照从 known_facts 和本人可见的真实 talk 迁移有限近期说法，原 verified semantic 不降级。存在该字段时恢复保存的当前状态，不反复重建被裁剪的历史。

同世界 RemoteWorld 刷新保留未保存的本地 NPC Belief；跨世界只恢复目标 snapshot，不合并旧世界报告。原 WorldController 的切换、保存和失败回滚链自然包含同一字段。

Java `WorldBeliefs` 在导入与 Agent 保存时校验：

- owner 必须是 NPC，不能给 Player 建立 Belief。
- 每条的 owner、ID、来源类型、status、字段和去重键有效，总量不超过 50。
- report confidence 必须为程序的 0.5，initial 为 1.0，均须为有限数值。
- report 的全部证据必须是本世界真实 talk、对 owner 可见、Actor 与消息原文规范化对应；不得引用自己的说话作为别人提供的报告。
- 最新 source_event_id、证据顺序和 order 必须对应；证据最多 5 条。
- initial 只能来自 Java 保存的本人 known_facts，不能伪造 observation、verified 状态或来源。

校验在修改保存字段前完成，拒绝不改变数据库快照。旧客户端省略 belief_memory 时保留已保存数据；整个保存接口仍不能覆盖 Java 物品、玩家或时间等业务状态。

旧 Event 缺少 perceived_by 时，迁移和校验只承认直接说话参与者，不能根据当前地点补造历史听闻。

## Player 与界面边界

Player talk 经过原 Play API、MCP 和 Java rules，NPC 可以获得 source_actor=Player 的 report。玩家本人没有 Belief/semantic/Reflection/RAG。Play projection 不添加任何 NPC Belief、秘密、目标或私有知识；Observe/Play 和 SSE 行为保持 Phase 5B 实现。

## 验证与限制

复用全部现有回归测试，只在现有文件中新增 2 个 Python 综合用例和 1 个 Java 综合用例，并更新新增保存字段的一处断言。没有新增测试文件或展开大量组合用例。

Python 全部 165 项、Java 全部 85 项通过；React build 和 git diff --check 通过。核心综合验证包含：玩家虚假说法不移动真实物品、不写 verified semantic、本人 report 来源与 Prompt 分区、相互矛盾报告、重复与数量上限、保存/刷新/旧快照/世界隔离，以及 Java 伪造来源/Actor/owner/置信度/状态/不可见证据的原子拒绝。原 Agenda、Conversation、Object、Player、Reflection、RAG 和一 Tick 一个行动测试继续通过。测试使用 mocked 行为与 H2，不请求真实 LLM 或生产 MySQL。

已知限制：报告是完整消息而非正式命题；confidence 是来源标签而非校准概率；不判断矛盾、不自动关联观察与报告、不做 Belief 验证/否定/语义去重；已验证观察仍遵循原 superseded 键和历史规则，不能自动知道未感知的物品移动。说法展示采用最近上下文，更旧信息依赖原 episodic RAG；没有增加独立 Belief 检索模型或 UI 编辑器。

未实现 inference、知识图谱、NLP parser、社会信任、关系演化、经济、Quest、派系、日历重构、travel_time、多玩家、Redis 或其他后续 Phase。没有新增 Workflow、TaskGraph 或 Planner。
