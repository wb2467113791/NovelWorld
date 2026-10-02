# NovelWorld V4 Phase 5A：Legacy Runtime Cleanup

基于审查通过的 `v4-phase4` / `938f322589f514848dc49db3d977012fc9127d5b`，在 `v4-phase5-cleanup` 完成小范围运行路径清理。未修改 main，未实现 Phase 5B、Player Actor 或 Play Mode。

## Legacy Audit

下表为修改前审计及最终处理。搜索覆盖 agent、skills、tools、world、memory、characters、Web/API、Java 代码和测试；`.items()` 字典遍历与 Character.items 物品字段分别核对，未把字典 API 当作物品状态误删。

| Legacy / Compatibility | 当前真实用途（清理前） | 正常 Runtime 是否还依赖 | 旧存档是否依赖 | 计划 |
| --- | --- | --- | --- | --- |
| Skill Scheduler continuation | completed_step → current_step → source=skill 入队 | 是，非 Agenda/Conversation 来源仍续排 | 旧 pending 可保存 skill | REMOVE |
| 旧 skill pending | 保存的旧待行动机会 | 仅恢复输入 | 是 | KEEP_MIGRATION_ONLY |
| completed_step | 判断 Skill 步骤是否成功以续排 | 是，无其他运行用途 | 否 | REMOVE |
| current_step / InvestigationStep | 为 Prompt 生成只读建议 | 是，不需执行器 | 否 | KEEP_REQUIRED |
| skill_view / skill_views | Scheduler 保存阶段，Java API / React 展示 | 展示有依赖，决策无依赖 | 无恢复意义 | REMOVE |
| conceal_clue / recover_clue | Phase 4 剧情特化动作兼容入口 | 正式 schema 不提供，仅旧测试调用 | 存档数据迁移不需要动作入口 | REMOVE |
| Character.items | 旧 inventory 输入、UI 展示字符串列表 | holder 判断不依赖它 | 是 | KEEP_DERIVED_VIEW |
| inspectable/concealable/concealed 字典 | 迁移输入和兼容投影，Java 注入仍用于查重 | 注入存在残余读取 | 是 | KEEP_DERIVED_VIEW |
| legacy_concealable Skill 条件 | 决定哪些可见物件值得保护 | concealment 建议依赖旧标记 | 标记是历史迁移数据 | REMOVE |
| give_item | 旧名字交付接口 | schema 仍暴露冗余别名 | 历史事件仍需显示 | DEPRECATE_WRAPPER |
| world_action(use_item/interact) | 外部旧参数映射 | schema 不暴露，但旧分支混在 WorldRules | 存档加载无需入口 | DEPRECATE_WRAPPER |
| narration 上传/刷新合并 | Python 叙述事件可进入 Java snapshot | 已无正常生产端 | 历史事件已在旧快照中 | REMOVE |
| narration 历史过滤、描述、UI 标签 | 读取旧存档，避免叙述成为反应/长期证据 | 读取历史时需要 | 是 | KEEP_MIGRATION_ONLY |
| Bootstrap | 每 NPC 一次开局机会 | 新世界需要 | 保存过的待机会需继续 | KEEP_REQUIRED |
| Event / Conversation / Agenda | V4 正式调度和持久化 | 是 | 是 | KEEP_REQUIRED |

## 删除的真实运行路径

- Scheduler 不导入或调用 Skill，不保存 skill_views，不检查 completed_step，不生成 skill pending。删除无其他消费者的 completed_step 与 skill_view。
- 删除 Python 与 Java 的 conceal_clue/recover_clue 行动入口、痕迹生成/找回结算，以及仅用于此路径的 Memory 临时痕迹清除函数。对应旧行为测试改为废弃 Tool 拒绝、正常 Object 行动和迁移测试；保留旧 concealed 快照迁移测试。
- 正式 Python Tool 集删除 give_item，旧 world_action 的 item/object_name 参数不再声明；正式 dispatch 拒绝 use_item/interact action。inspect 正式 schema 使用 object_id，省略对象仍可观察地点。
- 删除 Python 保存 narration 的 events 载荷与同世界刷新时合并本地 narration 的逻辑；Java save_agent_state 拒绝所有非空 events 输入，不再追加事件。旧客户端的空 events 仍接受，Java 已存在的历史事件不清除。验证在记忆/认知写入前完成，拒绝不改变数据库快照。
- Director 不再把“三条 narration”作为停滞信号；旧 narration 从其有效行动历史排除。仍保留真实重复事件、空闲、参与和冲突规则，Director 不承担唯一持续驱动职责。
- 删除 Java API / React 对 scheduler.skill_views 的阶段展示和对应读取，旧 UI 不再展示已失效的 workflow 阶段。Observatory 查询、时间线和 SSE 保留。
- Java 线索注入查重改查 canonical objects，包含关闭容器/隐藏物件，不再读 inspectable/concealed 派生字典做业务判断。

业务代码删除量大于新增业务代码量。仅新增一个小型 Java 外部参数兼容类，未增加 Planner、Workflow、表、框架或抽象接口体系。

## 正式 Scheduler 与 Bootstrap

Event Reaction → Conversation Turn → Due Agenda → Bootstrap → Idle。

有感知者的真实事件仍按原 reaction depth/去重规则处理；Conversation 生命周期、消息验证和独立轮次保留；Agenda 的冷却、busy、等待消费、异常重试和已提交行动不重放保持原规则。一 Tick 仍最多一个成功 world action。

Agenda 在 bootstrap、reaction、conversation 或 agenda 机会结束后，继续为有有效 active_goal 的角色建立未来自主机会。没有 Director、没有 Skill 自动续排时，调查角色仍可在下一 Agenda 机会根据最新知识重新选择 inspect/talk/move 等行动。Skill 不决定机会时间。

新 Java 模板显式保存每个 NPC 一条 source=bootstrap 的 pending；首次本地种子导入也显式生成一次初始 Scheduler 快照。读取已有 Java 世界时以远端 snapshot 为准，不把本地 seed 开局队列合并进去。恢复只使用已保存 pending，缺少 pending 时为空，不能因构造 Scheduler 又重新 bootstrap。

legacy migration only：旧 source=skill pending 经原字段和重复检查后转为该角色的到期 Agenda。已有 pending Agenda 时保留其 ID 并取原时间与当前 Tick 的较早值，避免丢失保存过的机会或新增重复提醒；没有有效目标则不建立 Agenda。迁移后的正常 Scheduler 队列不再有 skill，下一保存也不再写 skill_views。无 source 的旧队列无法可靠区分开局与事件，仍作为 legacy Event Reaction 保留原顺序，以免丢失真实事件反应。

## Skill 与 Prompt

现有 InvestigationStep / current_step 只保留作 Prompt 建议，没有完成状态、执行器或 Scheduler 消费方。它们查询角色自己的 semantic facts、Memory 和当前可见 objects，建议仅使用通用 inspect/take/talk/move；concealment 不再要求 legacy_concealable 标记，只从合法可见、可携带对象中提供保护建议。

保留 Markdown 的知识、约束和能力说明。删除 Skill 文本中已不存在的剧情 Tool 兼容说明与正式 schema 的旧参数说明，characters/prompt.py 原本没有这些废弃入口指令，因此无需重写。cognition、只读 agenda/busy、本人 conversation、Object 可见性和 Java authority 说明保留。

删除 skill_views 后，其曾经在展示时隐式触发的 select_goal 不再存在；角色快照在序列化 runtime_state 前明确执行原 select_goal，使保存与恢复继续使用相同初始目标规则。没有增加 Goal Manager，也不将 Plan 转成步骤。

## 正式 Tool surface 与 Java 边界

正式 NPC Tool：inspect、take、put、give、use、interact、move_character、talk、rest_character、update_relationship、wait、world_action（仅 attack/flee/follow）。wait 不产生事件；内部 get_world/save_agent_state 等 MCP 接口仍不暴露给 NPC。

`LegacyWorldTools.java` 仅转换外部旧调用参数：give_item → give，world_action(use_item) → use/consume，world_action(interact) → interact/明确 interaction。它不修改世界或生成事件。WorldMcpTools 仍先校验原 actingCharacter；之后 WorldRules 规范化参数，WorldObjects 执行相同 actor、对象、位置、可达性、affordance 和体力检查。外部旧交付成功现在产生标准 give Event，旧给物事件仍可读取。

按 name 解析对象的 Java fallback 仍为 deprecated 参数兼容；重名要求 ID。新 Agent 不看到这些外部 wrapper。conceal_clue/recover_clue 已删除，外部旧客户端如还调用需改用当前通用动作，不能从模型文字宣称恢复了隐藏原件。

## Object authority 与必须保留的兼容

Java snapshot.objects 继续是位置、holder、container、visible、state 的唯一权威来源。Python 只有 Java 业务镜像及角色 cognition/Memory 运行状态；MCP 请求 Java 校验结算。保存 Agent 状态不能覆盖 objects、items 或旧线索字典，也不能产生事件。

legacy migration only：objects 缺失时才迁移 inspectable/concealable/concealed、旧 items 和药物名称映射；旧 hidden 原件保持 invisible，痕迹引用保持有效。objects 存在时旧字段完全不反向覆盖。缺少 runtime_state/conversation 的快照仍按既有规则恢复。

KEEP_DERIVED_VIEW：Character.items 和旧物件字典只用于初始迁移或单向兼容展示/序列化。原 WorldSetup 模板仍采用旧外层格式作为创建输入，Java 创建后迁移/校验；未顺便重写模板编辑器。Python 恢复中删除了无效的旧视图重复读取，有 objects 的 snapshot 无需再依赖 inspectable_objects 字段。

旧历史 Event/Memory 中的 give_item、use_item、conceal、recover、narration 描述、标签和旧 semantic name-key 均仍可读取。narration 不是当前动作：不触发 Event Reaction，不出现在普通 Perception，不进入长期 RAG 或 Reflection；UI timeline 仍可显示已有历史。没有新增 narration 生产端或回传 Java 的通道。

## 验证

- 全部 Python：`.venv/Scripts/python.exe -m unittest discover -s tests -q`，140 项通过。
- 全部 Java：使用已有 Maven 仓库离线运行 `mvn -o -Dmaven.repo.local=<repo>/.m2 -f world-service/pom.xml test`，71 项通过。
- React：web 目录 `npm run build` 通过。使用已有依赖，未安装/更新包；第一次构建遇到沙箱目录权限，经获准重试后通过。
- `git diff --check` 通过。

新增 cleanup 测试验证：Skill 不驱动 Scheduler、调查通过 Agenda 跨恢复持续、旧 Skill pending 迁移和世界隔离、Bootstrap 一次性与首次导入、现有 Java 世界不会被 seed bootstrap 覆盖、正式 Tool surface/dispatch、三个旧物件字典与 items 无权威、旧 narration 可读但不可生产/同步、外部别名/actor 校验、canonical closed contents 注入查重。保留旧 inventory/hidden/object 迁移和全部 Conversation、Agenda（1000 Tick 有界增长）、Event、知识隔离、Object primitives、单成功行动与多世界测试。

所有模型/服务测试使用 deterministic/mocked behavior；数据库测试使用 H2 和现有 WorldStore JSON 代码，未调用真实 LLM 或生产 MySQL。

## 保留的 legacy debt 与后续未实现

- 旧缺 source 队列仍以 legacy 反应来源兼容；若旧快照没有 pending、没有 Agenda，本阶段不凭空恢复开局，需真实事件或原 Director/程序安排恢复机会。
- Workflow 文件名与 InvestigationStep 建议结构仍保留，但不控制调度；全面 Skill 内容/路由改写不在本阶段。
- 模板旧输入格式、派生字典、Character.items 展示以及历史事件标签继续兼容；未来可以独立迁移作者模板格式。
- hidden/trace_for/hidden_at_index 等旧对象属性仍需读写旧快照。旧 invisible 原件仍不能被普通 inspect/take 直接访问；本阶段没有新增通用 search/unhide 或剧情恢复能力。
- Java 外部 give_item/use_item/interact 参数 wrapper 未彻底删除，兼容客户端可逐步改用正式 primitives。
- 原 action、时钟、runtime save 的跨调用事务限制未改变。

Phase 5B、Player Actor、Play Mode、玩家 UI、Belief、经济、Redis、新 Planner/Workflow 或游戏系统均未实现。完成后停止。
