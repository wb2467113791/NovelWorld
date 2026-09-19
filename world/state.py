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


def record_event(event_type: str, actor: str, description: str) -> dict:
    """把一次已发生的世界行为追加到事件日志。"""
    event = {
        "time": WORLD_STATE["time"],
        "type": event_type,
        "actor": actor,
        "description": description,
    }
    WORLD_STATE["events"].append(event)
    return event
