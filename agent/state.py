"""定义单个 NPC LangGraph 流程中传递的状态。"""

from typing import Any, NotRequired, TypedDict

from characters.model import Character
from memory.retrieval import recent_memory_texts, retrieve_character_memory
from lore.catalog import retrieve_lore
from agent.perception import observe


class AgentState(TypedDict):
    """记录一次 NPC Agent Loop 在各节点之间共享的数据。"""

    # 当前行动的角色名称，用于构造角色视角并校验工具调用者。
    npc_id: str
    # 本轮正在处理的一个目标，默认取角色目标列表的第一项。
    goal: str
    # 本轮启动时的近期记忆快照，不随角色记忆的后续写入自动变化。
    memories: list[str]
    # 本轮开始时按目标检索出的历史经历与调查事实快照。
    retrieved_context: list[str]
    lore_context: list[str]
    # 本轮开始时按角色可见范围生成的现场观察。
    perception: list[str]
    # 本轮工具返回的观察结果，供后续模型决策查看。
    observations: list[str]
    # 已执行的工具轮数，用来限制 Agent Loop 的最大轮数。
    step: int
    # 模型刚提出、尚待 Python 执行的工具请求。
    pending_tool_calls: list["ToolCall"]
    # 本轮已执行的工具结果，保留 call_id 和原始参数。
    tool_results: list["ToolResult"]
    # 发给 Responses API 的对话记录，包含 Prompt、工具请求和工具结果。
    conversation: list[dict[str, Any]]
    # 模型给出的最终文字回答；尚未结束时为 None。
    final_answer: str | None


class ToolCall(TypedDict):
    """保存模型请求的工具调用；arguments 暂保持 Responses API 的 JSON 文本。"""

    name: str
    arguments: str
    call_id: str


class ToolResult(ToolCall):
    """工具执行结果，保留调用信息以便回传给 Responses API。"""

    output: str
    # 执行前的位置，供 Eval 区分在不同地点进行的调查。
    location_before: NotRequired[str]


def create_initial_agent_state(
    character: Character,
    goal: str | None = None,
    index: Any | None = None,
) -> AgentState:
    """根据角色当前信息创建一次全新的 Agent 流程状态。"""
    active_goal = goal or character.goals[0]
    query = f"{active_goal} {character.location}"

    return {
        "npc_id": character.name,
        "goal": active_goal,
        "memories": recent_memory_texts(character),
        "retrieved_context": (index.retrieve_memory(character, query) if index else retrieve_character_memory(character, query)),
        "lore_context": (index.retrieve_lore(character.name, query) if index else retrieve_lore(character.name, query)),
        "perception": observe(character),
        "observations": [],
        "step": 0,
        "pending_tool_calls": [],
        "tool_results": [],
        "conversation": [],
        "final_answer": None,
    }
