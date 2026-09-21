"""将已发生的事件写成单个角色能记住的视角摘要。"""

from world.events import Event


EVENT_IMPORTANCE = {
    "narration": 1,
    "move": 2,
    "inspect": 3,
    "talk": 3,
    "relationship": 4,
}


def event_memory_metadata(event: Event) -> dict:
    """由事件事实确定记忆元数据，不让模型臆测重要性。"""
    actors = (event["actor"],)
    if event["target"] is not None:
        actors += (event["target"],)
    return {
        "importance": EVENT_IMPORTANCE.get(event["type"], 1),
        "actors": actors,
        "tags": (event["type"], event["location"]),
    }


def summarize_event(event: Event, observer: str) -> str:
    """只使用事件中的可见字段，不从其他角色的私有状态取信息。"""
    kind = event["type"]
    actor = event["actor"]
    target = event["target"]
    location = event["location"]
    payload = event["payload"]

    if kind == "talk":
        message = payload["message"]
        if observer == actor:
            return f"我对{target}说：“{message}”"
        return f"{actor}对我说：“{message}”"

    if kind == "move":
        origin = payload["from"]
        if observer == actor:
            return f"我从{origin}来到{location}。"
        return f"我在{location}看到{actor}来到这里。"

    if kind == "inspect":
        return f"我调查了{location}：{payload['observation']}"

    if kind == "relationship":
        return (
            f"我对{target}的关系值从{payload['old_value']}"
            f"变为{payload['new_value']}。"
        )

    # narration 是 NPC 本轮未执行工具时的文字，本身没有更多结构化细节。
    return event["description"]
