"""保存离开近期窗口、但仍属于角色自己的情节记忆。"""

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class MemoryEntry:
    """一条角色自己的记忆及其简单检索线索。"""

    content: str
    importance: int = 1
    actors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: uuid4().hex)
    source_event_id: str | None = None
    timestamp: str | None = None
    derived_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.importance, bool) or not isinstance(self.importance, int) or not 1 <= self.importance <= 5:
            raise ValueError("记忆重要程度必须在 1 到 5 之间")


@dataclass
class EpisodicArchive:
    """按原顺序保留从近期窗口移出的记忆。"""

    entries: list[MemoryEntry] = field(default_factory=list)

    def add(self, entry: MemoryEntry) -> None:
        self.entries.append(entry)

    def all_entries(self) -> list[MemoryEntry]:
        return self.entries.copy()
