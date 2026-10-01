"""只加载有可执行进度的调查 Skill。"""

from functools import lru_cache
from pathlib import Path

from characters.model import Character
from skills.investigation.workflow import next_step
from skills.concealment.workflow import next_step as concealment_step


SKILL_ROOT = Path(__file__).resolve().parent


def choose_skill(character: Character, goal: str | None = None) -> str | None:
    objective = goal if goal is not None else character.runtime_state.select_goal(character.goals)
    if next_step(character, objective):
        return "investigation"
    return "concealment" if concealment_step(character, objective) else None


def current_step(character: Character, goal: str | None = None):
    objective = goal if goal is not None else character.runtime_state.select_goal(character.goals)
    return next_step(character, objective) or concealment_step(character, objective)


def skill_view(character: Character) -> dict | None:
    goal = character.runtime_state.select_goal(character.goals)
    kind = choose_skill(character, goal)
    step = current_step(character, goal)
    if kind is None or step is None:
        return None
    return {"name": "调查" if kind == "investigation" else "保护与隐瞒",
            "phase": step.phase, "tool": step.tool, "reason": step.reason}


@lru_cache(maxsize=2)
def _read_skill(name: str) -> str:
    return (SKILL_ROOT / name / "SKILL.md").read_text(encoding="utf-8").strip()


def skill_for(
    character: Character,
    goal: str | None = None,
) -> str:
    objective = goal if goal is not None else character.runtime_state.select_goal(character.goals)
    kind = choose_skill(character, objective)
    step = current_step(character, objective)
    if kind is None or step is None:
        return ""
    return (
        f"{_read_skill(kind)}\n\n"
        f"当前阶段：{step.phase}\n"
        f"建议工具：{step.tool}\n"
        f"建议参数：{step.arguments}\n"
        f"依据：{step.reason}"
    )
