"""保存角色最近经历的短期情节记忆。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryEntry:
    """一条角色自己的记忆及其简单检索线索。"""

    content: str
    importance: int = 1
    actors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.importance, bool) or not isinstance(self.importance, int) or not 1 <= self.importance <= 5:
            raise ValueError("记忆重要程度必须在 1 到 5 之间")


@dataclass
class ShortTermMemory:
    """按写入顺序保存最近若干条记忆。"""

    max_items: int = 5
    entries: list[MemoryEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_items <= 0:
            raise ValueError("短期记忆容量必须大于 0")

    def add(
        self,
        content: str,
        *,
        importance: int = 1,
        actors: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> None:
        """写入一条记忆；超过容量时淘汰最旧的一条。"""
        self.entries.append(MemoryEntry(content, importance, actors, tags))

        if len(self.entries) > self.max_items:
            self.entries.pop(0)

    def recent(self) -> list[str]:
        """仅返回文字，保持现有 Prompt 和 Agent State 的接口简单。"""
        return [entry.content for entry in self.entries]

    def recent_entries(self) -> list[MemoryEntry]:
        """返回带元数据的记忆副本，供后续筛选和反思使用。"""
        return self.entries.copy()
