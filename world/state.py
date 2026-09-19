"""保存 NovelWorld 当前的世界状态。"""

from characters.presets import CHARACTERS


WORLD_STATE = {
    "time": "08:00",
    "locations": ["晚风客栈", "县衙", "青石街"],
    # 世界状态直接保存 Character 对象，不再复制位置、体力和关系。
    "characters": CHARACTERS,
    "inspectables": {
        "晚风客栈": "一楼桌椅摆放整齐，柜台后方挂着一串旧钥匙。",
        "县衙": "案桌上放着尚未整理完的失踪案卷宗。",
        "青石街": "清晨的街面有些潮湿，行人正渐渐多起来。",
    },
    "events": [],
}


def advance_world_time(minutes: int) -> str:
    """把世界时间向前推进指定分钟，并返回新时间。"""
    if minutes < 1:
        raise ValueError("推进分钟数必须至少为 1")

    hour, minute = map(int, WORLD_STATE["time"].split(":"))
    total_minutes = (hour * 60 + minute + minutes) % (24 * 60)
    new_hour, new_minute = divmod(total_minutes, 60)
    WORLD_STATE["time"] = f"{new_hour:02d}:{new_minute:02d}"
    return WORLD_STATE["time"]


def record_event(
    event_type: str,
    actor: str,
    description: str,
    participants: list[str],
) -> dict:
    """记录世界行为，并让相关角色保存这段经历。"""
    event = {
        "time": WORLD_STATE["time"],
        "type": event_type,
        "actor": actor,
        "description": description,
    }
    WORLD_STATE["events"].append(event)

    for character_name in participants:
        WORLD_STATE["characters"][character_name].memory.add(description)

    return event
