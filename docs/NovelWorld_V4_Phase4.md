# NovelWorld V4 Phase 4：World Object Model 与基础行动

本阶段基于 `v4-phase3` 的 `457cd0d05bfbf505404eb1c23263e8f27db3dbd9`，在独立 `v4-phase4` 分支实现。没有修改 main，没有开始 Player Actor 或其他后续阶段。

## 实际调用链与权威边界

角色视角 Prompt / Perception → Python LangGraph 决策 → `execute_pending_tools`（每 Tick 最多一个成功行动）→ `tools/world_tools.py` 校验当前 actor → `RemoteWorld.execute` → MCP `execute_world_tool` → Java `WorldMcpTools` 校验 actingCharacter → `WorldRules` → `WorldObjects` 校验并结算 → `WorldStore.update` 写入原 `world_saves` JSON snapshot → Python 读取 Java snapshot、恢复只读业务镜像、按 perceived_by 补 Memory。

模型只提出意图、认知修订和工具请求。Python 没有 take/put/give/use/interact 的本地物理结算分支。`save_agent_state` 继续仅保存原有 Memory、runtime_state、Scheduler 和真实 talk 支持的 Conversation；传入 objects、items、旧线索字典均不能覆盖 Java 业务状态。首次本地种子/旧存档可以迁移并导入 Java，导入后的校验、保存和行动由 Java 负责。

## 最小对象结构与唯一来源

权威来源是 Java 当前世界 snapshot 的 `objects: {id: object}`；Python 的 objects 是该世界的镜像。没有跨世界 object registry 或新数据库表。

| 字段 | 含义 |
| --- | --- |
| id | 稳定、世界内唯一的引用；更名或移动不改 ID |
| name / type | 展示名称和简单类别，名称可重复，不能当主键 |
| description | inspect 才返回的观察内容，不自动进入普通 Prompt |
| location | 地面地点，仅允许合法世界地点 |
| holder | 当前物理持有者；与 owner 分离 |
| container | 一层固定容器 ID，地点由容器推导 |
| owner | 归属角色；拿取或交付不自动更改归属，可表达借用 |
| portable / visible | 是否可携带 / 是否可见；还需位置和容器可达性校验 |
| state | normal/open/closed/locked/lit/extinguished/damaged/consumed |
| properties | 白名单 container、heal，以及旧兼容标记 legacy_concealable、trace_for、hidden_at_index |
| affordances | 白名单 open/close/light/extinguish/consume；不是脚本 |

正常对象必须在 location、holder、container 三者中恰好指定一个。consumed 对象没有物理位置且 invisible，保留稳定 ID 防止重放使用。owner 不是位置字段。容器固定、不可携带，不支持嵌套、容量和重量。对象字段、引用、property 类型和 affordance 在 Java 保存/恢复时校验；Python 恢复时也校验，解析成功前不替换当前世界。

## 迁移与兼容视图

缺少 objects 的旧快照：场景 `inspectable_objects` 转为对象，旧 `items` 转为 holder/owner 为该角色的对象；旧 concealable 转为兼容属性；concealed 的原件保持原描述但 visible=false，痕迹对象引用原件。默认后门/柴房门锁映射为固定 Door，木箱为固定 Chest；登记簿和钥匙可携带。旧 inventory 中含“药”的名称只在一次迁移时映射为 consume/heal=20，运行时 use 不按名称推断行为。

迁移 ID 为 `obj-` 加 SHA-256 前 24 个十六进制字符，输入是带分隔的 scene/location/name 或 inventory/actor/name。相同旧存档在 Python、Java 得到同一 ID；同名不同地点/持有者得到不同 ID。ID 只需世界内唯一，相同模板的两个世界允许使用相同 ID。显式 objects 可自定义稳定 ID，包括同名对象；ID key 必须与字段一致。新增干预线索不能覆盖已有同 ID 的已移动对象。

有 objects 后，旧 `inspectable_objects / concealable_objects / concealed_objects` 只由 objects 单向重建。`Character.items` 保留旧展示格式，但 Prompt、snapshot 和 Java 保存读取 holder 派生 inventory；恢复同步展示字段。旧字典或 items 的写入不会反向修改 objects。模板仍支持原有外层格式，也可提供显式 objects，此时 objects 完全覆盖旧物件输入，不能把两套状态合并为权威来源。

## 基础行动

| Tool | Java 前置条件与结果 |
| --- | --- |
| inspect | 对象存在、本人可行动、可见且同地点/可接近；返回真实 description/state，生成仅本人可见 inspect；不改变对象。省略对象仍可调查地点 |
| take | 可见、同地点、portable、没有其他 holder、容器已打开；清空地面/容器位置并设置 holder |
| put | 本人持有；二选一：当前地点，或同地点可见且已打开的固定容器；清空 holder |
| give | 本人持有，双方存在、可行动、同地点；只转移 holder，owner 保留 |
| interact | 对象可接近且声明 affordance；closed→open、open→closed。locked 不能直接 open |
| use | 对象可接近且声明 affordance；extinguished→lit、lit→extinguished，或持有药物且未满生命时 consume，按 heal 恢复并消耗对象 |

每个成功动作扣除 Java 校验的体力、生成一个 Event。未知 action、自由文本、未声明能力、错误状态、无法接近的对象均拒绝，不写数据库、不生成成功事件。Key 当前只是可携带对象，尚未实现 lock/unlock；use 只实现已明确支持的少数用途。

`move_character / talk / rest_character / attack / flee / follow` 保留。旧 `give_item` 按名称解析唯一对象后调用相同 give 规则；重名时要求 ID。旧 `world_action(use_item)` 映射 consume，`world_action(interact)` 必须提供明确 `interaction=open/close`，原来不指明效果的万能互动不再成立。模型 world_action enum 仅保留 attack/flee/follow，新对象行为独立声明。

`conceal_clue / recover_clue` 是 deprecated 单行动兼容入口，仅操作 objects 的 visible 与痕迹对象，维持既有“调查当前痕迹后找回原件”的规则，不组合多次 primitives，避免绕过一 Tick 一个成功行动。原件内容不因看见痕迹而泄漏；找回仍不等于调查原件。两个入口从新 NPC schema 移除，旧调用仍可执行。现有 Skill 的可见对象查询改用 Object ID，保护线索建议采用 take，取消自动 recover 推荐；不新增对象 Workflow，保留原兼容建议机制，Skill 不替 Agent 执行计划。

## Event、知识和调度

object action payload 携带 object_id/object_name，use/interact 另携带 action/state_before/state_after；put 携带 container_id。Java 生成事件 ID、描述、地点和 perceived_by。inspect 仅本人，give 仅双方，take/put/use/interact 按原本地点目击者规则；与其他地点隔离。Event → Memory / RAG 保持原路径，inspect semantic fact 增加 object_id，旧按名称存储的 fact 仍能加载并单向迁移。

普通 Perception/Prompt 仅显示当前可见可接近对象的 ID、name、必要 state、portable 和 affordances，以及本人派生 inventory。隐藏对象、关闭/不可见容器内容、远处对象和他人持有对象不出现；owner、内部 properties 和未 inspect 的 description 不暴露。已获得的 Memory 不因物件移动而自动遗忘，尚未引入 Belief 系统。

不修改 Phase 1–3 调度和模型写入边界：Event Reaction → Active Conversation → Due Agenda → bootstrap/Skill compatibility → Idle；模型仍只能修改 active_goal/current_intention/current_plan。Agenda、busy_until 和 Conversation 生命周期仍由程序维护。

## 保存恢复与验证

objects 随原 MySQL JSON snapshot 保存，WorldStore.load 兼容迁移；下一次原有保存写入迁移结果，未新增表。Python local snapshot/restore、Java refresh 和 world switch 都按当前 world_id 读取对象，refresh 不把 Python objects 或 items 合并回 Java。

验证命令：`.venv/Scripts/python.exe -m unittest discover -s tests -q`；Java 使用已有本地 Maven 仓库离线执行 `mvn -o -Dmaven.repo.local=<repo>/.m2 -f world-service/pom.xml test`；`git diff --check`。

Python 132 项、Java 64 项全部通过。新增 Python 13 项，Java 39 项覆盖迁移/稳定 ID、名称歧义、合法/非法 inspect/take/put/give/use/interact、固定容器与可见性、失败不改状态、单 Tick 单行动、模型文本不产生物理效果、Java refresh/save 边界、持久化/多世界、旧 wrapper、派生 inventory 和全部既有 Scheduler/Conversation/知识边界回归。数据库测试用 H2 运行同一 WorldStore JSON 保存代码，没有连接生产 MySQL，也没有调用真实 LLM。

## 修改文件

- Python 业务镜像：world/objects.py（新增）、world/persistence.py、world/state.py、world/events.py。
- Agent 视角与知识：agent/perception.py、characters/model.py、characters/prompt.py、memory/semantic.py、memory/event_summary.py、tools/world_tools.py。
- 原 Skill 兼容：skills/investigation/workflow.py、skills/investigation/SKILL.md、skills/concealment/workflow.py、skills/concealment/SKILL.md。
- Java：WorldObjects.java（新增）、WorldRules.java、WorldMcpTools.java、WorldStore.java、WorldTemplateService.java、default-world-template.json。
- Python 测试：tests/test_world_objects.py（新增）、tests/test_agent_runtime.py、tests/test_current_runtime.py、tests/test_skill_routing.py。
- Java 测试：WorldObjectsTest.java、ObjectPersistenceTest.java（新增）、WorldRulesTest.java。
- 本文：docs/NovelWorld_V4_Phase4.md。

## 限制与未实现

仅一层固定容器，无锁钥匙关系、容量/重量/嵌套 inventory、耐久/物理、通用脚本或 ECS；兼容 legacy 的痕迹处理仍存在但不进入新模型工具集。普通可见性简化为同地点，未模拟视线或偷窃规则；give 保留 owner，不引入归属转移法律体系。

没有实现 Player Actor、玩家 UI、Belief System、经济/商店/货币、制作、复杂战斗、Redis、Skill 全面重构或新 Planner/Workflow。React + SSE Observatory、MCP、Chroma 可重建索引和现有 Java 权威架构保留。
