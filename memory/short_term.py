"""保存角色最近经历的短期情节记忆。"""

from dataclasses import dataclass, field


@dataclass
class ShortTermMemory:
    """按写入顺序保存最近若干条记忆。"""

    max_items: int = 5
    entries: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_items <= 0:
            raise ValueError("短期记忆容量必须大于 0")

    def add(self, content: str) -> None:
        """写入一条记忆；超过容量时淘汰最旧的一条。"""
        self.entries.append(content)

        if len(self.entries) > self.max_items:
            self.entries.pop(0)

    def recent(self) -> list[str]:
        """返回当前记忆的副本，避免外部意外修改内部列表。"""
        return self.entries.copy()
