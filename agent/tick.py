"""选择每个 World Tick 中获得行动机会的角色。"""

from collections.abc import Callable

from characters.model import Character
from memory.reflection import reflect_on_new_memories
from tools.world_tools import execute_tool
from world.state import WORLD_STATE, advance_world_time, record_event


TICK_MINUTES = 5
REFLECTION_INTERVAL = 3
MAX_REACTION_DEPTH = 3


class WorldTickScheduler:
    """CLI 保留轮询；Web 根据事件唤醒相关角色，零体力时自动休息。"""

    def __init__(self, director=None, *, event_driven: bool = False) -> None:
        self._next_index = 0
        self._tick_count = 0
        self.director = director
        self.event_driven = event_driven
        self._event_cursor = len(WORLD_STATE["events"])
        self._pending: list[dict] = []
        self._current_depth = 0
        if event_driven:
            # 开局每名角色获得一次目标驱动的行动机会，之后由事件唤醒。
            self._pending = [{"name": name, "depth": 0} for name in WORLD_STATE["characters"]]

    def snapshot(self) -> dict:
        state = {"next_index": self._next_index, "tick_count": self._tick_count}
        if self.event_driven:
            state.update(event_driven=True, event_cursor=self._event_cursor,
                         pending=list(self._pending), current_depth=self._current_depth)
        return state

    def restore(self, state: dict) -> None:
        count = len(WORLD_STATE["characters"])
        next_index = state["next_index"]
        tick_count = state["tick_count"]
        if not isinstance(next_index, int) or not 0 <= next_index < count:
            raise ValueError("存档中的角色调度位置无效")
        if not isinstance(tick_count, int) or tick_count < 0:
            raise ValueError("存档中的 Tick 数无效")
        self._next_index = next_index
        self._tick_count = tick_count
        if self.event_driven:
            cursor = state.get("event_cursor", len(WORLD_STATE["events"]))
            pending = state.get("pending", self._pending)
            if not isinstance(cursor, int) or not 0 <= cursor <= len(WORLD_STATE["events"]):
                raise ValueError("存档中的事件游标无效")
            if not isinstance(pending, list) or len(pending) > len(WORLD_STATE["characters"]) or any(
                not isinstance(item, dict) or item.get("name") not in WORLD_STATE["characters"]
                or not isinstance(item.get("depth"), int) or not 0 <= item["depth"] <= MAX_REACTION_DEPTH
                for item in pending
            ):
                raise ValueError("存档中的待唤醒角色无效")
            if len({item["name"] for item in pending}) != len(pending):
                raise ValueError("存档中的待唤醒角色重复")
            depth = state.get("current_depth", 0)
            if not isinstance(depth, int) or not 0 <= depth <= MAX_REACTION_DEPTH:
                raise ValueError("存档中的连锁反应层级无效")
            self._event_cursor = cursor
            self._pending = list(pending)
            self._current_depth = depth

    def _collect_events(self) -> None:
        from world.events import recipients_for_event
        events = WORLD_STATE["events"]
        awakened: list[dict] = []
        for event in events[self._event_cursor:]:
            if event["type"] in {"narration", "rest"}:
                continue
            depth = 0 if event["actor"] == "世界" else self._current_depth + 1
            if depth > MAX_REACTION_DEPTH:
                continue
            for name in recipients_for_event(event, WORLD_STATE["characters"]):
                if name == event["actor"]:
                    continue
                existing = next((item for item in awakened if item["name"] == name), None)
                if existing is not None:
                    existing["depth"] = min(existing["depth"], depth)
                    continue
                self._pending = [item for item in self._pending if item["name"] != name]
                awakened.append({"name": name, "depth": depth})
        self._pending = awakened + self._pending
        self._event_cursor = len(events)

    def choose_next_character(self) -> Character:
        """返回下一名角色，保证零体力角色仍有恢复机会。"""
        characters = list(WORLD_STATE["characters"].values())
        character = characters[self._next_index]
        self._next_index = (self._next_index + 1) % len(characters)
        return character

    def run_tick(
        self,
        decide_action: Callable[[Character], str],
    ) -> dict[str, str]:
        """选择一名 NPC，并让其 Agent 决定本轮行动。"""
        if self.event_driven:
            from tools.remote_world import active_backend
            backend = active_backend()
            if backend is not None:
                backend.sync_events()
            self._collect_events()
            scheduled = self._pending.pop(0) if self._pending else None
            character = WORLD_STATE["characters"][scheduled["name"]] if scheduled else None
            self._current_depth = scheduled["depth"] if scheduled else 0
        else:
            character = self.choose_next_character()
        tick_time = WORLD_STATE["time"]
        event_count_before = len(WORLD_STATE["events"])
        try:
            if character is None:
                action_result = "暂无需要回应的事件"
            elif character.status == "unconscious":
                action_result = "失去行动能力，无法回应"
            elif character.energy == 0:
                action_result = execute_tool("rest_character", {"character": character.name},
                                             acting_character=character.name)
            else:
                action_result = decide_action(character)
        except Exception as error:
            if len(WORLD_STATE["events"]) == event_count_before:
                # 尚无已提交的行动，本次 Tick 不应消耗角色的轮次。
                if self.event_driven and scheduled:
                    self._pending.insert(0, scheduled)
                elif not self.event_driven:
                    self._next_index = (self._next_index - 1) % len(WORLD_STATE["characters"])
                raise
            # 工具已改变世界；模型的后续总结失败也不能重放同一行动。
            action_result = f"行动已发生，后续总结失败：{error}"

        narrated = len(WORLD_STATE["events"]) == event_count_before
        if narrated and not self.event_driven:
            record_event(
                "narration",
                character.name,
                f"{character.name}本轮没有执行工具：{action_result}",
            )

        advance_world_time(TICK_MINUTES)
        self._tick_count += 1
        if self.director is not None:
            # 先持久化本轮叙述，保证后续 Director 事件的时间线顺序。
            from tools.remote_world import active_backend
            backend = active_backend()
            if narrated and backend is not None:
                backend.save_agent_state(self.snapshot())
            self.director.maybe_inject(self._tick_count)
        if self.event_driven:
            self._collect_events()
        if self._tick_count % REFLECTION_INTERVAL == 0:
            for current_character in WORLD_STATE["characters"].values():
                reflect_on_new_memories(
                    current_character.memory,
                    superseded_event_ids=current_character.semantic_memory.superseded_event_ids,
                )

        return {
            "time": tick_time,
            "character": character.name if character else "世界",
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
