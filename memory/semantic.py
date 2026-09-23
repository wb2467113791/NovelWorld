"""保存角色亲自调查后得到的、可更新的事实。"""

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class SemanticFact:
    """某角色对一个地点或对象的最新已验证观察。"""

    id: str
    owner: str
    location: str
    object_name: str | None
    observation: str
    source_event_id: str
    timestamp: str

    @property
    def content(self) -> str:
        subject = f"{self.location}的{self.object_name}" if self.object_name else self.location
        return f"{subject}：{self.observation}"


@dataclass
class SemanticMemory:
    """同一调查对象只保留最新事实，并记录被取代的事件来源。"""

    facts: dict[tuple[str, str | None], SemanticFact] = field(default_factory=dict)
    superseded_event_ids: set[str] = field(default_factory=set)

    def learn_inspection(
        self,
        *,
        owner: str,
        location: str,
        object_name: str | None,
        observation: str,
        source_event_id: str,
        timestamp: str,
    ) -> SemanticFact:
        key = (location, object_name)
        previous = self.facts.get(key)
        if previous is not None:
            if previous.source_event_id == source_event_id:
                return previous
            self.superseded_event_ids.add(previous.source_event_id)

        fact = SemanticFact(
            id=previous.id if previous is not None else uuid4().hex,
            owner=owner,
            location=location,
            object_name=object_name,
            observation=observation,
            source_event_id=source_event_id,
            timestamp=timestamp,
        )
        self.facts[key] = fact
        return fact

    def current_facts(self) -> list[SemanticFact]:
        return list(self.facts.values())
