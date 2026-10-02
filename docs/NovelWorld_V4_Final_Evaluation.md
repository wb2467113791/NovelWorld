# NovelWorld V4 Final Evaluation · V4 Scope Frozen

基于已审查 Phase 7 `934f4951693915e5c83e9dc5b9c4d08989ecaaa8`，在 `v4-phase8-final` 完成结构评估、稳定性修正和演示文档。以下数字来自 2026-10-02 的实际执行，没有调用商业模型或生产 MySQL。

## 验证环境与方法

命令：`python -m eval.long_run --ticks 1000 --boundaries`。同一次 Director=None、玩家零干预的 1000 Tick 运行记录 60/200/1000 检查点，避免重复跑相同场景。三名默认 NPC 为林默、苏晚、赵无极，在独立临时世界中同处客栈；scripted decision 选择真实 talk，体力不足则真实 rest。

生产 `WorldTickScheduler`、`RemoteWorld` 刷新/认知保存、Conversation、Belief、Memory/Reflection 与恢复代码直接参与运行。仅模型决策与 MCP 网络传输被离线替换：Java Eval bridge 调用生产 `WorldMcpTools`、Rules、Objects、Social、Store，持久化到临时文件 H2。桥接不复制任何业务规则、不进入生产构建、不连接真实世界；正式 Runtime 没有 eval_mode 或脚本特判。

需要先运行 `mvn -f world-service/pom.xml test`，桥接从该次 Surefire XML 读取测试 classpath。`--ticks` 默认 200，至少 60；`--boundaries` 启用额外误导信息/对象/Player/恢复场景。结构报告写入 Git 忽略的 `eval/results/latest.json`。没有 key 也能执行；在线人工 Demo 是可选的，需要已有模型配置并可能收费。

## Liveness 与 Fairness

| 检查点 | 林默机会/成功行动 | 苏晚 | 赵无极 | Conversation | Agenda | bootstrap | Event Reaction | Idle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 60 Tick | 24 | 18 | 18 | 55 | 4 | 1 | 0 | 0 |
| 200 Tick | 67 | 60 | 73 | 179 | 20 | 1 | 0 | 0 |
| 1000 Tick | 334 | 328 | 338 | 870 | 129 | 1 | 0 | 0 |

每个机会都提交一个 talk 或 rest，事件数分别为 60、200、1000。200 Tick 的个人分布：林默 61 conversation + 5 agenda + 1 bootstrap；苏晚 52 conversation + 8 agenda；赵无极 66 conversation + 7 agenda。1000 Tick 最大机会间隔每人均为 14，宽松条件为持续可行动角色在 60 Tick 窗口内不完全失去机会。未发现死锁或 Skill 续排依赖。

这个场景刻意保持双人持续交谈，talk 的 listener 由 Conversation 承接，所以普通 Event Reaction 为 0；不能据此宣称跑过所有事件洪泛输入。普通 Event Reaction 的知情者、深度、去重与优先级由现有全部 Python 回归验证。

## Bounded Growth

| 当前运行结构 | 1000 Tick 最大值 |
| --- | ---: |
| Scheduler pending | 3 |
| Agenda / NPC | 1 |
| active_conversations | 1 |
| 活动会话保留消息 | 11（第 12 条触发结束） |
| Belief entries / NPC | 50 |
| ShortTermMemory entries / NPC | 5 |
| 尚未处理的 Reflection 经历 / NPC | 2 |

每轮检查 Agenda、Belief、近期窗口、Reflection cursor 合法范围、pending、物品位置/holder/container、派生 inventory 与关系范围。Reflection cursor 是标量历史序号，可以增大；没有新增 Reflection 队列或历史状态表。

允许增长的历史单独记录：Event=1000；林默/苏晚/赵无极的 episodic archive 分别为 875/861/888。没有把这些数字包装成有界历史存储；MySQL snapshot 与 Python/Java 序列化、刷新和 RAG 同步成本仍随历史增加。

## Conversation 与重复统计

本次长跑开会话：林默↔苏晚 30 次、林默↔赵无极 31 次、苏晚↔赵无极 31 次。91 个已结束会话平均长度 10.04；48 次因消息上限结束，43 次因无 talk（休息）结束；尚有 1 个活动会话。timeout/move/unconscious/explicit_end 在该长跑中为 0，不虚构发生次数。

每人连续相同动作类型与目标的最大次数为 10，来自 talk 同一 partner；消息内容不同，没有禁止合理重复。这个脚本不评价故事自然度。重复 inspect 的 Java 拒绝、会话超过普通 reaction depth、next_speaker、Player 不自动运行 Agent、等待不阻塞别人、移动/失能/显式结束/超时/上限和结束全文清理，均由既有 Conversation、Player 与 Java 测试覆盖。

## 额外真实规则场景

`--boundaries` 实际通过以下检查：

- 玩家说“钥匙在县衙”，钥匙仍在客栈；苏晚有 report，林默没有该报告，Semantic 不自动获得该说法。
- 苏晚实际 inspect 后获得直接观察；report 继续未验证；Prompt 的 verified 与 reported 分区存在。
- 玩家 take/open/put/close/open/take/give，关闭箱子中的钥匙不进入 Play 可见投影，Object ID 保持稳定，位置及派生 inventory 合法。
- 玩家 give 只增加接收者对玩家关系 +2，随后 attack −15；单次 give 只有一个 Event，payload 可追踪 delta。
- 保存时确实有活动 Player↔苏晚会话，next_speaker=苏晚；重启 Java 后完整状态恢复一致。
- 切到第二临时世界后没有前一个世界的 holder/report；切回原世界恢复原钥匙 holder。

## Restart / Persistence

第 500 Tick 调用原 save_agent_state，关闭并重启 Java 进程，重新打开同一个临时 H2 文件，再用原 restore_snapshot/Scheduler.restore 继续到 1000。重启前后完整 Python 世界快照一致，包含 Agenda、活动会话/next_speaker、Belief、Memory、Player、objects、关系、世界时间和 scheduler cursor。Boundary 场景另覆盖实际 inspect Semantic 与玩家交付/攻击后的恢复。

这是正常已保存状态下的进程重启，不是断电、丢失响应或生产 MySQL 故障测试。行动、时钟、认知保存仍分开提交。

## 全部回归与覆盖来源

Python 162 项、Java 86 项全部通过；React build 通过；git diff --check 通过。没有新增单元测试文件或测试用例，只在原 Java Play Web 用例增加可读冲突错误断言。新增 Java bridge 是离线工具入口，没有 JUnit case。

| 要求 | 验证来源 |
| --- | --- |
| 自主/公平/有界增长 | 本次 1000 Tick + 60/200 检查点 |
| 会话生命周期与玩家等待 | 长跑、Boundary、test_conversation/test_player、ConversationPersistenceTest |
| 误导信息与知识隔离 | Boundary、test_perception/test_characters/test_world_objects/test_chroma_embedding、Belief 既有回归 |
| Object / Social 一致性 | Boundary、WorldObjectsTest/WorldRulesTest/PlayerActorTest/ObjectPersistenceTest（包括 use/move、多轮、失败与限幅） |
| 一个 Tick 一个成功行动 | 长跑每轮断言、Player 边界、原 Graph 两 Tool 与 Conversation/Agenda/Event 回归 |
| 恢复/旧快照/多世界 | 实际 Java 重启与 Boundary、test_world_switch/test_agent_runtime、Java persistence 回归 |

Chroma 验证使用 deterministic embedder/client 替身，不请求付费向量服务；H2 使用原 WorldStore JSON 逻辑，不代表生产数据库压测。

## 实际修复与最终审计

首次长跑发现：未获得首次机会的角色只有低优先级 bootstrap，其他人的 Conversation/Agenda 可让其超过 60 Tick 无机会。修正为开局累计等待达到一次 Agenda 冷却后，只给仍有 bootstrap 的可行动 NPC 补首次 Agenda。正常开局顺序不变；到期 Agenda 选中后原逻辑移除重复 bootstrap；空队列旧存档不凭空重新开局。优先级仍为 Event → Conversation → Agenda → bootstrap → Idle，没有新增公平 Scheduler 或业务系统。

另外修正 Play 状态读取静默重试的演示问题，显示服务错误、加载和空状态；Java 将规则/冲突错误整理为可读 detail，不发送堆栈。增加 `NOVELWORLD_DIRECTOR=off` 配置，默认行为不变。

Eval 开发中修正了失败清理临时 Java 进程与 Windows 输出编码问题；它们不属于生产世界 bug。

最终搜索 TODO/FIXME、Redis、update_relationship、conceal_clue/recover_clue、InvestigationStep、workflow.py、source=skill：当前 Runtime 没有旧步骤执行器或关系工具；Skill source 仅存在于旧存档验证/迁移；旧 UI 事件标签用于历史读取；Phase 文档保留历史语义。五份 V3 学习/架构资料明确归档，README 是当前入口。Redis 仅在“未实现/冻结”说明中出现。

## 修改文件清单

- Runtime：agent/tick.py、web_api.py。
- Eval：eval/__init__.py、eval/java_bridge.py、eval/long_run.py、StructuralEvalBridge.java、.gitignore。
- Web：web/src/PlayMode.jsx、WorldWebController.java、既有 PlayerActorTest.java。
- 文档：README.md、本文、NovelWorld_V4_Demo.md、Resume_Project_Description.md；五份 NovelWorld_项目整体说明/跟着代码学项目/面试备战/简历项目描述/自主世界完整验收流程归档标记。
- 作者原有 AGENTS.md 未提交改动保留，不包含在本阶段提交中。

## Known Limitations / Frozen Scope

仅证明指定 scripted 场景活性，不证明任意持续外部事件/模型决策下无饥饿；严格高优先级事件仍可能推迟其他机会。会话仅双人、12 条上限、8 Tick 超时；同地点感知、固定 Agenda 冷却、简单目标关键词 Skill、固定 report confidence 与两条 Social 规则保持简化。

Event/episodic 历史继续增长，未做持久快照分段或压测。跨语言 exactly-once、网络幂等、断电恢复、付费模型剧情质量和线上 MySQL/浏览器完整人工 Demo 均未在本次离线验收中证明。

**V4 Scope Frozen**：不自动开展 Phase 9，不新增经济、派系、制作、复杂情绪、多玩家、通用物理、天气、Quest、知识图谱、Planner、Workflow Engine 或 Redis。未来工作只作为讨论方向。
