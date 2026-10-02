"""角色认知状态；不代表世界事实，也不执行计划或调度 Agenda。"""

from dataclasses import asdict, dataclass, field

MODEL_COGNITION_FIELDS = frozenset({"active_goal", "current_intention", "current_plan"})


def _text(value, name, *, nullable=True):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空文字")


def _tick(value, name, *, nullable=True):
    if value is None and nullable:
        return
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} 必须是非负累计 Tick 序号")


@dataclass
class AgendaEntry:
    id: str
    character: str
    due_tick: int
    intention: str
    status: str = "pending"

    def __post_init__(self):
        for name in ("id", "character", "intention"):
            _text(getattr(self, name), name, nullable=False)
        _tick(self.due_tick, "due_tick", nullable=False)
        if not isinstance(self.status, str) or self.status not in {"pending", "completed", "cancelled"}:
            raise ValueError("Agenda status 无效")


@dataclass
class AgentRuntimeState:
    active_goal: str | None = None
    current_intention: str | None = None
    current_plan: str | None = None
    # 系统维护的调度状态；不能由模型 cognition 更新。
    agenda: list[AgendaEntry] = field(default_factory=list)
    # 世界累计 Tick 序号；由程序根据真实执行结果维护，尚不影响调度。
    busy_until: int | None = None

    def select_goal(self, goals: list[str]) -> str:
        """保留显式选择；首次或目标被移除时才按设定顺序选择。"""
        if self.active_goal not in goals:
            if self.active_goal is not None:
                self.current_intention = None
                self.current_plan = None
            self.active_goal = next((goal for goal in goals if goal.strip()), None)
        return self.active_goal or ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict, *, character: str):
        """解析程序持久化的完整状态；模型更新必须通过 revised 的字段白名单。"""
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise ValueError("Agent runtime 字段无效")
        for name in ("active_goal", "current_intention", "current_plan"):
            _text(data.get(name), name)
        _tick(data.get("busy_until"), "busy_until")
        raw_agenda = data.get("agenda", [])
        if not isinstance(raw_agenda, list):
            raise ValueError("Agenda 必须是列表")
        try:
            agenda = [AgendaEntry(**entry) for entry in raw_agenda]
        except TypeError as error:
            raise ValueError("Agenda 字段无效") from error
        if any(entry.character != character for entry in agenda):
            raise ValueError("Agenda 只能属于当前角色")
        if len({entry.id for entry in agenda}) != len(agenda):
            raise ValueError("Agenda ID 重复")
        return cls(**{**data, "agenda": agenda})

    def revised(self, changes: dict, *, character: str, goals: list[str]):
        """模型只修订目标、意图和计划；系统调度字段连清空也不允许。"""
        if not isinstance(changes, dict):
            raise ValueError("认知更新必须是对象")
        if set(changes) - MODEL_COGNITION_FIELDS:
            raise ValueError("模型仅可更新 active_goal、current_intention、current_plan；调度状态由程序维护")
        data = self.to_dict()
        if "active_goal" in changes and changes["active_goal"] != self.active_goal:
            data.update(current_intention=None, current_plan=None)
        updated = self.from_dict({**data, **changes}, character=character)
        if updated.active_goal is not None and updated.active_goal not in goals:
            raise ValueError("active_goal 必须来自本人目标")
        updated.select_goal(goals)
        return updated
