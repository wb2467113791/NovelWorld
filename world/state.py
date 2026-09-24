"""保存 NovelWorld 当前的世界状态。"""

from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

from characters.presets import CHARACTERS
from lore.catalog import load_lore
from memory.event_summary import event_memory_metadata, summarize_event
from world.events import Event, recipients_for_event


WORLD_STATE = {
    "world_id": uuid4().hex,
    "time": "08:00",
    "locations": ["晚风客栈", "县衙", "青石街"],
    # 世界状态直接保存 Character 对象，不再复制位置、体力和关系。
    "characters": CHARACTERS,
    "inspectables": {
        "晚风客栈": "一楼桌椅摆放整齐，柜台后方挂着一串旧钥匙。",
        "县衙": "案桌上放着尚未整理完的失踪案卷宗。",
        "青石街": "清晨的街面有些潮湿，行人正渐渐多起来。",
    },
    "inspectable_objects": {
        "晚风客栈": {
            "住客登记簿": "登记簿放在柜台抽屉里。现有记录未列出具体住客与时辰，无法据此核对个别人的行踪。",
            "后门": "后门通向客栈外；仅凭眼前环境无法确认案发夜经过的人是谁。",
            "柴房门锁": "柴房门锁已有锈迹；仅凭外观无法确认近期是否被打开过。",
        },
    },
    "lore": [asdict(entry) for entry in load_lore()],
    "events": [],
}

INITIAL_WORLD_STATE = deepcopy(WORLD_STATE)


def advance_world_time(minutes: int) -> str:
    """把世界时间向前推进指定分钟，并返回新时间。"""
    if minutes < 1:
        raise ValueError("推进分钟数必须至少为 1")

    from tools.remote_world import active_backend
    backend = active_backend()
    if backend is not None:
        WORLD_STATE["time"] = backend.advance_time(minutes)
        return WORLD_STATE["time"]

    hour, minute = map(int, WORLD_STATE["time"].split(":"))
    total_minutes = (hour * 60 + minute + minutes) % (24 * 60)
    new_hour, new_minute = divmod(total_minutes, 60)
    WORLD_STATE["time"] = f"{new_hour:02d}:{new_minute:02d}"
    return WORLD_STATE["time"]


def record_event(
    event_type: str,
    actor: str,
    description: str,
    *,
    target: str | None = None,
    location: str | None = None,
    payload: dict | None = None,
) -> Event:
    """记录世界行为，并让相关角色保存这段经历。"""
    event: Event = {
        "id": uuid4().hex,
        "timestamp": WORLD_STATE["time"],
        "type": event_type,
        "actor": actor,
        "target": target,
        "location": location or WORLD_STATE["characters"][actor].location,
        "payload": payload if payload is not None else {},
        "description": description,
    }
    event["perceived_by"] = recipients_for_event(event, WORLD_STATE["characters"])
    WORLD_STATE["events"].append(event)
    remember_event(event)
    return event


def remember_event(event: Event) -> None:
    """为已持久化的事件补充 Python 角色记忆，不重复写事件。"""
    event_type = event["type"]
    actor = event["actor"]
    for character_name in recipients_for_event(event, WORLD_STATE["characters"]):
        character = WORLD_STATE["characters"][character_name]
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
            )


def reconcile_event_memories() -> int:
    """从已提交事件补写缺失记忆；旧事件只补给直接参与者以免泄密。"""
    added = 0
    for event in WORLD_STATE["events"]:
        if event["type"] == "narration" and event["actor"] not in WORLD_STATE["characters"]:
            continue
        if "perceived_by" in event:
            recipients = event["perceived_by"]
        else:
            recipients = [event["actor"]]
            if event["type"] in {"talk", "give_item"} and event["target"] is not None:
                recipients.append(event["target"])
        for name in recipients:
            character = WORLD_STATE["characters"].get(name)
            if character is None:
                continue
            entry_id = f"{event['id']}:{name}"
            if any(entry.id == entry_id for entry in character.memory.all_entries()):
                continue
            # 复用正常事件投递逻辑，按事件中的知情者而非当前地点判断。
            replay_event = {**event, "perceived_by": [name]}
            remember_event(replay_event)
            added += 1
    return added
