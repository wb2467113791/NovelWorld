"""选择每个 World Tick 中获得行动机会的角色。"""

from collections.abc import Callable

from characters.model import Character
from memory.reflection import reflect_on_new_memories
from world.state import WORLD_STATE, advance_world_time, record_event


TICK_MINUTES = 5
REFLECTION_INTERVAL = 3


class WorldTickScheduler:
    """按固定顺序轮流选择体力大于 0 的角色。"""

    def __init__(self) -> None:
        self._next_index = 0
        self._tick_count = 0

    def snapshot(self) -> dict[str, int]:
        return {"next_index": self._next_index, "tick_count": self._tick_count}

    def restore(self, state: dict[str, int]) -> None:
        count = len(WORLD_STATE["characters"])
        next_index = state["next_index"]
        tick_count = state["tick_count"]
        if not isinstance(next_index, int) or not 0 <= next_index < count:
            raise ValueError("存档中的角色调度位置无效")
        if not isinstance(tick_count, int) or tick_count < 0:
            raise ValueError("存档中的 Tick 数无效")
        self._next_index = next_index
        self._tick_count = tick_count

    def choose_next_character(self) -> Character:
        """返回下一名可行动角色；没有可行动角色时抛出异常。"""
        characters = list(WORLD_STATE["characters"].values())

        for _ in characters:
            character = characters[self._next_index]
            self._next_index = (self._next_index + 1) % len(characters)

            if character.energy > 0:
                return character

        raise RuntimeError("当前没有可行动的角色")

    def run_tick(
        self,
        decide_action: Callable[[Character], str],
    ) -> dict[str, str]:
        """选择一名 NPC，并让其 Agent 决定本轮行动。"""
        character = self.choose_next_character()
        tick_time = WORLD_STATE["time"]
        event_count_before = len(WORLD_STATE["events"])
        action_result = decide_action(character)

        if len(WORLD_STATE["events"]) == event_count_before:
            record_event(
                "narration",
                character.name,
                f"{character.name}本轮没有执行工具：{action_result}",
            )

        advance_world_time(TICK_MINUTES)
        self._tick_count += 1
        if self._tick_count % REFLECTION_INTERVAL == 0:
            for current_character in WORLD_STATE["characters"].values():
                reflect_on_new_memories(
                    current_character.memory,
                    superseded_event_ids=current_character.semantic_memory.superseded_event_ids,
                )

        return {
            "time": tick_time,
            "character": character.name,
            "action_result": action_result,
        }

    def run_ticks(
        self,
        count: int,
        decide_action: Callable[[Character], str],
    ) -> list[dict[str, str]]:
        """连续运行指定次数的 World Tick。"""
        if count < 1:
            raise ValueError("Tick 次数必须至少为 1")

        return [self.run_tick(decide_action) for _ in range(count)]
