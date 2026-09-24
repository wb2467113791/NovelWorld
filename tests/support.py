"""为调度与记忆单元测试构造已提交事件。"""

from uuid import uuid4

from world.events import recipients_for_event
from world.state import WORLD_STATE, remember_event


def committed_event(event_type, actor, description, *, target=None, location=None, payload=None):
    event = {
        "id": uuid4().hex,
        "timestamp": WORLD_STATE["time"],
        "type": event_type,
        "actor": actor,
        "target": target,
        "location": location or WORLD_STATE["characters"][actor].location,
        "payload": payload or {},
        "description": description,
    }
    event["perceived_by"] = recipients_for_event(event, WORLD_STATE["characters"])
    WORLD_STATE["events"].append(event)
    remember_event(event)
    return event
