# NovelWorld V4 Phase 5B：Player Actor 与最小 Play Mode

基于已审查的 `v4-phase5-cleanup` 提交 `66eb400640e99a83432dcf50d8b108be5862e22c`，在 `v4-phase5-player` 实现。没有修改或合并 main。

## 数据模型与权威来源

每个世界在统一 `characters` 集合中保存一个 `actor_type=player` 的角色，NPC 为 `actor_type=npc`；旧 NPC 缺少此字段时默认 npc。Player 的字段只有 name、location、energy、hp、status、relationships、items 和 actor_type。items 仍由 Java objects.holder 派生，不是物品权威来源。

Java 直接复用既有角色 Map 和全部 WorldRules/WorldObjects 校验。Python 使用独立、无继承的 `PlayerActor` dataclass，共用物理字段形状，不强行给玩家创建 NPC goals、runtime_state、Memory、Skill 或 Agenda。Python 保存和读取的是 Java 业务镜像，没有第二份 player_actor 实体或跨世界玩家注册表。

## 创建、保存和世界切换

Java `WorldActors.ensure` 在 WorldStore 的原有快照加载、插入和更新链中迁移旧世界。默认姓名为“玩家”，地点为 locations 的第一个合法地点；若与 NPC 同名，依次尝试“玩家2”“玩家3”。同一个旧世界重复加载得到相同默认实体，下一次原有世界保存将迁移结果写入既有 MySQL JSON snapshot，不新增表。

World Template 可以提供 `player: {name: "旅人", location: "晚风客栈"}`。显式配置姓名冲突或地点无效会拒绝创建。现有开局工坊的 JSON 模板编辑器可以填写该字段，没有增加账号、角色绑定或多人模型。每个世界只允许一个 Player。

Player 物理状态、objects 和真实 Event 由 Java 持久化。Python 本地存档也序列化 PlayerActor，但 `save_agent_state.characters` 只上传 NPC Memory/认知；Java 按 NPC 集合校验并拒绝 Player 认知载荷，不允许该保存接口覆盖玩家物理状态。Conversation/Scheduler 仍随原保存链持久化。

RemoteWorld 同世界刷新只保留 NPC 未保存的记忆和认知，不把旧 Player 物理字段合并回 Java。世界切换沿用 WorldController 的保存、加载和失败回滚，Player 与该世界一同恢复；旧本地种子首次导入 Java 后也由同一迁移链补建 Player。

## 行动调用链与 API

Human Input → React PlayMode → Spring Boot → 内部 Python WorldController → Player 输入白名单和身份注入 → 现有 execute_tool → RemoteWorld → MCP execute_world_tool → Java WorldRules/WorldObjects → WorldStore → 真实 Event → NPC Memory、Conversation、后续 Reaction。

浏览器只访问 Java：

- `GET /api/play/state`：当前 Player 的可见投影。
- `POST /api/play/action`：`{world_id, action, arguments}`。
- `POST /api/play/conversation/end`：`{world_id}`，程序结束当前玩家会话。

world_id 用于拒绝世界切换后旧页面提交。Player 身份从服务端当前世界取得，arguments 中的 character、speaker、actor、giver、actingCharacter 一律拒绝；工具所需行动者字段由程序注入，不能控制 NPC。额外参数、错误类型和缺少必需参数也拒绝。

Player surface 为 inspect、take、put、give、use、interact、move、talk、rest；move/rest 映射到既有 move_character/rest_character。没有暴露 update_relationship、旧 Tool wrapper、内部保存接口或自由 world_action。Java MCP 也限制 Player 的工具范围，并继续核对 actingCharacter。Player 没有绕过位置、holder、可见性、portable、affordance、状态或体力校验的特殊分支。

这些 API 只路由输入，不直接修改物理状态。玩家不会调用生成模型；NPC 仍在其自己的后续机会中由 Agent 决策。原有 NPC Chroma 同步继续保留，Player 不创建 Chroma owner、不使用 RAG。

## Scheduler、时间和异常

NPC 优先级保持 Event Reaction → 可执行的 Conversation Turn → Due Agenda → bootstrap → Idle。bootstrap、恢复的 pending、Event recipients 入队、Agenda 扫描、Reflection、Skill/Agent 入口、Chroma 和 Director 的 NPC 参与判断都排除 Player。Player 仍可成为事件目击者、交谈/交付对象和 NPC 行动目标；真实玩家行动可以计入 Director 的世界活动历史。

Play 与 NPC Tick、世界切换共用 WorldController 的同一锁。NPC 正在执行时，Play 请求立即返回可读冲突错误，不排队执行旧输入；其他时刻玩家行动与 NPC Tick 串行。前端只重试读取状态，绝不自动重放 action。

成功 Player world action 独占一个正常 Tick：Java 提交一个真实行动，登记事件/会话，累计 Tick 加一，Java 时间推进 TICK_MINUTES=5。消息登记使用本 Tick 开始的计数。该请求不选择 NPC、不调用 NPC 决策、不执行 Director 注入；下一 Tick 才处理 NPC reaction/conversation/agenda。

Java 拒绝行动时不生成新 Event、不推进时间或累计 Tick、不消费 NPC pending/Agenda。显式结束会话属于 Session 生命周期操作，不产生虚假 talk、不推进 Tick。

Java 提交后刷新、时钟或 runtime 保存失败时返回 committed=true 和 warning，不自动再次执行工具。RemoteWorld 用 CommittedActionError 区分“已提交但刷新失败”；NPC 也不会因此重新排入原机会。已经提交的真实 talk 在正常登记后保持原 Session 轮次，后续异常不凭空重复说话。

没有新增跨 Python/Java 事务或 HTTP 幂等请求系统。action、时钟和 runtime save 仍是分开的调用；时钟失败可能使累计计数与 Java 时间暂时不一致，进程硬退出或网络丢失响应也不提供 exactly-once 保证。warning 明确表示行动已经发生，不应盲目再次提交。

## Player Conversation、感知与 Memory

Player talk 必须先通过 Java 同地点和体力规则，生成真实 talk Event；现有 accept_talk 将它建立或追加到双人 ConversationSession。next_speaker=NPC 时正常调度；next_speaker=Player 时跳过该会话并等待人类输入，不替玩家调用 Agent，也不阻塞其他会话、Event、Agenda 或 Idle。

玩家对原 partner 的下一条真实 talk 追加原 Session；改与其他 NPC 说话沿用冲突旧会话结束规则。显式结束 API、离开地点、失能、12 条消息上限和 8 Tick inactivity 都沿用现有生命周期，没有新增 Conversation Archive。

Play state 只包含自身物理状态/关系和可见 inventory、当前地点描述、附近角色公共状态、可见对象的 ID/name/type/state/portable/affordances、本人会话最近 6 条消息、最近 30 条本人可感知 Event 描述、合法地点及行动 schema。没有 NPC secrets/goals/private Memory、hidden 对象、关闭容器内容、他人会话、对象内部 properties/owner 或未 inspect 的 description。

Java perceived_by 可以包含 Player。Player 不建立 NPC Memory；界面从事件和本人会话展示感知。NPC 对玩家真实行动仍按 perceived_by 写入原 Memory/RAG，玩家不是事件系统中的例外。

## Observe / Play UI

React 增加独立 PlayMode 组件和 Observe/Play 切换。Observe 原有状态、关系、Memory、Timeline、Intervention、Run/Pause 和开局工坊保留；运行控制仍可用于推进下一 NPC Tick。

Play 提供玩家状态、附近角色选择、对话输入/当前交流/结束按钮、地点选择、对象查看/拿取/affordance 操作、持有物品放下/放入容器/交付。所有对象与目标选择来自服务器，不要求用户手填 object_id。

沿用 `/api/events` SSE，Play 模式 `?mode=play` 只发送 world_id/time/tick_count/running/event_count/revision 刷新信号，随后读取过滤后的 Play state；不发送 Observatory 的 NPC goals、全局事件或 Memory。切换 Play 时关闭原观察流并停止 NPC Memory 查询；action 后也主动刷新。没有新 WebSocket 系统。

## 验证与范围

全部 Python 163 项、Java 84 项通过；React build 和 git diff --check 通过。新增测试只使用 mocked/deterministic 行为，Java 持久化使用 H2，没有请求真实 LLM 或连接生产 MySQL。

测试覆盖模型/快照隔离、NPC 系统排除 Player、服务端身份白名单、可见信息过滤、真实 talk 会话续接与等待公平性、成功/失败 Tick 语义、提交后异常、WorldController 锁与切换回滚，以及 Java primitives、旧存档/模板、物品 holder 与 Player 认知保存边界。原 Phase 1–5A 测试全部保留，旧测试载荷改为明确的 NPC 集合。

已知限制：单世界单 Player；同地点可见性的简化规则；双人会话沿用原超时和消息上限；默认 Object 少数 affordances；UI 未做地图、战斗或 inventory grid；本次验证不包含真实模型表现和在线 MySQL 全链路验收。

未实现 Belief、Social Memory/Relationship 演化、经济、Quest、多玩家、登录绑定、PvP、地图、travel_time、日历升级、Player Skill/Agenda/RAG/LLM、Redis 或后续 Phase。没有新增 Workflow、PlanStep、TaskGraph 或 Planner Executor。
