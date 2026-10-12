# 原生 Tool Calling 局部升级

后续简化：已移除仅转交结果的 Remember 节点，当前流程为 Observe → Recall → Decide → Act → END。Act 的 `result` 仍返回执行回执，供 Tick 与演示使用；记忆、认知及回执的 Java 原子保存不变。下方五节点描述记录原升级时的实施情况。

## 改造前审计

- `llm_client.py` 从 Responses 的普通文本解析 action/arguments；`characters/prompt.py` 要求文本 JSON。
- `agent/graph.py` 保留 Observe → Recall → Decide → Act → Remember，失败最多改选一次；Remember 从 decisions 尾部取结果。
- `tools/remote_world.py` 只调用 commit_turn，网络异常后从 decisions 查请求。
- `WorldMcpTools.java` 在同一快照中保存行动、认知、记忆与 decisions；防重只覆盖最后 120 条。
- `WorldStore.java` 使用 MySQL 快照与 revision 乐观锁；`schema.sql` 只有 world_saves。
- `WorldTemplateService.java` 初始化 decisions；`WorldWebController.java` 将其提供给 Observe 与 SSE。
- `web/src/main.jsx` 将 Decision 的最后一个 event_id 关联到时间线动机，并展示人物最近动机。
- `agent/tick.py` 的局部 decisions 变量只是返回结果列表；mind 的 last_decision/next_decision 是调度时间，不能删除。
- 仓库没有已有单元/集成测试源文件；需补最小关键行为验收。玩家通过 Runtime 调用 backend.commit，浏览器仍只访问 Spring Boot。

## 分阶段实施

1. Java 九个独立业务 MCP Tool 复用原有规则与原子提交；新增持久请求回执、旧 v3 存档兼容迁移和提交确认工具。
2. Python 发现 MCP Schema，隐藏运行时身份/请求/认知持久字段，补充结构化认知参数，提供给现有模型的原生工具接口；Act 调用选中的独立 MCP Tool。
3. Event 保存请求关联与简短动机，迁移 Remember、前端、存档与文档；保留旧 Web decisions 字段的派生兼容输出。
4. 最小单元、H2 集成、MCP 与端到端演示，分别记录模拟模型和真实模型的证据，不将模拟当作真实模型证明。

## 边界

Tick、角色机会排序、五节点、Conversation、Memory/Mind、Skill、RAG、Redis/Chroma、玩家排队和 SSE 调度保持。每机会最多两次模型选行动、最多两次业务提交、最多一次成功行动；图步数另有限制。传输故障只查询提交状态，不自动改选或重放。成功后结果写入本人亲历记忆，不再请求模型生成第二个世界行动。

旧 v3 存档已有最后 120 条 Decision 可以迁移；更早已被旧代码裁掉的请求 ID 无法恢复，不能声称历史无限期防重。新回执不随时间线裁剪。


## 保存和恢复细节

- 新回执只存请求摘要、committed 状态、行动/角色/时间、短动机与 event_ids。完整 Mind/Memory 仍只在权威快照中保存。
- 相同请求 ID 和内容返回原回执，不再执行 apply；改变内容复用同一 ID 会拒绝。一次机会在 Python 中绑定一个请求 ID，规则拒绝后的唯一修正沿用它；失败不写成功回执。
- Java 明确规则拒绝返回 status=rejected。MCP isError、数据库异常、传输异常和响应解析错误均不能直接触发改选；先查询 get_execution，无法确认就暂停。
- 成功后 Java 把真实结果追加到本人亲历记忆，与本轮认知和回执同事务保存；下一次 Decide 通过本人记忆获知结果。失败修正使用原生 assistant/tool 消息反馈。Remember 返回提交回执，不额外请求模型，也不再执行行动。
- v3 旧存档首次读取会事务迁移并推进一次 revision，不修改时钟、活动或会话。v1/v2 不迁移。旧请求未保存原始完整参数，只能核对角色/行动后返回已提交回执，不能重建其请求摘要。

## 验收记录（2026-10-11）

- Java `mvn -q -f world-service/pom.xml test`：3 项通过。真实 Spring 事务/H2 验证九项行动、邀请接受与会话轮次、活动完成、Tick 防重、规则拒绝、超过120次后的回执重放、请求ID冲突、回执插入失败时快照/认知/记忆回滚、旧存档迁移与视角投影。
- Python `.venv/Scripts/python.exe -m unittest discover -s tests -v`：4 项通过。验证SDK原生tool_calls契约、拒绝文本JSON和多个调用、每Tick两名NPC、最多一次修正、网络丢响应只读确认、工具Schema适配与秘密隔离。
- 前端 `npm --prefix web run build`：通过。
- 真实模型隔离演示 `.venv/Scripts/python.exe tests/native_demo.py --live`：使用原有 qwen3.8-flash，仅1次请求，返回 `call_4a0438fd9abe4f2e8dfa8fba` / function / start_activity，经实际MCP与Java规则提交成功；本人Mind/Memory、Chroma owner过滤、SSE状态和玩家排队/可见范围断言通过。没有请求远程embedding，没有改现有世界指针或存档。
- 确定性端到端演示：3 Tick / 6次成功提交，累计分钟485、490、495；依次邀请、接受、两次移动、两次轮流发言。每Tick只有两名不同NPC获得行动机会，Chroma、SSE和玩家队列断言通过；模型返回使用SDK模拟，不作为真实模型证明。
- 实际MCP故障检查 `tests/native_demo.py --fault-only`：在临时H2上约束回执请求 fail-storage 必须插入失败；实际MCP入口的世界事件、认知、记忆、revision和回执均未提交，查询确认 not_committed 后停止，不再次执行行动。
- 实际MCP发现九个业务工具，respond_invitation.accept 为 boolean；内部控制/快照工具未传给模型。

测试使用独立H2数据库与本地确定性向量。没有对现有MySQL/Redis服务进行数据写入验收，没有重新验证长期叙事质量或生产并发能力。正式MySQL存储、Redis缓存和Chroma检索实现保留，只有增加回执表和事务边界；不能把隔离验收描述成生产部署验证。

复现端到端演示：先执行 `mvn -f world-service/pom.xml test dependency:build-classpath '-Dmdep.outputFile=target/test-classpath.txt' '-Dmdep.includeScope=test'`，再以 target/test-classes、target/classes 和 test-classpath.txt 里的依赖组成 Java classpath，启动 `org.novelworld.world.NativeToolsTest`。它只监听本机18080并使用临时H2。演示脚本临时监听18001，退出时停止Python服务；Java演示进程需手动结束。`--live` 会调用当前模型，最多两次请求；不带该参数只使用SDK模拟返回。`--fault-only` 只检查MCP事务回滚，不请求模型或重复三轮演示。
