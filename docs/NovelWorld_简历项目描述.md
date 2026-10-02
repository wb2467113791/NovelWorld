> **历史归档：V3 学习资料，非当前 V4 架构说明。** 文内 Skill 续排、藏匿/找回等旧描述仅用于历史学习。当前实现请阅读 [README](../README.md)、[最终验收](NovelWorld_V4_Final_Evaluation.md) 和 [简历文案](Resume_Project_Description.md)。

# NovelWorld｜自主叙事多 Agent 世界引擎（个人项目）

**技术栈：** Java、Spring Boot、Python、LangGraph、React、MySQL、Chroma、MCP、SSE

- 开发面向小说与 RPG 的持久叙事世界，NPC 基于各自目标、知识与记忆自主行动；支持开局编辑、多世界独立存档，以及通过 React 页面观察时间线、推进 Tick 和投放环境事件。
- 设计 Spring Boot 权威世界服务与 Python Agent Runtime 的职责边界：LangGraph 编排模型决策与工具调用，通过 MCP 请求 Java 校验、结算行动并记录事件；世界快照存入 MySQL，基于 revision 版本号条件更新检测写入冲突。
- 实现基于 Chroma 的角色视角 RAG：按世界隔离索引，按记忆归属与设定可见范围过滤检索；对记忆结合相关性、重要性与新近程度排序，并限制注入 Prompt 的条数与字符数。
- 实现调查与隐瞒 Skill 工作流：根据角色可见线索及已提交事件推导阶段，将工具建议注入 Prompt，由模型选择行动、Java 校验执行；仅在对应步骤成功且存在后续步骤时跨 Tick 续排，避免失败行动推进流程。
- 实现基于事件知情者的 NPC 唤醒调度，限制连锁反应深度；Director 在规则触发时提议环境线索，经 Java 校验后写入世界，通过 SSE 向页面推送世界状态与时间线。
