"""只为 Prompt 加载只读专业知识和行动建议，不参与调度。"""

from functools import lru_cache
from pathlib import Path

from characters.model import Character, is_npc
from skills.investigation.workflow import next_step
from skills.concealment.workflow import next_step as concealment_step


SKILL_ROOT = Path(__file__).resolve().parent


def choose_skill(character: Character, goal: str | None = None) -> str | None:
    if not is_npc(character):
        return None
    objective = goal if goal is not None else character.runtime_state.select_goal(character.goals)
    if next_step(character, objective):
        return "investigation"
    return "concealment" if concealment_step(character, objective) else None


def current_step(character: Character, goal: str | None = None):
    if not is_npc(character):
        return None
    objective = goal if goal is not None else character.runtime_state.select_goal(character.goals)
    return next_step(character, objective) or concealment_step(character, objective)


@lru_cache(maxsize=2)
def _read_skill(name: str) -> str:
    return (SKILL_ROOT / name / "SKILL.md").read_text(encoding="utf-8").strip()


def skill_for(
    character: Character,
    goal: str | None = None,
) -> str:
    if not is_npc(character):
        return ""
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
