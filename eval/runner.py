"""在隔离的世界状态中运行固定场景，并打印 Day 13 指标。"""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from agent.graph import build_agent_loop_graph
from agent.state import ToolResult, create_initial_agent_state
from characters.presets import CHARACTERS
from eval.metrics import (
    goal_consistency_stats,
    invalid_action_stats,
    knowledge_leakage_stats,
    repetition_stats,
)
from eval.scenarios import SCENARIOS, Scenario
from world.state import WORLD_STATE


@dataclass(frozen=True)
class ScenarioRun:
    scenario: Scenario
    tool_results: list[ToolResult]
    final_answer: str


@contextmanager
def scenario_world(scenario: Scenario) -> Iterator[None]:
    """每次从角色预设开始，结束后恢复调用者原有的世界。"""
    original_state = WORLD_STATE.copy()
    try:
        WORLD_STATE["time"] = "08:00"
        WORLD_STATE["characters"] = deepcopy(CHARACTERS)
        WORLD_STATE["events"] = []
        characters = WORLD_STATE["characters"]
        for name, location in scenario.location_overrides:
            characters[name].location = location
        for name, fact in scenario.fact_additions:
            characters[name].known_facts.append(fact)
        for name, memory in scenario.memory_additions:
            characters[name].memory.add(memory)
        yield
    finally:
        WORLD_STATE.clear()
        WORLD_STATE.update(original_state)


def run_scenario(
    scenario: Scenario,
    request_model: Callable[[list[dict[str, Any]], bool], Any],
) -> ScenarioRun:
    """执行一次 NPC Graph；返回模型调用和 Python 工具执行的结果。"""
    graph = build_agent_loop_graph(request_model)
    with scenario_world(scenario):
        character = WORLD_STATE["characters"][scenario.actor]
        state = graph.invoke(create_initial_agent_state(character))
        return ScenarioRun(
            scenario=scenario,
            tool_results=list(state["tool_results"]),
            final_answer=state["final_answer"] or "",
        )


def _display_rate(value: float | None) -> str:
    return "未测" if value is None else f"{value:.0%}"


def _ask_goal_label(scenario: Scenario) -> bool | None:
    print(f"目标：{scenario.expected_behavior}")
    while True:
        answer = input("行动符合目标吗？y=是 / n=否 / Enter=暂不标注 > ").strip().lower()
        if answer in ("y", "n", ""):
            return {"y": True, "n": False, "": None}[answer]
        print("请输入 y、n，或直接回车。")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 NovelWorld Day 13 固定评测场景")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--scenario", choices=[item.id for item in SCENARIOS])
    choice.add_argument("--all", action="store_true", help="运行全部 9 个场景")
    args = parser.parse_args()
    selected = SCENARIOS if args.all else tuple(
        item for item in SCENARIOS if item.id == args.scenario
    )

    # 延迟导入，离线测试不读取 .env，也不加载 API 客户端。
    from llm_client import MODEL, request_npc_graph_response

    print(f"模型：{MODEL}；每个场景最多 6 次 API 请求，{len(selected)} 个场景最多 {6 * len(selected)} 次。")
    runs: list[ScenarioRun] = []
    labels: list[tuple[Scenario, bool | None]] = []
    for scenario in selected:
        print(f"\n=== {scenario.id}｜{scenario.actor} ===")
        run = run_scenario(scenario, request_npc_graph_response)
        runs.append(run)
        for result in run.tool_results:
            print(f"Tool Call: {result['name']}({result['arguments']})")
            print(f"Tool Result: {result['output']}")
        print(f"NPC: {run.final_answer}")
        if scenario.focus == "goal_consistency":
            labels.append((scenario, _ask_goal_label(scenario)))

    invalid = invalid_action_stats(
        result for run in runs for result in run.tool_results
    )
    leakage = knowledge_leakage_stats(
        (run.scenario, run.tool_results, run.final_answer) for run in runs
    )
    goals = goal_consistency_stats(labels)
    repetition = repetition_stats(
        (run.scenario, run.tool_results) for run in runs
    )
    print("\n=== 评测汇总 ===")
    print(f"Knowledge Leakage: {_display_rate(leakage.rate)} ({leakage.leaked_scenarios}/{leakage.checked_scenarios})")
    print(f"Goal Consistency: {_display_rate(goals.rate)} ({goals.consistent}/{goals.reviewed}，待标注 {goals.pending})")
    print(f"Invalid Action: {_display_rate(invalid.rate)} ({invalid.rejected}/{invalid.attempted})")
    print(f"Repetition: {_display_rate(repetition.rate)} ({repetition.repeated}/{repetition.attempted})")


if __name__ == "__main__":
    main()
