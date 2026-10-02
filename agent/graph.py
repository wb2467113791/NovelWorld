"""可读的LangGraph：观察→回忆→决策→Java提交→记录；规则失败最多改选一次。"""

from typing import TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from characters.prompt import build_prompt
from memory.stream import observe, add_reflection


class TurnState(TypedDict, total=False):
    name: str
    world: dict
    mind: dict
    memories: list
    reflection_due: bool
    recalled: list
    lore: list
    proposal: dict
    error: str | None
    attempts: int
    result: dict


def validate_proposal(value, world, name):
    fields = {"action", "arguments", "reason", "goal", "intention", "plan", "reflection", "relationship_notes", "next_review_minutes"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("模型回复字段不完整")
    for key in ("reason", "goal", "intention"):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 600:
            raise ValueError(f"{key}需要简短非空文字")
    if not isinstance(value["action"], str) or not isinstance(value["arguments"], dict):
        raise ValueError("行动名或参数无效")
    gap = value["next_review_minutes"]
    if type(gap) is not int or not 5 <= gap <= 30:
        raise ValueError("思考间隔必须是5到30分钟")
    plans = value["plan"]
    if not isinstance(plans, list) or len(plans) > 6:
        raise ValueError("最多6条粗粒度计划")
    for p in plans:
        if not isinstance(p, dict) or set(p) != {"at", "location", "purpose"} or p["location"] not in world["locations"]:
            raise ValueError("计划地点或字段无效")
        if type(p["at"]) is not int or not 0 <= p["at"] <= world["minute"] + 1440:
            raise ValueError("计划时间应在当前可规划的一天范围内")
        if not isinstance(p["purpose"], str) or not p["purpose"].strip() or len(p["purpose"]) > 250:
            raise ValueError("计划说明无效")
    notes = value["relationship_notes"]
    if not isinstance(notes, dict):
        raise ValueError("关系印象必须是对象")
    for target, impression in notes.items():
        if target == name or target not in world["characters"] or not isinstance(impression, str) or len(impression) > 500:
            raise ValueError("关系印象无效")
        if not any(e["type"] in {"talk", "invitation", "invitation_declined", "conversation_started"}
                   and name in e["perceived_by"] and {name, target} <= {e["actor"], e["target"]} for e in world["events"]):
            raise ValueError("没有与此人的真实交流，不能更新关系印象")
    reflection = value["reflection"]
    if reflection is not None and (not isinstance(reflection, dict) or set(reflection) != {"content", "source_event_ids"}
                                   or not isinstance(reflection["content"], str) or not 1 <= len(reflection["content"]) <= 600
                                   or not isinstance(reflection["source_event_ids"], list)
                                   or any(not isinstance(s, str) for s in reflection["source_event_ids"])):
        raise ValueError("反思格式无效")
    return value


def build_graph(backend, index, request_model, progress=lambda *_: None):
    def perception(state):
        progress(state["name"], "观察现场")
        world = backend.load()
        mind, memories, due = observe(world, state["name"])
        return {"world": world, "mind": mind, "memories": memories, "reflection_due": due, "attempts": 0, "error": None}

    def recall(state):
        progress(state["name"], "检索记忆")
        person = state["world"]["characters"][state["name"]]
        query = " ".join([state["mind"]["goal"] or next(iter(person["goals"]), "日常生活"), state["mind"]["intention"], person["location"]])
        recalled, lore = index.recall(state["world"], state["name"], state["memories"], query)
        return {"recalled": recalled, "lore": lore}

    def decide(state):
        progress(state["name"], "考虑下一步")
        prompt = build_prompt(state["world"], state["name"], state["mind"], state["memories"],
                              state["recalled"], state["lore"], state["reflection_due"], state["error"])
        try:
            proposal = validate_proposal(request_model(prompt), state["world"], state["name"])
            return {"proposal": proposal, "error": None, "attempts": state["attempts"] + 1}
        except ValueError as error:
            if state["attempts"] >= 1:
                raise
            return {"error": str(error), "attempts": state["attempts"] + 1}

    def act(state):
        progress(state["name"], "提交世界行动")
        p = state["proposal"]
        mind = dict(state["mind"]); memories = list(state["memories"])
        try:
            if p["reflection"] is not None:
                if not state["reflection_due"]:
                    raise ValueError("还没有足够新经历，本轮无需反思")
                add_reflection(memories, p["reflection"]["content"], p["reflection"]["source_event_ids"], state["world"]["minute"])
                mind["reflection"] = p["reflection"]["content"]
                mind["reflection_cursor"] = len(memories)
            mind.update(goal=p["goal"], intention=p["intention"], plan=p["plan"],
                        relationship_notes={**mind["relationship_notes"], **p["relationship_notes"]},
                        last_decision=state["world"]["minute"], next_decision=state["world"]["minute"] + p["next_review_minutes"])
            result = backend.commit(state["name"], uuid4().hex, {
                "action": p["action"], "arguments": p["arguments"], "reason": p["reason"], "mind": mind, "memories": memories})
            return {"world": result, "error": None}
        except ValueError as error:
            if state["attempts"] >= 2:
                raise RuntimeError(f"{state['name']}连续两次提议未通过：{error}") from error
            return {"world": backend.load(), "error": str(error)}

    def remember(state):
        progress(state["name"], "记录本轮经历")
        return {"result": state["world"]["decisions"][-1]}

    builder = StateGraph(TurnState)
    for name, node in (("observe", perception), ("recall", recall), ("decide", decide), ("act", act), ("remember", remember)):
        builder.add_node(name, node)
    builder.add_edge(START, "observe"); builder.add_edge("observe", "recall"); builder.add_edge("recall", "decide")
    builder.add_conditional_edges("decide", lambda s: "decide" if s["error"] else "act")
    builder.add_conditional_edges("act", lambda s: "decide" if s["error"] else "remember")
    builder.add_edge("remember", END)
    return builder.compile()
