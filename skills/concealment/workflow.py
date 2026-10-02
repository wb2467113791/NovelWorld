"""根据角色当前可见对象和目标建议藏匿；是否成功只看 Java 事件。"""

from characters.model import Character
from skills.investigation.workflow import InvestigationStep
from world.state import WORLD_STATE


def next_step(character: Character, goal: str) -> InvestigationStep | None:
    if not any(word in goal for word in ("保护", "隐瞒", "藏")) or character.energy < 3:
        return None
    from world.objects import visible_objects
    for item in visible_objects(character):
        if item["portable"] and item["holder"] is None and item["properties"].get("legacy_concealable"):
            return InvestigationStep("保护可见物品", "take", {"character": character.name, "object_id": item["id"]},
                                     f"本人可见{item['name']}，可考虑拿取保护；后续安排由角色重新判断")
    return None
