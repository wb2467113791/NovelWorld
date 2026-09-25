# NovelWorld｜自主叙事多 Agent 世界引擎（个人项目）

**技术栈：** Java、Spring Boot、Python、LangGraph、React、MySQL、Chroma、MCP、SSE

- 设计由 NPC 自主推动的持久叙事世界：角色依据各自目标、知识与记忆行动；用户通过 React 页面观察时间线、推进 Tick 和投放事件，支持编辑开局及多世界独立存档。
- 以 Spring Boot 作为网页入口和权威世界服务；Python LangGraph Agent 通过 MCP 请求 Java 世界工具，Java 规则服务校验并结算行动、记录事件，将世界快照持久化到 MySQL，避免仅凭模型文本修改状态。
- 实现基于 Chroma 的角色视角 RAG：使用独立文本向量模型索引历史记忆与可见设定，按记忆归属和设定可见范围检索，再将少量结果加入 NPC Prompt，避免提供完整世界信息。
- 实现可跨 Tick 推进的调查 Skill：根据角色已知线索、本人调查事实及已提交事件规划移动、调查与询问步骤；仅在对应工具行动成功后续排角色，防止重复调查。
- 实现事件驱动调度，按事件发生时的知情者唤醒 NPC；Director 在规则判定剧情停滞时提议环境线索，由 Java 校验后写入世界；通过 SSE 向页面推送世界状态与时间线。
