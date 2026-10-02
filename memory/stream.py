"""角色可见经历的记忆流；转述、直接观察与主观反思保留来源。"""

from copy import deepcopy
from uuid import uuid4


def observe(world, name):
    person = world["characters"][name]
    mind = deepcopy(person.get("mind") or {})
    defaults = {"goal": "", "intention": "", "plan": [], "reflection": "", "relationship_notes": {},
                "last_decision": 0, "next_decision": 0, "event_cursor": 0, "reflection_cursor": 0}
    for key, value in defaults.items():
        mind.setdefault(key, value)
    memories = deepcopy(person["memories"])
    ids = {item["id"] for item in memories}
    for event in world["events"][mind["event_cursor"]:]:
        if name not in event["perceived_by"] or event["id"] in ids:
            continue
        reported = event["type"] in {"talk", "invitation"} and event["actor"] != name
        memories.append({
            "id": event["id"], "kind": "reported" if reported else "observation",
            "content": ("听到的说法（内容未核实）：" if reported else "亲历：") + event["description"],
            "minute": event["minute"], "importance": 4 if event["type"] in {
                "talk", "conversation_ended", "invitation_declined", "conversation_started"} else 2,
            "source_event_ids": [event["id"]],
        })
    mind["event_cursor"] = len(world["events"])
    fresh = [m for m in memories[mind["reflection_cursor"]:] if m["kind"] != "reflection"]
    return mind, memories, len(fresh) >= 5


def add_reflection(memories, content, sources, minute):
    visible = {event_id for m in memories for event_id in m["source_event_ids"]}
    if not sources or not set(sources) <= visible:
        raise ValueError("反思必须引用本人真实经历")
    memories.append({"id": uuid4().hex, "kind": "reflection", "content": "主观反思：" + content,
                     "minute": minute, "importance": 5, "source_event_ids": sources})
