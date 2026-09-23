"""保存角色最近经历的短期情节记忆。"""

from dataclasses import dataclass, field

from memory.episodic import EpisodicArchive, MemoryEntry


@dataclass
class ShortTermMemory:
    """保留近期窗口，将超出窗口的经历移到本人的情节档案。"""

    max_items: int = 5
    entries: list[MemoryEntry] = field(default_factory=list)
    archive: EpisodicArchive = field(default_factory=EpisodicArchive)
    reflection_cursor: int = 0

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
        source_event_id: str | None = None,
        timestamp: str | None = None,
        derived_event_ids: tuple[str, ...] = (),
        entry_id: str | None = None,
    ) -> None:
        """写入一条记忆；超过容量时归档最旧的一条。"""
        self.entries.append(MemoryEntry(
            content, importance, actors, tags,
            source_event_id=source_event_id, timestamp=timestamp,
            derived_event_ids=derived_event_ids,
            **({"id": entry_id} if entry_id is not None else {}),
        ))

        if len(self.entries) > self.max_items:
            self.archive.add(self.entries.pop(0))

    def recent(self) -> list[str]:
        """仅返回文字，保持现有 Prompt 和 Agent State 的接口简单。"""
        return [entry.content for entry in self.entries]

    def recent_entries(self) -> list[MemoryEntry]:
        """返回带元数据的记忆副本，供后续筛选和反思使用。"""
        return self.entries.copy()

    def archived_entries(self) -> list[MemoryEntry]:
        """返回已移出近期窗口的记忆副本。"""
        return self.archive.all_entries()

    def all_entries(self) -> list[MemoryEntry]:
        """按写入顺序返回归档和近期记忆。"""
        return self.archived_entries() + self.recent_entries()
