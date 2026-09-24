# NovelWorld 自主世界完整验收流程

适用范围：可编辑开局、独立世界、事件调度、NPC 知识边界、Java 行动结算、Director 和人为干预。人只观察与投放世界事件，不作为常驻玩家角色。

## 1. 启动前检查

1. 在项目根目录运行 `git status --short`，确认自己的修改仍在；不要删除 `data/`、`.env` 或已有数据库。
2. 启动 Docker Desktop 后运行 `docker compose up -d` 和 `docker compose ps`，确认 MySQL 与 Redis 正常。项目使用本机端口 3307/6380，避免误连已有 MySQL/Redis。Java 使用 JDK 17。
3. 在 `web/` 执行 `npm install`、`npm run build`。
4. 在**项目根目录**的 PowerShell 终端先确认 Maven 使用 JDK 17，再显式指定 `pom.xml` 与插件坐标启动 Spring Boot：

   ```powershell
   $env:JAVA_HOME = 'C:\Program Files\Java\jdk-17.0.2'
   $env:Path = "$env:JAVA_HOME\bin;$env:Path"
   mvn -version
   mvn -f .\world-service\pom.xml '-Dmaven.test.skip=true' 'org.springframework.boot:spring-boot-maven-plugin:4.1.1:run'
   ```

   `mvn -version` 必须显示 Java 17。看到 `Started WorldServiceApplication` 后保持这个终端运行。启动命令跳过 Maven 的测试编译；测试在下方单独运行。
5. **必须另开一个终端**，在项目根目录启动内部 Python Agent Runtime：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn web_api:app --host 127.0.0.1 --port 8001
   ```

   等待终端显示 `Application startup complete`，并保持终端运行。只启动一个 Python Runtime，且不要同时运行 `run_world.py --v2`。此时尚未执行 Tick，也不会调用模型。
6. 在第三个终端运行 `Invoke-RestMethod http://127.0.0.1:8001/internal/status` 和 `Invoke-RestMethod http://127.0.0.1:8080/api/world`；两条命令都应返回同一个 `world_id`。再打开 `http://127.0.0.1:8080`。页面应显示世界 ID、时间、角色状态，连接状态为“实时连接中”。浏览器只访问 Spring Boot 的 8080 端口。

若页面提示“运行中断：Service Unavailable”或 `/api/world` 返回 503，先检查第 5 步的 Python 终端是否仍在运行，以及 `8001/internal/status` 是否可访问。8080 的 Java 服务可以正常显示页面，但缺少 8001 的 Runtime 时无法查询调度状态。若两个端口都正常，查看 Python 终端的具体错误信息；不要仅凭 Maven 最后的 `exit code: 1` 判断原因。

## 2. 创建两个独立开局（无模型费用）

1. 确认页面“世界状态”为“已暂停”。如显示“运行中”，点“Ⅱ 暂停”，等当前 Tick 结束。记录页面左下角的原世界 ID；那里只显示前 10 位，完整 ID 可在第三个终端运行 `(Invoke-RestMethod http://127.0.0.1:8080/api/world).world_id` 取得。把它记为 **O**。
2. 点击左侧“开局工坊”。编辑区标题为“开局模板 JSON”，右侧是“创建前预览”。点“恢复默认模板”。在 JSON 的 `characters` → `林默` 中，把 `goals` 的第一项 `调查失踪案` 改为 `去晚风客栈调查住客登记簿`，把 `known_facts` 的第一项改为 `住客登记簿放在晚风客栈柜台抽屉里`。只改双引号内的文字，保留逗号、方括号和其他角色。右侧预览应立即显示林默的新目标和已知事实，且仍为 3 名 NPC、3 个地点。
3. 在“模板名称”输入 `验收模板A`，点“保存到本浏览器”，再点“创建新世界”。页面应显示完整“新世界 ID”，记为 **A**；“已保存的世界”也会多一条 A。此时左下角当前世界仍是 O，时间和事件数不应因创建而改变。保存模板只作用于当前浏览器；创建的世界进入 Java 数据库。
4. 再点“恢复默认模板”。把林默 `goals` 的第一项改为 `留在县衙核对失踪案卷宗`，把其 `known_facts` 第一项改为 `失踪案卷宗尚未核对，暂不采信客栈传闻`。预览确认后命名 `验收模板B`，依次点“保存到本浏览器”“创建新世界”，记下完整 ID **B**。确认 O、A、B 三个 ID 都不同。运行 `((Invoke-RestMethod http://127.0.0.1:8080/api/worlds).world_ids)` 可核对三个 ID 都在列表里。
5. 在“已保存的世界”找到 A，点该行“切换到此世界”。等页面左下角变为 A，点击“角色状态”里的林默，再看“林默的视角”：目标应含“去晚风客栈…”，已知事实应含“住客登记簿…”，不应出现 B 的“卷宗尚未核对…”。用同样方法切到 B、再切回 A；A 的目标和已知事实应保持原样。新世界的“已运行 Tick”为 0、“世界事件”为 0。角色视角不会展示其他人的 `secrets`；秘密仅在作者的开局预览中可见。
6. 校验失败场景：保持世界暂停，点“恢复默认模板”，在林默的 `relationships` 中另加一项 `"不存在的人": 10`（放在已有关系项后，注意逗号），点“创建新世界”。应显示关系对象无效的错误，“已保存的世界”数量不增加。恢复默认模板后，把林默 `location` 改为 `王宫`，创建应报地点不存在。再次恢复默认模板后，把苏晚的 `items` 改为 `["私人账本", "捕快腰牌"]`，创建应报物品重复归属。每次失败后都点“恢复默认模板”，不要保存错误草稿。

以上步骤不调用模型，API 费用为零。此时保持 A 为当前世界，继续下一节。

## 3. 投放线索并检查知情者（投放无模型费用）

1. 确认当前世界是 A、“已运行 Tick”为 0。页面默认位置应是林默在县衙、苏晚在晚风客栈、赵无极在青石街。先在第三个终端运行 `$before = Invoke-RestMethod http://127.0.0.1:8080/api/world`，记下 `$before.time`、`$before.event_count`、`$before.characters.'苏晚'.energy`。
2. 在“向世界投放线索”中选择 `晚风客栈`；“线索名称”填 `验收信封A`，“线索内容”填 `封口有一枚模糊的商会印记`；点“投放事件”。页面提示线索已进入世界，事件时间线新增一条“人为干预”，地点为晚风客栈。**此时先不要点“下一 Tick”。**
3. 在终端运行 `$page = Invoke-RestMethod 'http://127.0.0.1:8080/api/world-events?after=0'`，再运行 `$page.events | Where-Object { $_.type -eq 'intervention' -and $_.payload.object_name -eq '验收信封A' } | Select-Object id,location,perceived_by,payload`。应找到恰好一条事件，其 `location` 为晚风客栈、`perceived_by` 只有苏晚。`$after = Invoke-RestMethod http://127.0.0.1:8080/api/world` 后，`$after.event_count` 应比 `$before.event_count` 多 1；世界时间、三名角色的位置和苏晚体力仍与投放前相同。
4. 运行 `Invoke-RestMethod "http://127.0.0.1:8080/api/world-events?after=$($page.next_cursor)"`，新返回的 `events` 应为空。这说明已读事件不会因再次查询而重复返回；页面的事件时间线无需手动刷新也应显示刚投放的线索。
5. **此步开始可能产生模型费用。**点一次“▶ 下一 Tick”，等待“世界状态”重新显示“已暂停”；不要连续点击。A 中苏晚是这条新事件唯一的知情者，调度器会优先给她回应机会。模型可以决定调查、交谈、移动或等待，不能把具体台词或动作当作固定验收结果。若她调查 `验收信封A`，时间线应新增 `inspect`，角色视角的记忆才会增加调查结果；若她等待，可以没有新行动事件。无论选择什么，Tick 数应增加 1，世界时间从 `08:00` 到 `08:05`；若页面显示运行错误，记录错误并暂停后再排查。

新世界还给每名 NPC 一次开局目标驱动的行动机会，因此后续几 Tick 可能轮到其他角色；这不代表线索广播给了他们。线索的知情范围以第 3 步的 `perceived_by` 为准；调度器“事件优先于开局队列”由下节的确定性测试验证。投放与查询没有模型费用；真实 Tick 的费用取决于本机现有模型配置和工具轮数。

## 4. 验证世界规则与等待

1. 页面不提供“命令 NPC 攻击”或“强制 NPC 等待”按钮，因为动作应由角色自己选择。要验收 Java 规则，在**新的终端**进入项目根目录、确认 `mvn -version` 是 Java 17，运行：

   ```powershell
   mvn -f .\world-service\pom.xml '-Dtest=WorldRulesTest' test
   ```

   预期 `BUILD SUCCESS`。其中 `attackIsValidatedBeforeDamageAndRecordsWitnesses` 测试异地攻击被拒绝且不生成事件，随后同地点攻击造成 20 点伤害并记录目击者；`inventoryRequiresOwnershipAndColocation` 测试物品必须由持有者在同地点交付；`followingRequiresWitnessedDeparture` 测试跟随前必须目击离开；其他测试覆盖无效地点、重复调查、虚构已调查经历和体力不足。测试用内存样本，不修改 A/B 世界。
2. 在同一个终端运行以下**无模型费用**的调度测试：

   ```powershell
   .\.venv\Scripts\python.exe -m unittest tests.test_tick.WorldTickSchedulerTest.test_event_scheduler_waits_without_loop_and_wakes_only_witness tests.test_tick.WorldTickSchedulerTest.test_new_event_takes_priority_over_opening_goal_queue tests.test_tick.WorldTickSchedulerTest.test_handled_event_is_not_replayed_after_restart -v
   ```

   预期三个测试均为 `ok`。它们分别确认：开局行动机会耗尽后，等待不生成事件循环；新事件只唤醒目击者并优先于开局队列；重启调度器不会重复处理已消费的事件。真实 NPC 是否选择 `wait` 由模型决定，不需要为了验收反复付费碰运气。
3. 还可以验证**人为事件**的非法地点被 Java 拒绝：记录 `$count = (Invoke-RestMethod http://127.0.0.1:8080/api/world).event_count`，然后运行下列命令。预期请求报 `400`；再次查询 `event_count` 仍等于 `$count`。

   ```powershell
   Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/api/world-events' -ContentType 'application/json' -Body '{"location":"不存在的地点","object_name":"测试线索","observation":"测试内容"}'
   ```

攻击、用药、逃跑和互动若在真实剧情中自然出现，可额外核对时间线与角色状态；它们不作为必须由模型表演出来的固定步骤。模型提出动作，Java 验证后才会改变体力、生命值、物品或地点。

## 5. Director、暂停与重启

1. 先用确定性测试确认 Director 的触发边界，在项目根目录运行：

   ```powershell
   .\.venv\Scripts\python.exe -m unittest tests.test_v3_director_skills.V3DirectorAndSkillTests.test_director_proposal_runs_only_when_rule_triggers tests.test_v3_director_skills.V3DirectorAndSkillTests.test_director_event_reaches_only_characters_at_location -v
   ```

   预期两个测试均为 `ok`：规则未触发时不请求提议；触发后只添加发生地的可调查环境线索，不替 NPC 写台词。真实运行时至少到第 3 Tick 才可能触发，且取决于事件历史；**没有满足条件时不出现 Director 事件也是正确结果**。若时间线出现“世界事件”，用 `$page = Invoke-RestMethod 'http://127.0.0.1:8080/api/world-events?after=0'` 查找 `type` 为 `director` 的事件，核对 `payload.object_name`、`location`、`perceived_by`，不要期待固定文案。
2. 在页面把“间隔”滑块设为 `2s`，点“运行 10 Tick”，看到“世界状态”变为“运行中”后点“Ⅱ 暂停”。等待它显示“已暂停”，记下世界时间和 Tick 数；再等约 5 秒并刷新页面，两个值应保持不变。暂停会等待正在进行的 Tick 结束，所以点暂停后 Tick 数可能再增加 1。
3. 用第三个终端记录暂停后的状态：

   ```powershell
   $saved = Invoke-RestMethod http://127.0.0.1:8080/api/world
   $saved | Select-Object world_id,time,tick_count,event_count
   $savedIds = @($saved.events | ForEach-Object id)
   ```

   在**运行 Python Runtime 的终端**按 `Ctrl+C`，只停止 8001；保持 Java、MySQL、Redis 运行。此时页面可能暂时报 503。按第 1 节第 5 步的命令重新启动 Python，等 `Application startup complete`，刷新页面。然后运行：

   ```powershell
   $restored = Invoke-RestMethod http://127.0.0.1:8080/api/world
   $restored | Select-Object world_id,time,tick_count,event_count
   Compare-Object -ReferenceObject $savedIds -DifferenceObject @($restored.events | ForEach-Object id)
   ```

   `world_id`、时间、Tick 数和事件数应与 `$saved` 一致；`Compare-Object` 应无输出，表示原事件 ID 没有丢失或重复。再点一次“下一 Tick”，已存在的事件 ID 不应再追加一份；如果 NPC 等待，本次可能没有新行动事件。
4. 待世界暂停，在“已保存的世界”切换到 B。B 应保留自己的目标“留在县衙核对失踪案卷宗”，Tick 数仍为 0，且没有 A 的 `验收信封A` 事件。可在 B 单步运行一次并记录模型实际选择；再切回 A，A 的 Tick、事件和林默目标仍应是切走前的值。A/B 的**实际行动方向**应结合各自目标与知识观察，模型输出有随机性，不能以某一句台词或某个固定 Tool Call 作为唯一通过条件。

## 自动验证与费用边界

- Python：`.venv\Scripts\python.exe -m unittest discover -s tests -q`。
- Java：在 JDK 17 下运行 `mvn -f world-service/pom.xml test`。
- 前端：在 `web/` 运行 `npm run build`。
- 以上测试、开局操作、事件查询和人为投放均不调用模型。真实自动 Tick 会按项目现有模型配置产生费用；不需要真实模型时，先运行自动测试。

验收时记录每一步的世界 ID、事件 ID、事件 `perceived_by`、角色位置/物品/体力/生命值，以及遇到的错误信息。模型自主选择的具体台词与 Tool Call 不保证固定；以 Java 已结算的事件和状态为准。
