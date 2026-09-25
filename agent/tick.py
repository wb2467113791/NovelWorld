"""选择每个 World Tick 中获得行动机会的角色。"""

from collections.abc import Callable

from characters.model import Character
from memory.reflection import reflect_on_new_memories
from tools.world_tools import execute_tool
from world.state import WORLD_STATE, advance_world_time


TICK_MINUTES = 5
REFLECTION_INTERVAL = 3
MAX_REACTION_DEPTH = 3


class WorldTickScheduler:
    """根据事件唤醒相关角色，零体力时自动休息。"""

    def __init__(self, director=None) -> None:
        self._tick_count = 0
        self.director = director
        self._event_cursor = len(WORLD_STATE["events"])
        self._current_depth = 0
        # 开局每名角色获得一次目标驱动的行动机会，之后由事件唤醒。
        self._pending: list[dict] = [{"name": name, "depth": 0} for name in WORLD_STATE["characters"]]

    def snapshot(self) -> dict:
        return {"tick_count": self._tick_count, "event_cursor": self._event_cursor,
                "pending": list(self._pending), "current_depth": self._current_depth}

    def restore(self, state: dict) -> None:
        tick_count = state["tick_count"]
        cursor = state.get("event_cursor", len(WORLD_STATE["events"]))
        pending = state.get("pending", self._pending)
        depth = state.get("current_depth", 0)
        if not isinstance(tick_count, int) or tick_count < 0:
            raise ValueError("存档中的 Tick 数无效")
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
        if not isinstance(depth, int) or not 0 <= depth <= MAX_REACTION_DEPTH:
            raise ValueError("存档中的连锁反应层级无效")
        self._tick_count = tick_count
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

    def run_tick(
        self,
        decide_action: Callable[[Character], str],
    ) -> dict[str, str]:
        """选择一名 NPC，并让其 Agent 决定本轮行动。"""
        from tools.remote_world import active_backend
        backend = active_backend()
        if backend is None:
            raise RuntimeError("世界调度需要已连接的世界服务")
        backend.sync_events()
        had_new_events = len(WORLD_STATE["events"]) > self._event_cursor
        self._collect_events()
        scheduled = self._pending.pop(0) if self._pending else None
        character = WORLD_STATE["characters"][scheduled["name"]] if scheduled else None
        self._current_depth = scheduled["depth"] if scheduled else 0
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
                if scheduled:
                    self._pending.insert(0, scheduled)
                raise
            # 工具已改变世界；模型的后续总结失败也不能重放同一行动。
            action_result = f"行动已发生，后续总结失败：{error}"

        advance_world_time(TICK_MINUTES)
        self._tick_count += 1
        if self.director is not None:
            idle = not had_new_events and len(WORLD_STATE["events"]) == event_count_before and not self._pending
            self.director.maybe_inject(self._tick_count, idle=idle)
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
