# 日常活动与调查退化修复

## 审计结论

这次修复以 `affc7f1bec3eb224331813c0fc559b03da713023` 为基准，保留 Java 权威状态、LangGraph、Agenda、Conversation、Memory 与 Belief 架构。

1. `characters/prompt.py` 将对象称为“所在地点可调查对象”，`agent/perception.py` 又逐个列一次。工具说明也强调从列表选择对象。这是调查 affordance 的重复暗示，容易被理解成待办清单，但不能仅凭代码断言它是唯一原因。
2. 对独处且体力充足的角色，旧工具缺少日常职责的合法表达；inspect 比职责、经营和筹划更容易落到可执行动作。模板已经是日常生活主题，默认目标不会加载 investigation Skill，未发现 Skill 自动执行调查步骤。
3. Director 的生成 Prompt 要求“可调查的环境线索”，Java 更无条件创建“新线索N”对象。这是确定存在的结构性调查偏向，不能只修改 fallback 文案。
4. 首轮真实模型验收发现认知格式冲突：Prompt 同时要求 JSON 和 JSON 后独立的“原因”段，Graph 却严格解析整段 JSON。模型生成的后续意图经常没有保存，下一次 Agenda 仍引用旧意图。
5. `active_goal` 首次按目标顺序选择，之后可由模型切换；`current_intention/current_plan` 已有持久化入口。Agenda 到期只重新调用决策函数，不读取或执行 Plan。无需新增 planner 或重写 Scheduler。

现有简化反思按固定重要度选择近期经历，再重复写入记忆，并不按当前目标判断相关性。这可能放大已有信息的显著性；本次没有把它认定为唯一根因，也未扩展修改反思机制。

## 行动语义

新增 NPC 工具 `perform_activity(character, activity)`。活动目录由 Java 规则定义，支持 `duty`、`upkeep`、`administration`、`practice`、`planning`、`social_presence`，分别表示原地值守、日常整理活动、事务准备、练习、筹划和在场招呼过程。

- 不接收自然语言活动描述、结果、目标角色、物品、目的地或状态字段。未知类型及额外参数被 Java 拒绝，而非仅在 Prompt 中禁止。
- Python 与 Java MCP 均检查当前行动者；Java 再检查 NPC 身份、行动能力、当前位置和类型。Player 的工具白名单保持原规则，本次工具不开放给 Player。
- Java 使用固定描述生成真实 `activity` Event，payload 为活动类型及 `scope=process_only`。只证明这一轮过程发生，不证明账目完成、交易达成、信息获得或他人同意。
- 活动不改变 location、inventory、hp、energy、relationship、object state 或其他角色业务字段。无额外体力结算；一轮时间仍由现有 Tick 统一推进。
- 需要走到别处巡街，应使用 move_character；传话、交付、操作对象仍使用 talk、give、interact 等专用工具。目录扩展须在规则层定义受约束的新过程类型，不接受模型临时发明事实。

`execute_world_tool` 沿用现有快照更新与 revision 检查，把事件持久化。RemoteWorld 刷新 Java 镜像并补写 Event 来源记忆；活动仅成为经历，不进入已验证 SemanticFact 或 reported Belief。同地点见证者可以感知活动；Scheduler 跳过发起者自身，使用现有去重与 reaction depth 上限，没有新增自唤醒路径。Director 的近期事件窗口也能看到活动。

## Prompt、认知与 Director

对象只在 Prompt 的当前状态列一次，标为环境资源；明确 inspect 应由目标、计划、受托查看、异常或变化产生的信息需求驱动。保留连续调查能力，没有 cooldown 或次数限制。增加可前往地点，并鼓励从长期目标、关系、近期事件形成当前意图，再选一步行动。

认知回复的原因放在 JSON 的 `answer` 内；Graph 兼容旧格式中完整 JSON 后的“原因：”段，仍通过原有 cognition 字段白名单，不能写业务状态或调度字段。

Director 使用公共世界设定、全部长期目标和近期事件选择主题适合的干预。默认 `ambient` 只生成可感知的环境事件，不新增对象；显式 `clue` 保留旧物证能力。旧文本回调和未提供 form 的客户端默认 ambient，旧存档中的线索对象仍可调查。fallback 也使用通用日常机会，不绑定青石镇或某个角色。Director 只提议环境内容，Java 检查类别、形式、地点、长度与 Tick 并提交；自由环境文字的合理性仍依赖模型，不应视为角色或物品字段的结算。

## 验证与复现

离线验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
mvn -f world-service/pom.xml test -q
cd web
npm run build
```

跨语言结构检查：

```powershell
.\.venv\Scripts\python.exe -m eval.long_run --ticks 60 --boundaries
```

这是 scripted 的结构验证，包含真实 Java/H2、活动事件同步与 Memory、连续 inspect、Player、会话、对象、Belief、重启和世界切换，不能证明模型行为质量。

真实行为验收：

```powershell
.\.venv\Scripts\python.exe -m eval.behavior_smoke --scenario both --ticks 30
```

该流程会调用现有 `qwen3.8-max` 和 `qwen3.7-text-embedding`，产生费用。使用 production Graph/RAG/WorldSession/Scheduler 和临时 Java/H2，通过本地 bridge 调用正式 MCP handler，未经过 HTTP MCP 传输层，也不访问已有世界或生产数据库。Java bridge 改用原生 argv，避免 Windows Java 17 以 GBK 读 UTF-8 参数文件时损坏 Unicode Maven 路径。

每场默认最多 120 次决策 API 请求，禁用 SDK 自动重试；embedding 请求另计。默认场景使用新建默认世界，Director OFF。调查场景只变更长期目标和公共调查主题，不规定工具、路线或结论。输出 `eval/results/behavior-smoke/{default,investigation}.json` 和世界快照；JSON 包含逐 Tick 的来源、事件、认知、请求数、token 使用量及各 NPC 行动分布。

统计口径：`object_interaction` 合并 take/put/give/use/interact；`other` 包括 rest 等；NPC 有机会却未提交事件计入 wait（包括纯认知回复），世界空闲 Tick 单独保留在 trace，不算 NPC wait。验收应看行动与意图的关系以及是否反复扫描，不应断言固定比例或剧情。

人工检查 trace 时，应逐项看：inspect 的理由是否对应具体信息需求；获取信息后是否转向职责、移动或交往；认知修订是否被保存并用于后续机会；activity 是否成为新的无意义重复；调查主题是否仍能连续核实不同材料。检查范围不要求任何角色必须去某地、找某人或达成某项结果。

## 限制

有限过程目录不能表达全部经营成果、登记完成、交易或能力成长；这些需要未来明确的世界规则。模型仍可能重复活动、过度准备、将粗粒度 Plan 写得像步骤、在信息需求不明确时选择调查，或长时间停留在对话。活动有真实经历但没有业务成果计量，不能把它包装成完整经济或职业系统。单次 30 Tick 只能提供样本证据，不能保证所有自定义世界的行为质量。

## 修改文件范围

- 决策与观察：`characters/prompt.py`、`agent/perception.py`、`agent/graph.py`。
- 行动路由与事件记忆：`tools/world_tools.py`、`tools/remote_world.py`、`world/events.py`、`memory/event_summary.py`。
- Java 权威规则：`WorldRules.java`、`WorldMcpTools.java`。
- Director：`agent/director.py`、`web_api.py`。
- UI：`web/src/WorldSetup.jsx` 将预览中的“可调查对象”改成“环境对象”，`web/src/main.jsx` 增加日常活动事件标签与筛选项。
- 验收：`eval/behavior_smoke.py`、`eval/java_bridge.py`、`eval/long_run.py`、`StructuralEvalBridge.java`。
- 回归：`tests/test_perception.py`、`tests/test_current_runtime.py`、`tests/test_agent_runtime.py`、`tests/test_agenda_scheduler.py`、`WorldMcpToolsTest.java`。
- 文档：本报告。

`agent/state.py`、`agent/runtime.py`、`agent/session.py`、`agent/tick.py`、`skills/router.py`、默认世界模板与既有兼容测试已审查，无需改写。作者原有 `AGENTS.md` 修改保留在工作区，不纳入本次提交。

## 实际验收结果（2026-10-02）

- Python：167 项全部通过。新增 5 项关键回归，覆盖对象语义、活动路由与记忆恢复、Director 形式、认知格式兼容、Scheduler 深度和 Agenda 边界。
- Java：88 项全部通过，0 failure/error/skipped。新增 2 项回归，覆盖活动事件持久化、额外字段与伪造执行者拒绝、Player 边界、业务状态不变以及 ambient 不生成对象；原 clue 测试改为显式 clue。
- React：`npm run build` 成功，30 modules；涉及预览标签与日常活动事件标签/筛选。
- 跨语言离线：60 Tick scripted 结构检查通过，violations 为空；Java 在第 30 Tick 真实重启，快照一致；新增活动 Java → Python 同步 → Memory 与连续 inspect 检查通过。
- diff：工作区与暂存区 `git diff --check` 均通过。

最终默认世界验收是真实 LLM，不是 scripted。Director OFF，30 Tick，53 次决策 API 请求，已返回 usage 的 input/output tokens 分别为 219672/35617；另有正常 RAG embedding 请求。出现 3 次 Java 提交后的总结超时，Scheduler 保留事件并继续，未重放行动；因此不能将 token 统计当成账单的完整费用统计。每场上限设为 90 次，低于入口默认的 120 次。认知修复前的试跑在 11 Tick 后停止，报告记录 18 次请求，可能另有停止时在途请求；它只用于定位格式问题，不混入最终统计。

| 默认世界角色 | inspect | talk | move | activity | object interaction | wait | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 林默 | 2 | 4 | 0 | 4 | 0 | 0 | 0 |
| 苏晚 | 1 | 2 | 0 | 3 | 0 | 0 | 0 |
| 赵无极 | 3 | 4 | 3 | 0 | 0 | 0 | 0 |
| 合计 | 6 | 10 | 3 | 7 | 0 | 0 | 0 |

另有 4 个世界空闲 Tick。赵无极核实公告与登记单后前往县衙，与林默交流登记方式，随后继续移动和交往；林默有值守和事务准备过程；苏晚只查看了一张与座位安排有关的便笺，随后整理与交流，没有扫描登记簿、箱子、钥匙等全部对象。本次样本不支持“所有 NPC 稳定轮流扫描当前位置全部对象”的退化描述，但仍能观察到重复日常活动与较长对话。

明确调查目标世界也实际完成 30 Tick，53 次决策 API 请求，已返回 usage 的 input/output tokens 为 295777/43464；Director OFF。发生 1 次提交后总结超时，事件保留且未重放。

| 调查世界角色 | inspect | talk | move | activity | object interaction | wait | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 林默 | 5 | 4 | 2 | 0 | 0 | 0 | 0 |
| 苏晚 | 4 | 3 | 1 | 0 | 0 | 0 | 0 |
| 赵无极 | 2 | 4 | 1 | 0 | 0 | 1 | 0 |
| 合计 | 11 | 11 | 4 | 0 | 0 | 1 | 0 |

另有 3 个世界空闲 Tick。三人各自在自己的行动机会中最长连续 inspect 均为 2 次；林默与苏晚还移动后继续核实新地点的材料。调查能力并未被次数限制或活动偏好压制。该样本只改变目标和主题，并未强制任何工具或固定结论。

两场结束后原脚本因 Windows Chroma HNSW 文件锁清理失败而以非零状态退出，行为验收记录与世界快照均已完整保存。随后在验收脚本 `finally` 显式关闭 Chroma 持久化客户端，使用本地向量完成了真实 Chroma 写入、查询、关闭与临时目录清理验证；不为这项资源释放修复重复调用付费模型。该退出问题不应误报成行为验收没有跑满 30 Tick，也不应把原脚本退出状态写成成功。
