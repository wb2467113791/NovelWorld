"""从已提交 talk 维护持续交流；会话只安排机会，不执行世界行为。"""

from dataclasses import asdict, dataclass, field
from uuid import uuid4

from agent.runtime import _text, _tick

MAX_CONVERSATION_TURNS = 12
CONVERSATION_TIMEOUT = 8
RECENT_CONVERSATION_MESSAGES = 6


class DecisionResult(str):
    """保留原文字结果接口，只携带本轮模型的继续/结束意愿。"""

    def __new__(cls, text: str, continue_conversation: bool | None = None):
        result = super().__new__(cls, text)
        result.continue_conversation = continue_conversation
        return result


@dataclass
class ConversationMessage:
    speaker: str
    content: str
    tick: int
    event_id: str


@dataclass
class ConversationSession:
    id: str
    participants: list[str]
    location: str
    started_tick: int
    last_activity_tick: int
    next_speaker: str
    status: str = "active"
    messages: list[ConversationMessage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def sessions() -> list[ConversationSession]:
    from world.state import WORLD_STATE
    return WORLD_STATE.setdefault("active_conversations", [])


def for_participant(name: str) -> ConversationSession | None:
    return next((session for session in sessions() if session.status == "active" and name in session.participants), None)


def end(session: ConversationSession) -> None:
    session.status = "ended"
    sessions()[:] = [current for current in sessions() if current.status == "active"]


def expire(current_tick: int) -> None:
    from world.state import WORLD_STATE
    for session in list(sessions()):
        if session.status != "active" or len(session.messages) >= MAX_CONVERSATION_TURNS or (
            current_tick - session.last_activity_tick >= CONVERSATION_TIMEOUT
        ) or any(name not in WORLD_STATE["characters"] or
                 WORLD_STATE["characters"][name].location != session.location or
                 WORLD_STATE["characters"][name].status == "unconscious"
                 for name in session.participants):
            end(session)


def accept_talk(event: dict, current_tick: int) -> bool:
    """仅消费已提交事件；返回是否由 Conversation 负责 listener 的续轮。"""
    from world.state import WORLD_STATE
    if event["type"] != "talk":
        return False
    actor, target = event["actor"], event["target"]
    names = [actor, target]
    if actor == target or any(name not in WORLD_STATE["characters"] for name in names):
        return False
    if any(WORLD_STATE["characters"][name].location != event["location"] or
           WORLD_STATE["characters"][name].status == "unconscious" for name in names):
        return False
    if any(name not in event.get("perceived_by", names) for name in names):
        return False
    content = event["payload"].get("message")
    if not isinstance(content, str) or not content.strip():
        return False
    if not any(committed == event for committed in WORLD_STATE["events"]):
        raise ValueError("Conversation 只能接收已提交 talk event")
    for session in sessions():
        if any(message.event_id == event["id"] for message in session.messages):
            return True
    session = for_participant(actor)
    if session is None or set(session.participants) != set(names):
        # 新的真实谈话取代冲突会话，角色不会同时占用两个会话。
        for name in names:
            previous = for_participant(name)
            if previous is not None:
                end(previous)
        session = ConversationSession(uuid4().hex, names, event["location"], current_tick, current_tick, target)
        sessions().append(session)
    session.messages.append(ConversationMessage(actor, content, current_tick, event["id"]))
    session.last_activity_tick = current_tick
    session.next_speaker = target
    if len(session.messages) >= MAX_CONVERSATION_TURNS:
        end(session)
    return True


def context_for(name: str) -> dict | None:
    session = for_participant(name)
    if session is None:
        return None
    return {
        "partner": next(participant for participant in session.participants if participant != name),
        "your_turn": session.next_speaker == name,
        "messages": [{"speaker": message.speaker, "content": message.content, "tick": message.tick}
                     for message in session.messages[-RECENT_CONVERSATION_MESSAGES:]],
    }


def restore_sessions(raw: list, characters: dict, events: list) -> list[ConversationSession]:
    """先验证完整运行状态，再恢复 active；旧快照默认空列表。"""
    if not isinstance(raw, list):
        raise ValueError("Conversation 必须是列表")
    result, occupied, ids, message_ids = [], set(), set(), set()
    committed = {event["id"]: event for event in events}
    positions = {event["id"]: index for index, event in enumerate(events)}
    for data in raw:
        try:
            session = ConversationSession(**{**data, "messages": [ConversationMessage(**item) for item in data["messages"]]})
        except (TypeError, KeyError) as error:
            raise ValueError("Conversation 字段无效") from error
        for name in ("id", "location", "next_speaker"):
            _text(getattr(session, name), name, nullable=False)
        if not isinstance(session.participants, list) or len(session.participants) != 2 or any(
            not isinstance(name, str) or name not in characters for name in session.participants
        ) or len(set(session.participants)) != 2 or session.next_speaker not in session.participants:
            raise ValueError("Conversation participants 无效")
        if not isinstance(session.status, str) or session.status not in {"active", "ended"} or session.id in ids:
            raise ValueError("Conversation status / ID 无效")
        ids.add(session.id)
        _tick(session.started_tick, "started_tick", nullable=False)
        _tick(session.last_activity_tick, "last_activity_tick", nullable=False)
        if not 1 <= len(session.messages) <= MAX_CONVERSATION_TURNS:
            raise ValueError("Conversation messages 数量无效")
        previous_tick = session.started_tick
        previous_position = -1
        for message in session.messages:
            _text(message.speaker, "message speaker", nullable=False)
            _text(message.content, "message content", nullable=False)
            _text(message.event_id, "message event_id", nullable=False)
            _tick(message.tick, "message tick", nullable=False)
            event = committed.get(message.event_id)
            if message.event_id in message_ids or not event or event["type"] != "talk" or (
                event["actor"] != message.speaker or event["target"] not in session.participants or
                set((event["actor"], event["target"])) != set(session.participants) or
                event["location"] != session.location or event["payload"].get("message") != message.content or
                any(name not in event.get("perceived_by", session.participants) for name in session.participants)
            ) or message.tick < previous_tick or positions[message.event_id] <= previous_position:
                raise ValueError("Conversation message 必须匹配真实 talk event 和顺序")
            message_ids.add(message.event_id)
            previous_tick = message.tick
            previous_position = positions[message.event_id]
        if session.started_tick != session.messages[0].tick or session.last_activity_tick != previous_tick or (
            session.next_speaker != committed[session.messages[-1].event_id]["target"]
        ):
            raise ValueError("Conversation 时间或轮次无效")
        if session.status == "active":
            if occupied.intersection(session.participants):
                raise ValueError("角色不能同时参与多个 active Conversation")
            occupied.update(session.participants)
            result.append(session)
    return result
