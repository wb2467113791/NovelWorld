"""为单个 NPC 生成地点和事件范围内的观察，不暴露他人私有状态。"""

from characters.model import Character
from world.state import WORLD_STATE


def observe(character: Character) -> list[str]:
    location = character.location
    nearby = [
        other.name for other in WORLD_STATE["characters"].values()
        if other.name != character.name and other.location == location
    ]
    observations = [
        f"同地点角色：{'、'.join(nearby) if nearby else '暂无'}"
    ]
    witnessed = [
        event for event in WORLD_STATE["events"]
        if character.name in event.get("perceived_by", [event["actor"]])
        and event["type"] not in {"narration", "rest"}
        and event["id"] not in character.semantic_memory.superseded_event_ids
    ]
    observations.extend(f"已感知事件：{event['description']}" for event in witnessed[-3:])
    return observations
