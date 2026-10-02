# NovelWorld V4 Phase 7：Social Dynamics + Skill 重构

从已审查的 `v4-phase6-belief` 提交 `7df412c94f34a040e41c88b9fe9fa2c9a5fca388` 创建 `v4-phase7-social-skill`。保留作者已有 AGENTS.md 改动，不修改 main，不开始 Phase 8。

## 社交规则与唯一权威

relationships 仍是 Java snapshot 中的单向整数倾向，范围 -100 至 100。Python 只读取业务镜像，认知保存接口不能覆盖它。没有新增表、关系缓存或 Social Agent。

成功 give：接收者对赠予者 +2。成功 attack：受害者对攻击者 -15。普通 talk 和其他行为不自动变化，目击者不变化。Belief 与关系独立：不判断谎言，不惩罚传闻，不按关系提高 confidence。

`WorldRules/WorldObjects` 校验并执行真实行动 → 构造原 Event → `WorldSocial.apply` 确定性结算关系 → 原 Event 入列 → 原 MCP `WorldStore.update` 保存整个快照。关系变化和物品交付/伤害在同一次 revision 更新中保存，不由 Python 请求第二个动作，不产生第二个 Event。校验失败不会调用 Social 或提交快照；Social 只处理 give/attack，输入来自 Java 已验证的 Event。

限幅使用 `max(-100, min(100, before + requested))`。原 Event payload 增加：

```json
{"relationship_changes": [{"owner": "苏晚", "target": "林默", "delta": 2, "before": 10, "after": 12}]}
```

delta 是实际限幅后的变化；例如 99 接收物品后变为 100，delta=1；-95 遭攻击后变为 -100，delta=-5。已到边界仍记录 delta=0，便于追踪这次互动的结算。描述与 Memory 继续记真实行为，不额外创建“关系 +2”的叙事记忆。

删除 NPC `update_relationship` schema、Python actor 路由、Java 工具分支及体力费用。Java 内部 Social helper 是唯一新增关系写入点，不作为模型 Tool 暴露。历史 relationship Event 与旧快照关系字段继续可读，无需迁移事件。

## Player 一致性

Player/NPC 共用同一 evaluator，可以互相赠予、攻击并受相同规则影响。Player 没有 Social Agent、认知或 Skill。

Play API 新增受限 `attack`，只接受 target；程序注入当前 Player 身份和 action=attack，再通过既有 MCP 请求 Java。Java Player whitelist 仅额外允许 world_action 的 attack，仍拒绝其他 world_action 与所有直接关系修改。没有自由 action 数值、角色伪装或修改关系的按钮。没有新增战斗 UI，现有 Play 控件与 Observe debug 继续保留。

## Skill 新职责

删除 `InvestigationStep`、`current_step` 及 investigation/concealment 两个 workflow.py；无需替代 Advisor 模型。新链路是 Role + 当前 Goal → Router → 稳定 SKILL.md → Prompt → LLM 选择具体行动。

Router 根据调查/保护类目标选择指导，角色身份补充捕快线索、老板/守卫保管等语义；无关目标不因职业强行加载。显式传入目标优先，否则读 active_goal，尚未初始化时只读 goals 首项作为兼容回退，不修改 Runtime。它不扫描 WorldState、对象、事件或记忆，不计算工具参数，不保存进度。

Markdown 包含 Purpose、Knowledge、Heuristics、Evidence rules、Useful actions、Examples、Common mistakes。调查强调 verified semantic 与 reported belief 不同、重要说法需要独立证据；保护指导强调可见/可接近/可携带与合法保管。能力说明可包含 inspect/talk/move_character/take/put 等名称，没有具体对象 ID、交谈者或目的地。

Skill 不是 Planner：没有执行序列、步骤、完成游标或状态，也不创建 Agenda。动态 Perception、Objects、Conversation、Belief、Semantic、Goal 由原 Prompt 其他区提供。

Prompt 改为“角色技能知识”，说明 Skill 是专业经验，不是必须执行的计划；关系是系统中的简化社交倾向，不是精确心理真理。工具失败后的 Graph 提示继续重新决策和禁止重复失败调用，使用稳定专业指导，不再宣称有可执行 Skill 步骤。

## 保持的边界与验证

Event Reaction → Conversation → Agenda → bootstrap → Idle 优先级不变。旧 Skill pending 的 Agenda 迁移保留；wait、异常、提交后不重放、每 Tick 一个成功行动规则不变。Java 仍持有所有业务权威；原 snapshot/MySQL 保存恢复与多世界隔离、角色 perceived_by、Memory/RAG、Chroma、Observe/Play SSE 不变。

不新增测试文件。把旧精确 next-step 测试改为两个综合指导测试，并适配其他旧消费者；在既有 Java PlayerActorTest 增加一个综合用例，扩充现有 Rules 断言。覆盖 NPC/Player give/attack、失败拒绝、talk 不漂移、上下限、同 revision 单 Event、payload、重连恢复、多世界、认知保存不能覆盖关系，以及 Skill 纯只读、无参数、稳定指导、目标选择和调度独立。全部回归使用 mocked/deterministic 行为与 H2，不调用真实 LLM 或生产 MySQL。

实际验证：`.venv/Scripts/python.exe -m unittest discover -s tests -q` 全部 162 项通过；已有本地 Maven 仓库离线执行全部 Java 测试，86 项通过；web 的 `npm run build` 通过；`git diff --check` 通过。没有安装或更新依赖。测试数量减少来自删除旧精确步骤约束，不影响原调度、知识边界、Conversation、Belief、对象和持久化回归。

## 已知限制与后续范围

关系是简化整数，give 也可表示借用，首版统一 +2，没有防刷、意图识别或赠礼价值模型。只支持 give/attack 两条规则，没有复杂情绪、信任、欺骗检测、派系、声望或多维关系。

行动提交原子性限定在 Java 原 action snapshot；行动、时钟和 Agent 保存仍是原来的分开调用，不新增跨语言事务或网络 exactly-once 保证。路由使用少量目标关键词，不能理解任意自然语言；指导不会自动验证 Belief。

未实现 Phase 8 最终 Eval、经济、派系、复杂情绪、任务系统、Planner、Workflow engine、Redis 或新大型框架。
