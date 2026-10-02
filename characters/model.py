"""定义 NovelWorld 中一个角色的完整当前状态。"""

from dataclasses import dataclass, field

from memory.short_term import ShortTermMemory
from memory.semantic import SemanticMemory
from agent.runtime import AgentRuntimeState


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
    hp: int = 100
    status: str = "normal"
    secrets: list[str] = field(default_factory=list)
    known_facts: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
    # 兼容展示字段；运行中的 inventory 以 Java snapshot objects.holder 为准。
    items: list[str] = field(default_factory=list)
    memory: ShortTermMemory = field(default_factory=ShortTermMemory)
    semantic_memory: SemanticMemory = field(default_factory=SemanticMemory)
    runtime_state: AgentRuntimeState = field(default_factory=AgentRuntimeState)
    actor_type: str = "npc"


@dataclass
class PlayerActor:
    """人控制的物理实体；没有 NPC 认知、记忆或自主调度。"""

    name: str
    location: str
    energy: int = 100
    hp: int = 100
    status: str = "normal"
    items: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
    actor_type: str = "player"


def is_npc(actor) -> bool:
    return getattr(actor, "actor_type", "npc") == "npc"
