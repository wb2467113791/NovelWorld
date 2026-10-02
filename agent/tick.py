"""推进共同时间，然后给至多两名NPC一次决策机会；没有Director或事件连锁深度。"""


def opportunities(world, excluded=()):
    candidates = []
    now = world["minute"]
    for order, (name, person) in enumerate(world["characters"].items()):
        if person["actor_type"] != "npc" or name in excluded:
            continue
        mind = person["mind"]
        invitation = any(i["to"] == name for i in world["invitations"])
        session = next((s for s in world["conversations"] if name in s["participants"]), None)
        if session is not None and session["next_speaker"] != name:
            continue
        speaking = session is not None
        if person["activity"] is not None and not invitation:
            continue
        due_plan = any(p["at"] <= now for p in mind.get("plan", []))
        if not invitation and not speaking and now < mind.get("next_decision", 0) and not due_plan:
            continue
        last = mind.get("last_decision", 0)
        neglected = now - last >= 20
        # 久未获得机会的可行动角色先于会话；其余优先处理邀请和轮次。
        candidates.append((0 if neglected else 1, 0 if invitation or speaking else 1, last, order, name))
    return [entry[-1] for entry in sorted(candidates)]


class WorldSession:
    def __init__(self, backend, graph):
        self.backend = backend
        self.graph = graph

    def next_tick(self):
        self.backend.load()
        self.backend.advance()
        handled = []
        decisions = []
        for _ in range(2):
            available = opportunities(self.backend.snapshot, handled)
            if not available:
                break
            name = available[0]
            decisions.append(self.graph.invoke({"name": name})["result"])
            handled.append(name)
        return decisions
