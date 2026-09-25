# NovelWorld

NovelWorld 是一个自主叙事世界原型：NPC 根据自己的目标、知识与记忆行动；人通过网页观察，并可偶尔向世界投放线索。模型提出行动，Java 世界规则校验并结算，成功后才产生事件和状态变化。

第一次读代码，先看[跟着代码理解项目](docs/NovelWorld_跟着代码学项目.md)。想系统掌握架构与面试讲法，阅读[项目整体说明与面试掌握手册](docs/NovelWorld_项目整体说明.md)。逐步操作见[自主世界完整验收流程](docs/NovelWorld_自主世界完整验收流程.md)。

## 当前架构

```mermaid
flowchart LR
  UI[React 世界观测台] -->|HTTP / SSE| J[Spring Boot 世界服务]
  J -->|本机控制 HTTP| P[Python Agent Runtime]
  P --> S[事件调度器]
  S --> N[NPC Agent / LangGraph]
  S --> D[Director]
  N -->|模型决策| L[Qwen Responses]
  D -->|按规则提议线索| L
  N -->|MCP 行动请求| J
  D -->|MCP 环境事件| J
  J --> R[WorldRules]
  R --> M[(MySQL 权威世界快照)]
  J --> C[(Redis 可重建缓存)]
```

- **NPC** 只能依据自己的设定、记忆、可见世界设定和已感知事件决定行动，也可等待。
- **Scheduler** 在新世界开局给每名 NPC 一次行动机会，之后只唤醒新事件的知情者；每 Tick 最多一名 NPC，连锁反应最多三层。空队列或等待不调用 NPC 模型、不产生行动事件；若本 Tick 没有新事件且待行动队列已空，Director 会在冷却结束后立即尝试在有角色的地点投放剧情线索，再唤醒知情者。
- **Director** 先由规则判断是否需要新线索，触发后才请求模型提出环境内容；不替 NPC 决定行为。
- **WorldRules** 校验行动者、位置、体力、物品和状态，按确定性规则结算移动、调查、交谈、交付、休息、攻击、用药、逃跑、跟随与互动。
- **Spring Boot** 是网页唯一入口；MySQL 保存权威世界快照、事件和调度进度，Redis 只作可重建快照缓存。Python 通过 MCP 提交行动，不直接写权威业务状态。

## 本机启动

需要 Docker Desktop、JDK 17、Maven、Python 3.11+ 和 Node.js。模型密钥放在未提交的 `.env` 中，使用 `DASHSCOPE_API_KEY`；模型配置见 `llm_client.py`。在项目根目录运行：

```powershell
docker compose up -d
docker compose ps
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd web
npm install
npm run build
cd ..
```

在第一个终端确保 Maven 使用 Java 17，并启动世界服务。按本机安装位置调整 `JAVA_HOME`：

**PowerShell**（提示符通常以 `PS` 开头）：

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17.0.2'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
mvn -version
mvn -f .\world-service\pom.xml '-Dmaven.test.skip=true' 'org.springframework.boot:spring-boot-maven-plugin:4.1.1:run'
```

**cmd 命令提示符**（提示符如 `C:\Users\...\novelworld>`；不要复制上面的单引号）：

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-17.0.2"
set "PATH=%JAVA_HOME%\bin;%PATH%"
mvn -version
mvn -f .\world-service\pom.xml -Dmaven.test.skip=true org.springframework.boot:spring-boot-maven-plugin:4.1.1:run
```

**保持这个终端开着**，等日志出现 `Started WorldServiceApplication`。另开一个 PowerShell 终端，在项目根目录确认 Java 的 8080 已可访问：

```powershell
(Invoke-WebRequest 'http://127.0.0.1:8080/' -UseBasicParsing).StatusCode
```

若检查终端也是 cmd，可运行 `curl.exe -I http://127.0.0.1:8080/`，预期看到 `HTTP/1.1 200`。

预期为 `200`。若此时访问 `/api/world` 返回 `503`，是因为 Python 尚未启动，先继续下一步。若首页也连不上，请回到 Java 终端查看启动失败信息；不要先启动 Python。

保持 Java 终端运行，在第二个终端启动唯一的内部 Agent Runtime：

```powershell
.\.venv\Scripts\python.exe -m uvicorn web_api:app --host 127.0.0.1 --port 8001
```

**也保持第二个终端开着**，等日志出现 `Application startup complete`。可在第三个终端验证两端已连通：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8001/internal/status'
Invoke-RestMethod 'http://127.0.0.1:8080/api/world'
```

若第三个终端也是 cmd，可分别运行 `curl.exe http://127.0.0.1:8001/internal/status` 和 `curl.exe http://127.0.0.1:8080/api/world`；两条命令都应返回 JSON，而不是连接错误。

然后在浏览器打开 `http://127.0.0.1:8080`。页面只访问 Spring Boot 的 8080 端口；8001 只供 Java 本机控制。Docker 默认将项目 MySQL / Redis 映射到本机 `3307` / `6380`。

启动故障可按端口定位：**首页也打不开**，先检查 Java 终端和 8080；**首页能打开但世界数据报 `Service Unavailable`**，检查 Python 终端和 8001；**Python 启动时出现 `httpx.ConnectError: All connection attempts failed`**，先确认 Java 仍在运行且 8080 返回 `200`。两个服务都需要各自终端持续运行。

## 使用方式

1. 在“开局工坊”编辑默认 JSON 模板并预览。可设置时间、地点、场景线索、NPC 人设、目标、秘密、已知事实、关系、体力和物品。模板草稿保存在当前浏览器；正式创建会由 Java 校验并生成新的世界 ID，不覆盖旧世界。创建和切换前需暂停。
2. 切换到新世界后，点“下一 Tick”或“运行 10/20 Tick”。开局角色先获得行动机会；其后由已提交事件唤醒知情者。每 Tick 世界时间前进 5 分钟。
3. 从时间线和角色视角观察结果。作者可在指定地点投放可调查线索；Java 记录事件发生时的知情者，下个 Tick 由相关角色自行决定反应。
4. 需要保留现有世界时，先暂停再关闭服务。MySQL 数据卷保存世界；`data/world.json` 是 Python 本地恢复副本，`data/chroma/` 是可重建检索索引。不要删除 `data/` 或 Docker 数据卷来“清理项目”。
5. 要删除旧世界，先暂停运行，在“已保存的世界”中点该世界旁的“删除世界”并确认。当前世界不能直接删除；先切换到另一个世界。删除会移除该世界的 MySQL 存档与 Redis 缓存，Git 无法恢复数据库内容。`data/chroma/<世界 ID>/` 是可重建的本地检索缓存，目前不会随世界一起清理；它不能使已删除的世界重新出现。

创建、预览、切换、查询、投放线索和自动测试不请求模型。NPC 获得行动机会时可能多次请求模型；Director 规则触发时可能有额外请求，费用由服务商按实际用量计算。

## 代码入口与验证

| 路径 | 作用 |
| --- | --- |
| `web/src/main.jsx`、`web/src/WorldSetup.jsx` | 页面、时间线、开局工坊 |
| `world-service/src/main/java/org/novelworld/world/` | 网页 API、MCP、模板、规则与 MySQL 存档 |
| `web_api.py` | Java 背后的本机 Agent Runtime 控制入口 |
| `agent/session.py`、`agent/tick.py`、`agent/graph.py` | 会话、事件调度与 NPC 决策循环 |
| `agent/director.py`、`agent/perception.py` | 剧情触发与角色观察 |
| `tools/remote_world.py`、`tools/world_tools.py` | MCP 客户端与模型工具路由 |
| `world/`、`memory/`、`retrieval/`、`lore/` | Python 世界投影、事件、记忆与设定检索 |

不调用模型的验证命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
mvn -f .\world-service\pom.xml test
cd web
npm run build
```

Java 测试需使用 JDK 17。当前项目以小规模世界的完整闭环为目标；Director 长期规划、复杂感知传播、海量 NPC 与高并发存储仍是后续演进方向。
