"""定义可供时间线和角色感知使用的结构化世界事件。"""

from collections.abc import Mapping
from typing import Any, TypedDict

from characters.model import Character


class Event(TypedDict):
    """一次已发生的世界行为，字段共同描述谁在何时何地做了什么。"""

    # 唯一 ID，用于关联角色记忆与其来源事件。
    id: str
    # 行为类别，例如 move、talk、inspect 或 relationship。
    type: str
    # 发起行为的角色名称。
    actor: str
    # 行为指向的角色；移动和调查没有角色目标时为 None。
    target: str | None
    # 行为发生的地点；移动事件使用抵达后的地点。
    location: str
    # 各类事件的细节，例如对话内容或移动前后的地点。
    payload: dict[str, Any]
    # 记录事件时的世界时间，当前格式为 HH:MM。
    timestamp: str
    # 供现有短期记忆和剧情日志阅读的中文描述。
    description: str


def recipients_for_event(
    event: Event,
    characters: Mapping[str, Character],
) -> list[str]:
    """按事件类别确定能感知事件的角色，返回不重复的姓名。"""
    recipients = [event["actor"]]

    if event["type"] in {"talk", "give_item"} and event["target"] is not None:
        recipients.append(event["target"])
    elif event["type"] == "move":
        recipients.extend(
            name for name, character in characters.items()
            if name != event["actor"] and character.location == event["location"]
        )

    return recipients
