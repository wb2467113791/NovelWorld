"""有来源的主观说法；已验证观察仍只保存在 SemanticMemory。"""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from math import isfinite

MAX_BELIEFS = 50
MAX_EVIDENCE = 5


def normalized(text: str) -> str:
    return " ".join(text.split())


def visible_to(event: dict, owner: str) -> bool:
    return owner in event.get("perceived_by", [event["actor"], event.get("target")])


@dataclass
class BeliefEntry:
    id: str
    owner: str
    content: str
    source_type: str
    source_actor: str
    source_event_id: str | None
    confidence: float
    status: str
    order: int
    evidence_event_ids: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return self.source_type, self.source_actor, normalized(self.content)


@dataclass
class BeliefMemory:
    """当前决策上下文，最多 50 条；不是永久说法档案或事实结算器。"""

    entries: list[BeliefEntry] = field(default_factory=list)

    def _put(self, *, owner, content, source_type, source_actor, event_id=None, order=0) -> None:
        key = source_type, source_actor, normalized(content)
        previous = next((entry for entry in self.entries if entry.key == key), None)
        if previous is not None and (event_id is None or event_id in previous.evidence_event_ids):
            return
        if previous is not None and event_id is not None and order <= previous.order:
            return  # 历史补写不能把较旧来源重新提升为当前证据。
        evidence = list(previous.evidence_event_ids) if previous else []
        if event_id is not None:
            evidence = [*evidence, event_id][-MAX_EVIDENCE:]
        identifier = sha256(str((owner, *key)).encode("utf-8")).hexdigest()[:24]
        entry = BeliefEntry(previous.id if previous else identifier, owner, content, source_type,
                            source_actor, event_id, 0.5 if source_type == "report" else 1.0,
                            "active", order, evidence)
        self.entries = [value for value in self.entries if value.key != key] + [entry]
        self.entries.sort(key=lambda value: value.order)
        self.entries = self.entries[-MAX_BELIEFS:]

    def seed_initial(self, owner: str, known_facts: list[str]) -> None:
        for content in known_facts:
            self._put(owner=owner, content=content, source_type="initial", source_actor=owner)

    def learn_report(self, event: dict, *, owner: str, order: int) -> None:
        if event["type"] != "talk" or event["actor"] == owner or not visible_to(event, owner):
            return
        content = event["payload"].get("message")
        if isinstance(content, str) and content.strip():
            self._put(owner=owner, content=content, source_type="report", source_actor=event["actor"],
                      event_id=event["id"], order=order)

    def report_context(self, *, max_items=8, max_chars=1400) -> list[str]:
        result = []
        for entry in reversed(self.entries):
            if entry.source_type != "report":
                continue
            text = f'{entry.source_actor}曾说：“{entry.content}” [未验证，confidence={entry.confidence}]'
            if max_chars <= 0 or len(result) >= max_items:
                break
            result.append(text[:max_chars])
            max_chars -= len(result[-1])
        return result

    def to_dict(self) -> dict:
        return {"entries": [asdict(entry) for entry in self.entries]}

    @classmethod
    def from_dict(cls, raw: dict, *, owner: str, known_facts: list[str], events: list[dict]):
        if not isinstance(raw, dict) or set(raw) != {"entries"} or not isinstance(raw["entries"], list) or len(raw["entries"]) > MAX_BELIEFS:
            raise ValueError("BeliefMemory 字段或数量无效")
        try:
            entries = [BeliefEntry(**entry) for entry in raw["entries"]]
        except (TypeError, KeyError) as error:
            raise ValueError("BeliefEntry 字段无效") from error
        committed = {event["id"]: (order, event) for order, event in enumerate(events)}
        ids, keys = set(), set()
        for entry in entries:
            if any(not isinstance(value, str) or not value.strip() for value in
                   (entry.id, entry.owner, entry.content, entry.source_type, entry.source_actor, entry.status)):
                raise ValueError("Belief 文字字段无效")
            if entry.owner != owner or entry.id in ids or entry.key in keys or entry.status != "active" or entry.source_type not in {"initial", "report"}:
                raise ValueError("Belief 归属、重复或类型无效")
            ids.add(entry.id); keys.add(entry.key)
            if type(entry.confidence) not in (float, int) or not isfinite(entry.confidence) or entry.confidence != (0.5 if entry.source_type == "report" else 1.0):
                raise ValueError("Belief confidence 必须由程序确定")
            if type(entry.order) is not int or entry.order < 0 or not isinstance(entry.evidence_event_ids, list):
                raise ValueError("Belief order / evidence 无效")
            evidence = entry.evidence_event_ids
            if entry.source_type == "initial":
                if entry.source_actor != owner or entry.source_event_id is not None or evidence or entry.order != 0 or entry.content not in known_facts:
                    raise ValueError("Initial Belief 必须来自本人开局设定")
                continue
            if not 1 <= len(evidence) <= MAX_EVIDENCE or any(not isinstance(value, str) for value in evidence) or len(set(evidence)) != len(evidence) or entry.source_event_id != evidence[-1]:
                raise ValueError("Report evidence 无效")
            last_order = -1
            for event_id in evidence:
                position, event = committed.get(event_id, (-1, None))
                if not event or position <= last_order or event["type"] != "talk" or event["actor"] != entry.source_actor or event["actor"] == owner or not visible_to(event, owner) or normalized(event["payload"].get("message", "")) != normalized(entry.content):
                    raise ValueError("Report 必须来自本人可见的真实 talk")
                last_order = position
            if entry.order != last_order:
                raise ValueError("Report order 必须匹配最新证据")
        return cls(entries)
