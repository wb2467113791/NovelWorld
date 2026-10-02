"""选择每个 World Tick 中获得行动机会的角色。"""

from collections.abc import Callable
from copy import deepcopy

from agent.runtime import DEFAULT_AGENDA_DELAY
from characters.model import Character
from memory.reflection import reflect_on_new_memories
from tools.world_tools import execute_tool
from world.state import WORLD_STATE, advance_world_time


TICK_MINUTES = 5
REFLECTION_INTERVAL = 3
MAX_REACTION_DEPTH = 3


class WorldTickScheduler:
    """事件优先，其次到期 Agenda；保留开局与 Skill 兼容机会。"""

    def __init__(self, director=None) -> None:
        self._tick_count = 0
        self.director = director
        self._event_cursor = len(WORLD_STATE["events"])
        self._current_depth = 0
        self._pending: list[dict] = [{"name": name, "depth": 0, "source": "bootstrap"}
                                    for name in WORLD_STATE["characters"]]

    def snapshot(self) -> dict:
        from skills.router import skill_view
        return {"tick_count": self._tick_count, "event_cursor": self._event_cursor,
                "pending": deepcopy(self._pending), "current_depth": self._current_depth,
                "skill_views": {name: view for name, character in WORLD_STATE["characters"].items()
                                if (view := skill_view(character)) is not None}}

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
            or item.get("source", "legacy") not in {"event", "bootstrap", "skill", "legacy"}
            for item in pending
        ):
            raise ValueError("存档中的待唤醒角色无效")
        if len({item["name"] for item in pending}) != len(pending):
            raise ValueError("存档中的待唤醒角色重复")
        if not isinstance(depth, int) or not 0 <= depth <= MAX_REACTION_DEPTH:
            raise ValueError("存档中的连锁反应层级无效")
        self._tick_count = tick_count
        self._event_cursor = cursor
        # 旧快照无法区分来源；保留顺序并按事件优先级处理，避免降低已保存反应的优先级。
        self._pending = [{**item, "source": item.get("source", "legacy")} for item in pending]
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
                awakened.append({"name": name, "depth": depth, "source": "event"})
        self._pending = awakened + self._pending
        self._event_cursor = len(events)

    def _select_opportunity(self) -> dict | None:
        reaction = next((item for item in self._pending if item["source"] in {"event", "legacy"}), None)
        if reaction is not None:
            self._pending.remove(reaction)
            return reaction
        candidates = []
        for order, (name, character) in enumerate(WORLD_STATE["characters"].items()):
            runtime = character.runtime_state
            runtime.prune_agenda()
            if character.status == "unconscious" or (
                runtime.busy_until is not None and self._tick_count < runtime.busy_until
            ):
                continue
            for position, entry in enumerate(runtime.agenda):
                if entry.status == "pending" and entry.due_tick <= self._tick_count:
                    candidates.append((entry.due_tick, order, position, name, entry.id))
        if candidates:
            _, _, _, name, agenda_id = min(candidates)
            # 本轮已经给出机会，不能又重复使用此人的开局或 Skill 兼容机会。
            self._pending = [item for item in self._pending if item["name"] != name]
            return {"name": name, "depth": 0, "source": "agenda", "agenda_id": agenda_id}
        return self._pending.pop(0) if self._pending else None

    def _finish_opportunity(self, scheduled: dict) -> None:
        # 工具刷新和模型修订都可能重建 Character / runtime，必须在当前对象上按 ID 更新。
        character = WORLD_STATE["characters"][scheduled["name"]]
        runtime = character.runtime_state
        next_tick = self._tick_count + 1
        for entry in runtime.agenda:
            if entry.status != "pending":
                continue
            if scheduled["source"] == "agenda" and entry.id == scheduled["agenda_id"]:
                # completed 只表示这次行动机会已消费，不表示意图或世界目标已完成。
                entry.status = "completed"
            elif scheduled["source"] != "agenda" and entry.due_tick <= self._tick_count:
                # 事件优先获得机会后，保留提醒并冷却，避免下一 Tick 再次重复唤醒。
                entry.due_tick = next_tick + DEFAULT_AGENDA_DELAY
        runtime.prune_agenda()
        if character.status != "unconscious":
            runtime.schedule_next_agenda(character=character.name, current_tick=next_tick, goals=character.goals)

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
        scheduled = self._select_opportunity()
        character = WORLD_STATE["characters"][scheduled["name"]] if scheduled else None
        from skills.investigation.workflow import completed_step
        from skills.router import current_step

        # 只有旧兼容来源延续原 Skill 续排；Agenda 的节奏不取决于 Workflow 步骤。
        skill_step = current_step(character) if character and scheduled["source"] != "agenda" else None
        self._current_depth = scheduled["depth"] if scheduled else 0
        tick_time = WORLD_STATE["time"]
        event_count_before = len(WORLD_STATE["events"])
        try:
            if character is None:
                action_result = "暂无需要回应的事件或到期安排"
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
                if scheduled and scheduled["source"] != "agenda":
                    self._pending.insert(0, scheduled)
                raise
            # 工具已改变世界；模型的后续总结失败也不能重放同一行动。
            action_result = f"行动已发生，后续总结失败：{error}"

        # 先消费已完成的机会；即使后续推进时钟或 Director 出错，也不能重放已提交行动。
        if scheduled is not None:
            self._finish_opportunity(scheduled)
        advance_world_time(TICK_MINUTES)
        self._tick_count += 1
        if self.director is not None:
            idle = scheduled is None and not had_new_events and not self._pending
            self.director.maybe_inject(self._tick_count, idle=idle)
        self._collect_events()
        if self._tick_count % REFLECTION_INTERVAL == 0:
            for current_character in WORLD_STATE["characters"].values():
                reflect_on_new_memories(
                    current_character.memory,
                    superseded_event_ids=current_character.semantic_memory.superseded_event_ids,
                )

        # 只在角色真实完成一步调查行动后安排下一步；计划本身不产生世界事件。
        if character is not None and any(
            completed_step(skill_step, event, character.name)
            for event in WORLD_STATE["events"][event_count_before:]
        ):
            current = WORLD_STATE["characters"][character.name]
            if current_step(current) and not any(
                item["name"] == current.name for item in self._pending
            ):
                self._pending.append({"name": current.name, "depth": 0, "source": "skill"})

        return {
            "time": tick_time,
            "character": character.name if character else "世界",
            "action_result": action_result,
            "source": scheduled["source"] if scheduled else "idle",
            "agenda_id": scheduled.get("agenda_id", "") if scheduled else "",
        }
