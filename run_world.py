"""运行 NovelWorld 的多角色 World Tick。"""

from collections.abc import Callable
from typing import Any

from agent.graph import build_agent_loop_graph
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.model import Character


MAX_CLI_TICKS = 20


def make_graph_decide_action(
    request_model: Callable[[list[dict[str, Any]], bool], Any],
) -> Callable[[Character], str]:
    """把单 NPC Graph 适配为 World Tick 使用的决策函数。"""
    graph = build_agent_loop_graph(request_model)

    def decide_npc_action(character: Character) -> str:
        result = graph.invoke(create_initial_agent_state(character))
        answer = result["final_answer"]
        if answer is None:
            raise RuntimeError("NPC Graph 未返回最终回答")
        return answer

    return decide_npc_action


def run_world(
    count: int,
    decide_action: Callable[[Character], str],
) -> list[dict[str, str]]:
    """连续运行 World Tick，并打印每名 NPC 的行动结果。"""
    if count < 1:
        raise ValueError("Tick 次数必须至少为 1")

    scheduler = WorldTickScheduler()
    results = []

    for tick_number in range(1, count + 1):
        result = scheduler.run_tick(decide_action)
        results.append(result)
        print(
            f"[Tick {tick_number} | {result['time']}] "
            f"{result['character']} > "
            f"{result['action_result']}"
        )

    return results


def main() -> None:
    """使用真实模型运行用户指定次数的 World Tick。"""
    # 延迟导入：普通单元测试不需要安装或调用模型 SDK。
    from llm_client import request_npc_graph_response

    raw_count = input("请输入 Tick 次数（1–20，直接回车默认 1）：").strip()
    count = int(raw_count or "1")

    if not 1 <= count <= MAX_CLI_TICKS:
        raise ValueError(f"Tick 次数必须在 1–{MAX_CLI_TICKS} 之间")

    print(f"NovelWorld 将使用 LangGraph 和真实模型运行 {count} 个 World Tick。")
    run_world(count, make_graph_decide_action(request_npc_graph_response))


if __name__ == "__main__":
    main()
