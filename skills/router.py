"""按身份设定与当前社会情境加载Markdown，不读旁人的私有状态。"""

from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED = {"hospitality", "community", "craft", "social"}


@lru_cache(maxsize=4)
def read_skill(name):
    if name not in ALLOWED:
        raise ValueError("未知角色Skill")
    return (ROOT / name / "SKILL.md").read_text(encoding="utf-8")


def skill_for(person, mind):
    selected = list(person["skills"])
    if any(word in (mind["goal"] + mind["intention"]) for word in ("朋友", "交流", "误会", "聚会")) and "social" not in selected:
        selected.append("social")
    return "\n\n".join(read_skill(name) for name in selected)
