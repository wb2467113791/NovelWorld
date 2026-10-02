"""选择每个 World Tick 中获得行动机会的角色。"""

from collections.abc import Callable
from copy import deepcopy

from agent.runtime import DEFAULT_AGENDA_DELAY
from agent.conversation import accept_talk, end, expire, for_participant, sessions
from characters.model import Character, is_npc
from memory.reflection import reflect_on_new_memories
from tools.world_tools import execute_tool
from world.state import WORLD_STATE, advance_world_time


TICK_MINUTES = 5
REFLECTION_INTERVAL = 3
MAX_REACTION_DEPTH = 3


class WorldTickScheduler:
    """事件、会话轮次、Agenda；仅保留一次开局机会。"""

    def __init__(self, director=None) -> None:
        self._tick_count = 0
        self.director = director
        self._event_cursor = len(WORLD_STATE["events"])
        self._current_depth = 0
        self._pending: list[dict] = [{"name": name, "depth": 0, "source": "bootstrap"}
                                    for name, actor in WORLD_STATE["characters"].items() if is_npc(actor)]

    def snapshot(self) -> dict:
        return {"tick_count": self._tick_count, "event_cursor": self._event_cursor,
                "pending": deepcopy(self._pending), "current_depth": self._current_depth}

    def restore(self, state: dict) -> None:
        tick_count = state["tick_count"]
        cursor = state.get("event_cursor", len(WORLD_STATE["events"]))
        pending = state.get("pending", [])
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
        # legacy migration only：旧 Skill 队列转为 Agenda，不再恢复调度特权。
        # 无 source 的历史队列仍可能包含真实事件，保留原顺序和反应优先级。
        self._pending = []
        for item in pending:
            if not is_npc(WORLD_STATE["characters"][item["name"]]):
                continue
            if item.get("source") == "skill":
                character = WORLD_STATE["characters"][item["name"]]
                entry = character.runtime_state.schedule_next_agenda(
                    character=character.name, current_tick=tick_count, goals=character.goals)
                if entry is not None:
                    entry.due_tick = min(entry.due_tick, tick_count)
            else:
                self._pending.append({**item, "source": item.get("source", "legacy")})
        self._current_depth = depth

    def _collect_events(self, *, event_tick: int | None = None) -> None:
        from world.events import recipients_for_event
        events = WORLD_STATE["events"]
        awakened: list[dict] = []
        for event in events[self._event_cursor:]:
            if event["type"] in {"narration", "rest"}:
                continue
            conversational = accept_talk(event, self._tick_count if event_tick is None else event_tick)
            depth = 0 if event["actor"] == "世界" else self._current_depth + 1
            if depth > MAX_REACTION_DEPTH:
                continue
            for name in recipients_for_event(event, WORLD_STATE["characters"]):
                if not is_npc(WORLD_STATE["characters"][name]):
                    continue
                if name == event["actor"]:
                    continue
                if conversational and name == event["target"]:
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
        active = [session for session in sessions()
                  if is_npc(WORLD_STATE["characters"][session.next_speaker])]
        if active:
            conversation = min(enumerate(active), key=lambda item: (item[1].last_activity_tick, item[0]))[1]
            name = conversation.next_speaker
            self._pending = [item for item in self._pending if item["name"] != name]
            return {"name": name, "depth": 0, "source": "conversation", "conversation_id": conversation.id}
        candidates = []
        for order, (name, character) in enumerate(WORLD_STATE["characters"].items()):
            if not is_npc(character):
                continue
            runtime = character.runtime_state
            runtime.prune_agenda()
            if for_participant(name) is not None or character.status == "unconscious" or (
                runtime.busy_until is not None and self._tick_count < runtime.busy_until
            ):
                continue
            for position, entry in enumerate(runtime.agenda):
                if entry.status == "pending" and entry.due_tick <= self._tick_count:
                    candidates.append((entry.due_tick, order, position, name, entry.id))
        if candidates:
            _, _, _, name, agenda_id = min(candidates)
            # 本轮已经给出机会，不能又重复使用此人的开局机会。
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
        from tools.remote_world import active_backend, CommittedActionError
        backend = active_backend()
        if backend is None:
            raise RuntimeError("世界调度需要已连接的世界服务")
        backend.sync_events()
        expire(self._tick_count)
        had_new_events = len(WORLD_STATE["events"]) > self._event_cursor
        self._collect_events()
        scheduled = self._select_opportunity()
        character = WORLD_STATE["characters"][scheduled["name"]] if scheduled else None
        self._current_depth = scheduled["depth"] if scheduled else 0
        tick_time = WORLD_STATE["time"]
        event_count_before = len(WORLD_STATE["events"])
        committed_refresh_failed = False
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
            if not isinstance(error, CommittedActionError) and len(WORLD_STATE["events"]) == event_count_before:
                # 尚无已提交的行动，本次 Tick 不应消耗角色的轮次。
                if scheduled and scheduled["source"] not in {"agenda", "conversation"}:
                    self._pending.insert(0, scheduled)
                raise
            # 工具已改变世界；模型的后续总结失败也不能重放同一行动。
            committed_refresh_failed = isinstance(error, CommittedActionError)
            action_result = f"行动已发生，后续总结失败：{error}"

        # 先登记真实 talk；总结失败仍只追加一次，并从独立会话轮次继续。
        self._collect_events()
        if character is not None:
            conversation = for_participant(character.name)
            if conversation is not None and (
                getattr(action_result, "continue_conversation", None) is False or (
                    scheduled["source"] == "conversation" and not committed_refresh_failed and not any(
                        event["type"] == "talk" and event["actor"] == character.name
                        and event["target"] in conversation.participants
                        for event in WORLD_STATE["events"][event_count_before:]
                    )
                )
            ):
                end(conversation)
        expire(self._tick_count)
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
                if not is_npc(current_character):
                    continue
                reflect_on_new_memories(
                    current_character.memory,
                    superseded_event_ids=current_character.semantic_memory.superseded_event_ids,
                )

        return {
            "time": tick_time,
            "character": character.name if character else "世界",
            "action_result": action_result,
            "source": scheduled["source"] if scheduled else "idle",
            "agenda_id": scheduled.get("agenda_id", "") if scheduled else "",
            "conversation_id": scheduled.get("conversation_id", "") if scheduled else "",
        }

    def run_player_action(self, action: str, arguments: dict) -> dict:
        """Java 成功行动占用独立 Tick；不选择或执行任何 NPC 机会。"""
        from tools.remote_world import active_backend, CommittedActionError
        from world.play import submit_action
        backend = active_backend()
        if backend is None:
            raise RuntimeError("世界服务尚未连接")
        backend.sync_events()
        warning = None
        try:
            output = submit_action(action, arguments)
        except CommittedActionError as error:
            output, warning = error.output, str(error)
        # 此时已提交。即使后续时钟/同步失败，也记录已消费 Tick，且绝不重放工具。
        self._current_depth = 0
        event_tick = self._tick_count
        self._tick_count += 1
        try:
            self._collect_events(event_tick=event_tick)
            advance_world_time(TICK_MINUTES)
            expire(self._tick_count)
        except Exception as error:
            warning = f"行动已提交，后续处理失败：{error}"
        return {"committed": True, "output": output, "warning": warning, "tick_count": self._tick_count}
