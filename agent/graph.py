"""用 LangGraph 组织单个 NPC 的 Agent Loop。"""

import json
from collections.abc import Callable
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from agent.state import AgentState, ToolCall, ToolResult
from characters.prompt import build_action_prompt
from tools.world_tools import READ_ONLY_TOOLS, execute_tool, unverified_inspection_claim
from world.state import WORLD_STATE


DEFAULT_MAX_TOOL_ROUNDS = 5


def build_model_prompt(state: AgentState) -> str:
    """按本轮 State 构造 NPC 可见的行动 Prompt。"""
    character = WORLD_STATE["characters"].get(state["npc_id"])
    if character is None:
        raise ValueError(f"角色不存在：{state['npc_id']}")

    return build_action_prompt(
        character,
        active_goal=state["goal"],
        memories=state["memories"],
        retrieved_context=state["retrieved_context"],
        lore_context=state.get("lore_context", []),
        observations=state["observations"],
    )


def _extract_tool_calls(response: Any) -> list[ToolCall]:
    """从 Responses 输出中提取模型提出的工具请求。"""
    return [
        {
            "name": item.name,
            "arguments": item.arguments,
            "call_id": item.call_id,
        }
        for item in response.output
        if item.type == "function_call"
    ]


def execute_pending_tools(state: AgentState) -> dict:
    """执行模型提出的工具请求，并记录实际结果或可读错误。"""
    new_results: list[ToolResult] = []
    action_done = any(
        result["name"] not in READ_ONLY_TOOLS
        and not result["output"].startswith("工具错误：")
        for result in state["tool_results"]
    )

    for call in state["pending_tool_calls"]:
        location_before = WORLD_STATE["characters"][state["npc_id"]].location
        if action_done:
            output = "工具错误：本轮已完成一次行动，请在下一 Tick 再行动"
        else:
            try:
                arguments = json.loads(call["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须是 JSON 对象")
                output = execute_tool(
                    call["name"], arguments, acting_character=state["npc_id"]
                )
            except (TypeError, ValueError) as error:
                output = f"工具错误：{error}"
            if call["name"] not in READ_ONLY_TOOLS and not output.startswith("工具错误："):
                action_done = True

        new_results.append({**call, "output": output, "location_before": location_before})

    return {
        "pending_tool_calls": [],
        "tool_results": state["tool_results"] + new_results,
        "observations": state["observations"] + [
            result["output"] for result in new_results
        ],
        "conversation": state["conversation"] + [
            {
                "type": "function_call_output",
                "call_id": result["call_id"],
                "output": result["output"],
            }
            for result in new_results
        ],
        "step": state["step"] + (1 if new_results else 0),
    }


def route_after_model_decision(state: AgentState) -> Literal["tools", "finish"]:
    """模型请求工具时执行工具，否则直接结束本轮。"""
    return "tools" if state["pending_tool_calls"] else "finish"


def build_agent_loop_graph(
    request_model: Callable[[list[dict[str, Any]], bool], Any],
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """构建模型 → 工具 → 模型的循环，可选保存流程检查点。"""
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds 必须至少为 1")

    def model_decision(state: AgentState) -> dict:
        conversation = state["conversation"] or [
            {"role": "user", "content": build_model_prompt(state)}
        ]
        action_done = any(
            result["name"] not in READ_ONLY_TOOLS
            and not result["output"].startswith("工具错误：")
            for result in state["tool_results"]
        )
        allow_tools = state["step"] < max_tool_rounds and not action_done
        response = request_model(conversation, allow_tools)
        tool_calls = _extract_tool_calls(response) if allow_tools else []
        call_messages = [
            {
                "type": "function_call",
                "name": call["name"],
                "arguments": call["arguments"],
                "call_id": call["call_id"],
            }
            for call in tool_calls
        ]
        answer = response.output_text or "已达到工具轮数上限，本轮结束。"
        if not tool_calls:
            unverified_object = unverified_inspection_claim(state["npc_id"], answer)
            if unverified_object:
                answer = f"本轮回复声称已调查{unverified_object}，但缺少工具记录。原因：需要先执行调查工具。"
        return {
            "conversation": conversation + call_messages,
            "pending_tool_calls": tool_calls,
            "final_answer": None if tool_calls else answer,
        }

    builder = StateGraph(AgentState)
    builder.add_node("model_decision", model_decision)
    builder.add_node("execute_pending_tools", execute_pending_tools)
    builder.add_edge(START, "model_decision")
    builder.add_conditional_edges(
        "model_decision",
        route_after_model_decision,
        {"tools": "execute_pending_tools", "finish": END},
    )
    builder.add_edge("execute_pending_tools", "model_decision")
    return builder.compile(checkpointer=checkpointer)
