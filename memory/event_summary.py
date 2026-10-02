"""将已发生的事件写成单个角色能记住的视角摘要。"""

from world.events import Event


# legacy history only：narration/relationship/give_item/conceal/recover/use_item 仅供旧 Event 读取。
EVENT_IMPORTANCE = {
    "narration": 1,
    "move": 2,
    "inspect": 3,
    "talk": 3,
    "relationship": 4,
    "give_item": 3,
    "rest": 1,
    "director": 4,
    "conceal": 4,
    "recover": 4,
    "take": 3, "put": 3, "give": 3, "use": 3, "interact": 3,
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

    if kind in {"give_item", "give"}:
        item = payload["item"]
        if observer == actor:
            return f"我把{item}交给了{target}。"
        return f"{actor}把{item}交给了我。"

    if kind == "move":
        origin = payload["from"]
        if observer == actor:
            return f"我从{origin}来到{location}。"
        return f"我在{location}看到{actor}来到这里。"

    if kind == "inspect":
        object_name = payload.get("object_name")
        subject = f"{location}的{object_name}" if object_name else location
        return f"我调查了{subject}：{payload['observation']}"

    if kind == "relationship":
        return (
            f"我对{target}的关系值从{payload['old_value']}"
            f"变为{payload['new_value']}。"
        )

    if kind == "rest":
        return event["description"] if observer != actor else f"我休息后体力恢复到{payload['energy_after']}。"

    if kind == "director":
        return f"我在{location}注意到：{event['description']}"

    # legacy history only：旧 narration/conceal/recover/use_item 历史仍可显示原描述。
    return event["description"]
