# NovelWorld：简历与面试介绍

## 中文简历版

- 开发小规模持久 AI 角色世界引擎，采用 Event Reaction、Conversation 与 Agenda 调度角色自主行动，支持人类玩家进入同一世界。
- 使用 Python/LangGraph 组织模型与工具循环，经 MCP 请求 Java 校验并结算行动；以 MySQL JSON snapshot 保存权威世界状态，控制每 Tick 最多一个成功行动。
- 实现按角色视角隔离的 Memory/Chroma RAG，区分直接观察知识与有来源的未验证说法，避免模型文本直接改写世界事实。
- 实现通用对象互动、确定性社交结算及 React/SSE 观察与玩家界面；通过 scripted Agent 与真实 Java/H2 的离线长期运行和重启恢复验证结构稳定性。

## English resume version

- Built a small persistent AI character world with event reactions, conversation turns, agenda-driven opportunities, and a human player sharing the same world.
- Used Python/LangGraph for model decisions and MCP requests to authoritative Java rules, with MySQL JSON snapshots and a one-successful-action-per-tick boundary.
- Implemented character-scoped Memory/Chroma retrieval and separated direct observations from sourced, unverified beliefs.
- Added object interaction, deterministic social effects, and React/SSE Observe and Play modes; evaluated structural liveness and restart consistency with scripted agents and real Java/H2 persistence.

## 面试时 1 分钟介绍

NovelWorld 是我做的小型持久 AI 角色世界原型。角色会按目标、自己的记忆和获得的信息行动，人也可以作为玩家进入。最重要的设计是：大模型决定想做什么，Java 决定能不能做以及实际结果。Python 用 LangGraph 组织决策，通过 MCP 请求 Java，Java 校验后才产生事件和更新 MySQL 快照。调度不只靠外部事件，还包括持续会话和 Agenda 自主机会。知识方面，我把真实世界、本人观察和别人说过的话分开，检索也按角色隔离。最后用不调用商业模型的脚本跑长期场景和重启恢复，验证的是结构一致性和活性，不把它包装成剧情质量评分。这是小规模单机原型，没有宣称生产并发或大规模性能。

## 最值得讲的 5 个技术决策

1. Java 权威规则：从 `execute_tool → RemoteWorld → WorldMcpTools → WorldRules/WorldObjects → WorldStore` 讲一次交付。模型不能声明物品或关系变化；交付和 Social delta 同次提交。
2. Event 之外加入 Agenda：从 `WorldTickScheduler._select_opportunity` 讲优先级。提醒安排一次重新思考，不执行 Plan 步骤；Director 关闭后也能继续。
3. Memory、Belief 与 World Truth 分开：从 `remember_event` 讲 talk 与 inspect。说话只产生来源报告，观察进入 Semantic；Chroma 按 world/owner 检索。
4. Skill 不做 Workflow：从 `skills/router.py → SKILL.md → build_action_prompt` 讲专业经验。没有 next-step、参数推荐或调度状态，具体动作仍由模型选择。
5. Conversation 不依靠 reaction depth：从 `accept_talk` 和 Scheduler 的 conversation 分支讲 next_speaker。双人会话独立轮次与上限，Player 轮次等输入，不让普通事件深度截断交流。

## 表述边界

“多 Agent”指多个角色决策上下文，不是训练了多个独立模型。H2 Eval 不是生产 MySQL 压测；离线 scripted 决策不代表真实模型的叙事质量。没有 Redis、经济、派系、多玩家、情绪模型、知识图谱或通用规划执行器。准确验收数字见 [最终验收](NovelWorld_V4_Final_Evaluation.md)。
