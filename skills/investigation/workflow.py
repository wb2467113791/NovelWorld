"""根据角色自己的已知事实和已提交行动推进调查任务。"""

from dataclasses import dataclass

from characters.model import Character
from world.state import WORLD_STATE


@dataclass(frozen=True)
class InvestigationStep:
    phase: str
    tool: str
    arguments: dict[str, str]
    reason: str


def completed_step(step: InvestigationStep | None, event: dict, actor: str) -> bool:
    """只用 Java 已提交事件确认建议步骤确实完成。"""
    if step is None or event["actor"] != actor:
        return False
    if step.tool == "move_character":
        return event["type"] == "move" and event["location"] == step.arguments["location"]
    if step.tool == "inspect":
        return event["type"] == "inspect" and (event["payload"].get("object_id") == step.arguments["object_id"] if "object_id" in step.arguments else event["payload"].get("object_name") == step.arguments["object_name"])
    if step.tool == "take":
        return event["type"] == "take" and event["payload"].get("object_id") == step.arguments["object_id"]
    if step.tool == "talk":
        return event["type"] == "talk" and event["target"] == step.arguments["listener"]
    if step.tool == "recover_clue":
        return event["type"] == "recover" and event["payload"].get("object_name") == step.arguments["object_name"]
    if step.tool == "conceal_clue":
        return event["type"] == "conceal" and event["payload"].get("object_name") == step.arguments["object_name"]
    return False


def _is_investigator(character: Character, goal: str) -> bool:
    return "捕快" in character.role or goal.startswith(("调查", "查明", "追查", "寻找线索"))


def next_step(character: Character, goal: str) -> InvestigationStep | None:
    """只读规划；不调用工具，也不修改权威世界状态。"""
    if not _is_investigator(character, goal) or character.energy < 20:
        return None

    location = character.location
    own_events = [event for event in WORLD_STATE["events"] if event["actor"] == character.name]
    from world.objects import visible_objects
    for item in visible_objects(character):
        if item["holder"] is None and not any(fact.location == location and
            (fact.object_id == item["id"] or (fact.object_id is None and fact.object_name == item["name"]))
            for fact in character.semantic_memory.current_facts()):
            return InvestigationStep("核对现场", "inspect", {"character": character.name, "object_id": item["id"]},
                                     f"{location}的{item['name']}尚无本人调查记录")

    # 先询问目前就在现场、且本轮线索更新后尚未询问过的人。
    latest_fact_event_ids = {
        fact.source_event_id for fact in character.semantic_memory.current_facts()
        if fact.location == location
    }
    last_inspection_index = max(
        (index for index, event in enumerate(own_events)
         if event["id"] in latest_fact_event_ids),
        default=-1,
    )
    questioned = {
        event["target"] for event in own_events[last_inspection_index + 1:]
        if event["type"] == "talk" and event["location"] == location
    }
    for name, other in WORLD_STATE["characters"].items():
        if name != character.name and other.location == location and name not in questioned:
            return InvestigationStep(
                "询问在场人", "talk",
                {"speaker": character.name, "listener": name},
                f"{name}在场，且尚未针对当前线索与其交谈",
            )

    # 线索来源仅限角色自己的事实和已感知的事件；新对话可重新指向旧地点。
    event_positions = {event["id"]: index for index, event in enumerate(WORLD_STATE["events"])}
    lead_texts = [(-1, text) for text in character.known_facts]
    lead_texts.extend(
        (event_positions.get(fact.source_event_id, -1), fact.observation)
        for fact in character.semantic_memory.current_facts()
    )
    for memory in character.memory.all_entries():
        event_index = event_positions.get(memory.source_event_id)
        if event_index is None:
            continue
        event = WORLD_STATE["events"][event_index]
        if event["actor"] != character.name and event["type"] in {"talk", "director", "intervention"}:
            lead_texts.append((event_index, memory.content))
    last_visit = {
        destination: max(
            (index for index, event in enumerate(WORLD_STATE["events"])
             if event["actor"] == character.name and event["location"] == destination
             and event["type"] in {"move", "inspect", "talk"}),
            default=-1,
        )
        for destination in WORLD_STATE["locations"]
    }
    for destination in WORLD_STATE["locations"]:
        if destination != location and any(
            destination in text and (last_visit[destination] == -1 or source > last_visit[destination])
            for source, text in lead_texts
        ):
            return InvestigationStep(
                "追踪地点线索", "move_character",
                {"character": character.name, "location": destination},
                f"本人获得的线索提到{destination}，此后尚未到访",
            )
    return None
