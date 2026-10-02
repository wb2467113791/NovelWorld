"""按角色与当前目标加载无状态专业知识，不扫描世界或推荐具体行动。"""
from functools import lru_cache
from pathlib import Path
from characters.model import Character, is_npc

SKILL_ROOT = Path(__file__).resolve().parent


def choose_skill(character: Character, goal: str | None = None) -> str | None:
    if not is_npc(character):
        return None
    # 只读目标；初始化和切换属于 Runtime，不属于 Skill。
    objective = goal if goal is not None else character.runtime_state.active_goal
    if objective is None:
        objective = next(iter(character.goals), "")
    if any(word in objective for word in ("调查", "查明", "追查", "寻找线索")) or (
        "捕快" in character.role and "线索" in objective and "保护" not in objective
    ):
        return "investigation"
    if any(word in objective for word in ("保护", "隐瞒", "藏")) or (
        any(role in character.role for role in ("老板", "守卫")) and "保管" in objective
    ):
        return "concealment"
    return None


@lru_cache(maxsize=2)
def _read_skill(name: str) -> str:
    return (SKILL_ROOT / name / "SKILL.md").read_text(encoding="utf-8").strip()


def skill_for(character: Character, goal: str | None = None) -> str:
    kind = choose_skill(character, goal)
    return _read_skill(kind) if kind else ""
