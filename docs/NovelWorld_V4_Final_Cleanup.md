# V4 Final Cleanup：Canonical Format + Legacy Boundary

基于 `v4-phase8-final` 的 `ee41947bf2831f138c481b6e0054f2d88dc0a366`，在 `v4-final-cleanup` 清理格式和旧执行入口。没有新增功能、数据库表或 Phase 9；作者原有 AGENTS.md 改动保留且不纳入提交。Phase 4/5A/7 文档继续记录当时实现，不重写历史。

## 审计及最终边界

| Legacy / Duplicate | 清理前作用 | 当前 V4 Runtime 是否需要 | 旧存档是否需要 | 处理 |
|---|---|---:|---:|---|
| LegacyWorldTools / 旧动作别名 | 外部旧请求转换，无正式调用者 | 否 | 否 | REMOVE |
| object_name / item 定位 fallback | 按名称寻找对象 | 否 | 否 | REMOVE |
| 旧三字典输入 | 无 objects 的旧存档迁移 | 否 | 是 | MIGRATION_ONLY |
| legacy_views / Java 三字典投影 | 重新序列化旧格式 | 否 | 否 | REMOVE |
| legacy_concealable / trace_for | 退役能力标记及痕迹引用 | 否 | 仅加载时清除 | MIGRATION_ONLY |
| hidden_at_index | 旧隐藏状态后的调查去重边界 | 恢复旧世界时需要 | 是 | KEEP_CURRENT |
| Character.items | holder 派生展示、旧 inventory 输入 | 展示需要 | 是 | KEEP_CURRENT |
| 旧 Event 类型 | 历史摘要、标签、过滤 | 历史读取需要 | 是 | HISTORY_ONLY |
| Python 重复默认 seed | 第二份开局数据 | 否 | 否 | REMOVE |
| 浏览器旧草稿 | 旧模板输入格式 | 否 | 不属于世界存档 | DOCUMENT_ONLY |
| known_facts、两个 Actor、双重调查检查、正式调度 | 当前认知、身份、规则、行动机会 | 是 | 是 | KEEP_CURRENT |
| 历史 Phase / 已归档 V3 资料 | 记录旧实现 | 否 | 历史说明需要 | HISTORY_ONLY |

## 当前 template 与 snapshot

默认开局单一来源：`world-service/src/main/resources/default-world-template.json`。Java 从 classpath 读取；Python presets/state 从仓库同一文件读取 seed。对象 ID 沿用 `obj-` + SHA-256 前 24 位：`scene\0location\0name` 或 `inventory\0holder\0name`，清理不改变已有默认 ID。

新 template 包含 time、locations、inspectables、objects、characters、lore，以及可选 player 配置。objects 按 ID 保存完整 id/name/type/description/location/container/holder/owner/portable/visible/state/properties/affordances。角色输入不再接受 items；初始持有物品在 objects 中声明 holder/owner。Java 先校验人物与引用，构建世界，再复用 WorldObjects.validate 校验对象，projectInventory 派生 items；不复制第二套对象规则。

WorldSetup 预览从 objects 推导角色物品及场景对象。旧三字典或 characters.items 模板输入明确拒绝。浏览器草稿使用新的 localStorage V2 key，旧草稿不再载入，应重新创建；未删除旧浏览器内容，也未删除任何持久世界。

canonical snapshot：version=2、world_id、time、locations、inspectables、objects、characters、lore、events、active_conversations、scheduler；Java 另保留原 revision 乐观锁。新世界会话显式为空，Python 本地 snapshot 同样保存活动会话。items 是 holder 派生的展示字段；objects 是唯一物品权威。

Python snapshot_world/restore 不再调用 legacy_views，该函数删除；current_objects 不再进行惰性旧格式初始化。Java projectInventory 只派生 items，ensure 清除旧三字典，不再生成它们。无第二套业务状态源；Python 的 objects 仍是 Java 业务镜像，save_agent_state 不能覆盖物理状态或提交事件。

## V1 加载与 V2 保存

加载接受 V1/V2；新建和后续保存只写 V2，V2 缺少 objects 会拒绝。V1 没有 objects 才读取 inspectable_objects、concealed_objects 和 Character.items，转换为稳定 ID 对象；concealable_objects 只作为旧字段丢弃，不再产生能力标记。V1 已有 objects 时直接使用它们并移除退役的 legacy_concealable/trace_for，不合并旧字典或 items。

旧隐藏原件保留原描述和 visible=false；旧痕迹保持普通可见、不可携带对象，不需要特殊引用或找回行为。hidden_at_index 保留在原件及痕迹上，供现有 inspect 去重忽略隐藏状态之前的旧观察。新默认世界和当前行动不生成该属性。允许 properties 最终只有 container、heal、hidden_at_index，Python/Java 白名单及类型校验一致。

Java WorldStore.load/insert 接受迁移输入，当前行动拿到的世界已规范为 V2；update 写 canonical V2。迁移结果在下一次正常保存写回原 world_saves JSON，没有双 Runtime 分支、额外表或批量覆盖旧世界。Python restore 在全部解析、对象校验成功后替换当前镜像。已存在的 Memory、Semantic、Belief、Conversation、runtime_state、scheduler、世界隔离和 perceived_by 保留。

## 旧 Tool 与历史 Event

LegacyWorldTools.java 删除，WorldRules 不再 normalize。正式 Java 入口拒绝 give_item、conceal_clue、recover_clue、update_relationship、world_action(use_item/interact)。对象动作使用 object_id；inspect 不带对象仍可调查地点，旧 object_name/item 参数拒绝。没有保留动作 wrapper。

legacy history only：give_item、conceal、recover、relationship、narration、use_item Event 仍可加载和显示，摘要只使用历史 Event 可见字段。narration 仍不进入普通感知、Event Reaction、长期 RAG/Reflection 或 Director 的有效行动历史。当前 take/put/give/use 标签补齐；Observe 描述改为事件、会话、Agenda 提供机会，无机会才 Idle。

known_facts 保留开局认知、Prompt/UI 和 Belief 校验用途。Character/PlayerActor 不改继承。Python unverified_inspection_claim 防 final text 虚构，Java REVIEW_CLAIM/OBJECT_ALIASES 防 committed talk 虚构，二者保留。Event → Conversation → Agenda → bootstrap → Idle、wait、异常重试及已提交行动不重放均不变。

## 最终关键词审计

| 关键词 | 剩余位置与原因 |
|---|---|
| LegacyWorldTools | 仅历史文档与本文；类及运行引用删除 |
| give_item / use_item | Event/Memory/UI 历史读取、退役拒绝测试与文档；没有动作执行入口 |
| conceal_clue / recover_clue / update_relationship | 仅拒绝测试、范围说明及历史文档 |
| inspectable_objects / concealed_objects | 旧快照读取、字段清除、模板拒绝、迁移/防伪造测试及文档 |
| concealable_objects | 字段清除、模板拒绝、旧夹具和文档；不生成属性或调度 |
| legacy_concealable / trace_for | 仅 V1 加载时清除、拒绝/迁移测试及历史说明；不在 schema 中 |
| hidden_at_index | 旧迁移生成、合法属性校验、inspect 去重、迁移测试；保留必要 Runtime 消费者 |
| narration | 旧历史显示/摘要/安全过滤、拒绝上传测试与文档；没有生产或上传路径 |
| InvestigationStep / workflow.py / completed_step | 仅历史文档，无当前实现 |
| skill_views | 旧保存字段忽略/清除、迁移/无字段断言及历史文档；无当前读写消费 |
| source="skill"（或相同 source 值） | 旧 scheduler 队列转 Agenda 的单次迁移、夹具与文档；不新增 skill 机会 |
| TODO / FIXME | 本次仓库受版本控制的代码未发现未处理项；历史审计文字保留关键词 |

## 验证与 intentional debt

复用已有用例，无新增测试文件或测试数量。覆盖 canonical 新模板/快照、holder inventory、V1 两种格式、隐藏物件、稳定 ID、历史去重、旧 Tool 拒绝和旧 Event 可读；全部原 Conversation/Belief/Social/Player/知识隔离/多世界回归保留。

2026-10-02 实际验证：Python 全部 162 项、Java 全部 86 项、React build、git diff --check 通过。Python/Java 的旧 snapshot migration 包含在全套回归中，不调用真实 LLM 或生产数据库。业务代码净删除 117 行；默认 JSON 因展开 8 个 canonical 对象增加数据行，没有新增抽象体系。

`python -m eval.long_run --ticks 1000 --boundaries` 再次通过，未修改 Eval 期望或代码。Director OFF、玩家零干预，violation=[]；成功行动林默/苏晚/赵无极为 334/328/338，最大机会间隔均 14。pending 最大 3、Agenda/NPC 最大 1、活动会话最大 1、会话消息最大 11、Belief 最大 50、近期记忆最大 5。第 500 Tick 真正重启 Java，快照完全一致；misinformation、private_report、verified_prompt_partition、closed_container、object_invariants、player_social、带活动玩家会话的 restart、world_switch 全部 passed。60/200/1000 检查点与 Phase 8 一致，未改变调度语义。

剩余边界：Event/episodic 历史允许增长；MySQL 整份 JSON 快照与索引同步成本随之增长。Character.items 展示字段及旧 Semantic name-key、旧 Skill 队列迁移有明确消费者，保留。默认世界数据已统一，但 Python seed 仍依赖仓库资源路径，不是独立安装包。H2/scripted Eval 不代表生产 MySQL 压测或付费模型剧情质量；行动、时钟、Agent save 仍分开调用，无跨语言 exactly-once 或网络幂等保证。不引入 BaseActor、Planner、Redis 或任何后续 Phase。
