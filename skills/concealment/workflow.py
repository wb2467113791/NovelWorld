"""根据角色当前可见对象和目标建议藏匿；是否成功只看 Java 事件。"""

from characters.model import Character
from skills.investigation.workflow import InvestigationStep
from world.state import WORLD_STATE


def next_step(character: Character, goal: str) -> InvestigationStep | None:
    if not any(word in goal for word in ("保护", "隐瞒", "藏")) or character.energy < 3:
        return None
    location = character.location
    visible = WORLD_STATE["inspectable_objects"].get(location, {})
    concealed_before = {
        event["payload"].get("object_name")
        for event in WORLD_STATE["events"]
        if event["type"] == "conceal" and event["actor"] == character.name
        and event["location"] == location
    }
    for object_name in WORLD_STATE.get("concealable_objects", {}).get(location, []):
        if object_name in visible and object_name not in concealed_before:
            return InvestigationStep(
                "藏匿可疑线索", "conceal_clue",
                {"character": character.name, "object_name": object_name},
                f"本人所在的{location}有可藏匿的{object_name}，且尚未藏过",
            )
    return None
