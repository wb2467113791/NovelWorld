# 架构与面试调用链

可口述：我做了一个小规模 AI 社会沙盒。角色用 LangGraph 把现场观察、自己的记忆和计划组合起来选择行动，通过 MCP 请求 Java 执行。Java 校验地点、活动和对话轮次并保存事实。浏览器从 Spring Boot 接收 SSE 更新，在上帝视角查看每个人的行动与动机，也能作为玩家参与。

## 一次真实轮次

1. React 请求 `/api/control/next`，Spring Boot 的 `WorldWebController.next` 调用本机 Python 控制入口。
2. `web_api.WorldController.start` 启动单个后台工作线程。状态查询不等慢模型锁，所以 SSE 可以显示“正在考虑下一步”。
3. `agent.tick.WorldSession.next_tick` 请求 MCP `advance_world`。Java `WorldRules.advance` 推进5分钟，完成所有到期活动，处理过期邀请与会话。
4. `opportunities` 选择至多两名有机会的 NPC。持续活动可同时存在，模型请求顺序执行。久未行动者优先，之后考虑邀请、会话轮次与日程。
5. LangGraph 的 observe 读取 Java 快照。`memory.stream.observe` 仅收集 `perceived_by` 含本人的经历；`characters.prompt.build_prompt` 不会把全局快照直接发给模型。
6. recall 在 Chroma 中先按 owner 过滤再检索；近期8条直接进上下文。长期候选综合语义相关性、新近程度和重要性。世界设定按 audience 过滤。
7. decide 用现有模型返回一个行动、短动机、粗粒度计划及可选反思。SKILL 来自身份与情境相关的 Markdown，不是固定工具流程。
8. act 通过 `RemoteWorld.commit` 调用 `WorldMcpTools.commitTurn`。Java 白名单检查认知字段及记忆来源，`WorldRules.apply` 校验并执行动作。
9. Java 为实际动作生成事件，自动关联故事记录，并原子保存业务状态、本人认知和记忆。数据库 revision 乐观锁防止覆盖其他请求。
10. SSE 推送已保存的世界视图。React `Story` 按真实事件顺序展示对话与活动，把短动机放在对应事件旁。

## 角色活动与对话

活动开始时设置 started/until，时间推进到 until 才产生完成事件。角色不必再次请求模型才能结束活动。接受邀请可以中断活动，但不会虚构被中断工作的成果。

邀请和会话都由 Java 保存。邀请人不能替对方接受；只有会话的 next_speaker 可以 say。玩家停在自己的轮次等待人类输入，NPC不会替玩家发言。普通事件没有“连锁深度”来切断对话；会话使用自己的消息数量和世界时间限制。

## 信息与关系

观察、听说和反思使用同一个有类型与事件来源的记忆流，减少重复状态。角色知道“有人说了什么”，不代表知道消息是真的。对象描述只有查看后才进入本人记忆。

关系是初始描述和后续主观印象，没有机械的好感加减分。Python要求关系更新有当事人实际交流记录；它仍是模型的主观判断，不是客观心理真理。

反思在累积5条新经历后随同一次决策生成，必须引用本人可见的真实事件。没有单独的反思模型请求。日程是个人意图，不会自动创建与别人共同确认的约定。

## 持久化、检索与缓存

MySQL 保存 version=3 世界 JSON、业务事件、认知、记忆、活动及活跃会话。此规模采用整份JSON快照，易调试但随历史增长成本上升。

Chroma是可重建索引，不能修改世界状态。Redis只缓存向量，键包含模型、维度和文本SHA-256；缓存不包含角色决策，不会让两名角色复用同一行动。缓存掉线时退化，不把Redis称为权威数据库或分布式任务调度。

Python只存当前世界ID；重启从Java恢复。轮次请求ID保留最近120条，用于网络返回丢失后的确认。时间推进携带 expectedTick。以上只提供本原型的短期防重，不宣称跨服务无限期 exactly-once、集群一致性或生产并发经验。

## 简历准确写法

“基于 Spring Boot、Python/LangGraph 构建小规模持久 AI 社会沙盒；实现角色视角记忆检索、计划与反思、持续活动及自愿会话，通过 MCP 调用 Java 规则执行行动，并用 React/SSE 展示群像事件与角色动机。”

“使用 MySQL 保存权威世界与角色认知，Chroma按角色可见范围检索记忆，Redis缓存文本向量；基于JSON快照和revision乐观锁控制状态覆盖。”

不要写成独立训练的大模型、海量NPC、完整经济模拟、多人游戏或生产级分布式系统。
