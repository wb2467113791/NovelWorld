"""用 LangGraph 组织单个 NPC 的 Agent Loop。"""

import json
from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from agent.state import AgentState, ToolCall, ToolResult
from characters.prompt import build_action_prompt
from tools.world_tools import execute_tool, unverified_inspection_claim
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
        observations=state.get("perception", []) + state["observations"],
        runtime_context=state.get("runtime_context"),
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
        not result["output"].startswith("工具错误：")
        for result in state["tool_results"]
    )

    for call in state["pending_tool_calls"]:
        if action_done:
            output = "工具错误：本轮已完成一次行动，请在下一 Tick 再行动"
        elif any(
            previous["name"] == call["name"]
            and previous["arguments"] == call["arguments"]
            and previous["output"].startswith("工具错误：")
            for previous in state["tool_results"] + new_results
        ):
            output = "工具错误：本轮相同调用已失败，请改选其他行动或等待"
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
            if not output.startswith("工具错误："):
                action_done = True

        new_results.append({**call, "output": output})

    conversation = state["conversation"] + [
        {
            "type": "function_call_output",
            "call_id": result["call_id"],
            "output": result["output"],
        }
        for result in new_results
    ]
    if any(result["output"].startswith("工具错误：") for result in new_results):
        from skills.router import skill_for
        character = WORLD_STATE["characters"][state["npc_id"]]
        updated = skill_for(character, state["goal"])
        conversation.append({"role": "user", "content":
            "工具未成功。重新考虑当前可执行步骤；不要重复相同的失败调用。"
            + (f"\n{updated}" if updated else "\n当前无可执行 Skill 步骤，可等待或处理其他可见事件。")})
    return {
        "pending_tool_calls": [],
        "tool_results": state["tool_results"] + new_results,
        "observations": state["observations"] + [
            result["output"] for result in new_results
        ],
        "conversation": conversation,
        "step": state["step"] + (1 if new_results else 0),
    }


def route_after_model_decision(state: AgentState) -> Literal["tools", "finish"]:
    """模型请求工具时执行工具，否则直接结束本轮。"""
    return "tools" if state["pending_tool_calls"] else "finish"


def build_agent_loop_graph(
    request_model: Callable[[list[dict[str, Any]], bool], Any],
):
    """构建模型 → 工具 → 模型的循环。"""

    def model_decision(state: AgentState) -> dict:
        conversation = state["conversation"] or [
            {"role": "user", "content": build_model_prompt(state)}
        ]
        action_done = any(
            not result["output"].startswith("工具错误：")
            for result in state["tool_results"]
        )
        allow_tools = state["step"] < DEFAULT_MAX_TOOL_ROUNDS and not action_done
        response = request_model(conversation, allow_tools)
        # 同一次模型回复可提出认知修订；它不执行世界行为，也不消耗行动额度。
        character = WORLD_STATE["characters"][state["npc_id"]]
        answer = response.output_text or "已达到工具轮数上限，本轮结束。"
        cognition_error = None
        try:
            envelope = json.loads(answer)
        except (ValueError, TypeError):
            envelope = None
        if isinstance(envelope, dict) and "cognition" in envelope:
            try:
                if not isinstance(envelope.get("answer"), str):
                    raise ValueError("认知回复缺少 answer 文字")
                character.runtime_state = character.runtime_state.revised(
                    envelope["cognition"], character=character.name, goals=character.goals)
                conversation = conversation + [{"role": "assistant", "content": response.output_text}]
                answer = envelope["answer"]
            except ValueError as error:
                cognition_error = f"认知更新未保存：{error}"
                answer = cognition_error
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
        if not tool_calls:
            unverified_object = unverified_inspection_claim(state["npc_id"], answer)
            if unverified_object:
                answer = f"本轮回复声称已调查{unverified_object}，但缺少工具记录。原因：需要先执行调查工具。"
        return {
            "conversation": conversation + call_messages + (
                [{"role": "user", "content": cognition_error}] if cognition_error else []),
            "goal": character.runtime_state.select_goal(character.goals),
            "runtime_context": character.runtime_state.to_dict(),
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
    return builder.compile()
