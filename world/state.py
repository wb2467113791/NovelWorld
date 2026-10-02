"""保存 NovelWorld 当前的世界状态。"""

from copy import deepcopy
from uuid import uuid4

from characters.presets import CHARACTERS, DEFAULT_TEMPLATE
from characters.model import is_npc
from memory.event_summary import event_memory_metadata, summarize_event
from world.events import Event, recipients_for_event


WORLD_STATE = {
    "world_id": uuid4().hex,
    **{key: deepcopy(DEFAULT_TEMPLATE[key]) for key in ("time", "locations", "inspectables", "objects", "lore")},
    "characters": CHARACTERS,
    "events": [],
    "active_conversations": [],
}

def advance_world_time(minutes: int) -> str:
    """把世界时间向前推进指定分钟，并返回新时间。"""
    if minutes < 1:
        raise ValueError("推进分钟数必须至少为 1")

    from tools.remote_world import active_backend
    backend = active_backend()
    if backend is None:
        raise RuntimeError("世界服务尚未连接")
    WORLD_STATE["time"] = backend.advance_time(minutes)
    return WORLD_STATE["time"]


def remember_event(event: Event) -> None:
    """为已持久化的事件补充 Python 角色记忆，不重复写事件。"""
    event_type = event["type"]
    actor = event["actor"]
    for character_name in recipients_for_event(event, WORLD_STATE["characters"]):
        character = WORLD_STATE["characters"][character_name]
        if not is_npc(character):
            continue
        if event_type == "talk":
            # 使用快照中已提交的来源，不把传入文本或模型认知当成证据。
            source = next(((order, actual) for order, actual in enumerate(WORLD_STATE["events"])
                           if actual["id"] == event["id"]), None)
            if source is not None:
                character.belief_memory.learn_report(source[1], owner=character_name, order=source[0])
        entry_id = f"{event['id']}:{character_name}"
        if any(entry.id == entry_id for entry in character.memory.all_entries()):
            continue
        character.memory.add(
            summarize_event(event, character_name),
            **event_memory_metadata(event),
            source_event_id=event["id"],
            timestamp=event["timestamp"],
            entry_id=entry_id,
        )
        if event_type == "inspect" and character_name == actor:
            character.semantic_memory.learn_inspection(
                owner=character_name,
                location=event["location"],
                object_name=event["payload"].get("object_name"),
                observation=event["payload"]["observation"],
                source_event_id=event["id"],
                timestamp=event["timestamp"],
                object_id=event["payload"].get("object_id"),
            )


def reconcile_event_memories() -> int:
    """从已提交事件补写缺失记忆；旧事件只补给直接参与者以免泄密。"""
    added = 0
    for event in WORLD_STATE["events"]:
        if "perceived_by" in event:
            recipients = event["perceived_by"]
        else:
            recipients = [event["actor"]]
            if event["type"] in {"talk", "give_item", "give"} and event["target"] is not None:
                recipients.append(event["target"])
        for name in recipients:
            character = WORLD_STATE["characters"].get(name)
            if character is None or not is_npc(character):
                continue
            entry_id = f"{event['id']}:{name}"
            if any(entry.id == entry_id for entry in character.memory.all_entries()):
                continue
            # 复用正常事件投递逻辑，按事件中的知情者而非当前地点判断。
            replay_event = {**event, "perceived_by": [name]}
            remember_event(replay_event)
            added += 1
    return added
