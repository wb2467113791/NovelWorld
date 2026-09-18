# NovelWorld Codex 协作约定

## 项目目标

NovelWorld 是一个用于学习 Agent 工程的动态叙事世界引擎。当前优先完成两周 V1：先让角色、工具、世界状态、记忆和多 Agent Tick 形成可运行的最小闭环。

## 和作者协作

- 作者是初学者，修改代码时先用简短中文解释“为什么这样改”，再实施修改。
- 讲解新功能时，顺带补充少量与当前内容直接相关的 AI / Agent 原理或面试知识；首次出现的重要英文术语要给出中文含义，但不要让面试内容喧宾夺主。
- 区分“模型做的事”和“Python 程序做的事”，尤其说明模型选择工具、程序执行工具、规则校验和状态修改之间的边界。
- 每次只完成一个可验证的小目标，不提前引入 LangGraph、RAG、MCP、数据库或 Web UI，除非作者明确要求。
- 优先保留简单、可读、容易调试的 Python 实现。
- 不删除或覆盖用户已有代码；发现不确定的设计时先说明影响。
- 修改后运行相关命令或测试，并报告实际结果。
- 如果涉及 API、模型或费用，先明确说明，不擅自更换模型或扩大调用范围。

## 当前工作流

1. 先检查现有文件和 Git 状态。
2. 说明本次目标、将修改的文件和验收方式。
3. 小步修改。
4. 运行最小验证，例如 `python main.py` 或针对性测试。
5. 总结改了什么、学到了什么、对应的少量 AI 知识和下一步是什么。
6. 每个学习日结束时检查 Git 状态，完成一次清晰的 commit，并 push 到当前远程分支；提交前不得包含 `.env`、`.venv` 或其他敏感文件。

## 当前学习进度

### Day 1：Python 环境与最小 LLM 调用

- 已创建 Python 项目、环境变量配置、LLM 客户端和角色扮演 CLI。
- `llm_client.py` 使用 OpenAI Python SDK 的 Responses API 接口形式调用模型。
- API Key 放在 `.env`，代码通过 `python-dotenv` 读取；`.env` 必须被 Git 忽略。
- 已理解 Git 分支是指向 Commit 的引用；`git branch -m` 是安全重命名，`-M` 允许强制覆盖已有目标分支引用。

### Day 2：Tool Calling——世界时间工具

- `WORLD_STATE` 保存程序中的真实世界状态，当前包含世界时间。
- `get_world_time()` 是真正执行读取操作的 Python 函数。
- Tool Schema 是给模型看的工具说明书，描述工具名称、用途和参数格式；Schema 本身不会执行函数。
- `TOOL_FUNCTIONS` 是工具注册表，把模型返回的字符串名称映射到允许执行的 Python 函数，避免使用不安全的 `eval()`。
- `execute_tool(name, arguments)` 是统一工具执行入口；未知工具会被拒绝。
- 模型返回的 `arguments` 是 JSON 字符串，需要用 `json.loads()` 转成 Python 字典。
- `call_id` 用于关联某次 `function_call` 与对应的 `function_call_output`。
- 一次完整工具调用通常需要两次模型请求：第一次由模型决定是否调用工具，Python 执行后，第二次由模型根据真实工具结果组织最终回答。
- 已实现 `move_character(character, location)`：校验角色和地点后，真实修改角色在 `WORLD_STATE` 中的位置。
- 当前实现支持模型在同一轮响应中请求一个或多个工具；连续多轮的 Reason → Act → Observe 循环留到 Day 3。
- 已通过真实 API 验证 `get_world_time` 与 `move_character`。模型能够先移动苏晚，再读取世界时间，并根据两个真实工具结果生成回答。


## 安全约定

- 不读取、打印或提交 `.env` 中的密钥。
- 不执行破坏性 Git 操作，除非作者明确要求。
- 所有世界状态的真实变化必须由 Python 代码和工具执行，不能只靠模型文本假装发生。
