"""运行 NovelWorld 的多角色 World Tick。"""

from collections.abc import Callable

from agent.tick import WorldTickScheduler
from characters.model import Character


MAX_CLI_TICKS = 20


def run_world(
    count: int,
    decide_action: Callable[[Character, str], str],
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
    from llm_client import chat_with_tools
    from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS

    raw_count = input("请输入 Tick 次数（1–20，直接回车默认 1）：").strip()
    count = int(raw_count or "1")

    if not 1 <= count <= MAX_CLI_TICKS:
        raise ValueError(f"Tick 次数必须在 1–{MAX_CLI_TICKS} 之间")

    def decide_npc_action(character: Character, prompt: str) -> str:
        return chat_with_tools(
            prompt,
            tool_schemas=NPC_ACTION_TOOL_SCHEMAS,
            acting_character=character.name,
        )

    print(f"NovelWorld 将使用真实模型运行 {count} 个 World Tick。")
    run_world(count, decide_npc_action)


if __name__ == "__main__":
    main()
