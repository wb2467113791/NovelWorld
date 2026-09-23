"""按职业、目标和体力只加载当前 NPC 需要的一份 Skill。"""

from functools import lru_cache
from pathlib import Path

from characters.model import Character


SKILL_ROOT = Path(__file__).resolve().parent


def choose_skill(character: Character, goal: str | None = None) -> str:
    if character.energy < 20:
        return "survival"
    objective = goal or character.goals[0]
    if "捕快" in character.role or "调查" in objective:
        return "investigation"
    if "隐瞒" in objective or "保护弟弟" in objective:
        return "deception"
    if "商会" in character.role or "交易" in objective:
        return "trading"
    return "negotiation"


@lru_cache(maxsize=5)
def _read_skill(name: str) -> str:
    return (SKILL_ROOT / name / "SKILL.md").read_text(encoding="utf-8").strip()


def skill_for(character: Character, goal: str | None = None) -> str:
    return _read_skill(choose_skill(character, goal))
