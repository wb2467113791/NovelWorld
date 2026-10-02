"""根据目标和当前可见物件提供只读保护建议，不执行或调度行动。"""

from characters.model import Character
from skills.investigation.workflow import InvestigationStep


def next_step(character: Character, goal: str) -> InvestigationStep | None:
    if not any(word in goal for word in ("保护", "隐瞒", "藏")) or character.energy < 2:
        return None
    from world.objects import visible_objects
    for item in visible_objects(character):
        if item["portable"] and item["holder"] is None:
            return InvestigationStep("保护可见物品", "take", {"character": character.name, "object_id": item["id"]},
                                     f"本人可见{item['name']}，可考虑拿取保护；后续安排由角色重新判断")
    return None
