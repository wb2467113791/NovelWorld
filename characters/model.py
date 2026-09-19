"""定义 NovelWorld 中一个角色的完整当前状态。"""

from dataclasses import dataclass, field


@dataclass
class Character:
    """一个 NPC 的设定、位置、体力和独立信息视角。"""

    name: str
    role: str
    background: str
    personality: str
    goals: list[str]
    location: str
    energy: int
    secrets: list[str] = field(default_factory=list)
    known_facts: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
