"""以可解释的规则检测叙事停滞，并只向世界注入环境事件。"""

from world.state import WORLD_STATE, record_event


DIRECTOR_COOLDOWN = 6


class Director:
    def __init__(self) -> None:
        prior = next((event for event in reversed(WORLD_STATE["events"])
                      if event["type"] == "director"), None)
        self.last_event_tick = prior["payload"].get("tick_count", -DIRECTOR_COOLDOWN) if prior else -DIRECTOR_COOLDOWN

    def choose_event(self, tick_count: int) -> tuple[str, str] | None:
        if tick_count - self.last_event_tick < DIRECTOR_COOLDOWN or tick_count < 3:
            return None
        history = [event for event in WORLD_STATE["events"] if event["type"] != "director"]
        recent = history[-6:]
        if len(history) >= 3 and (all(event["type"] == "narration" for event in history[-3:])
                                  or len({event["description"] for event in history[-3:]}) == 1):
            return "stagnation", "晚风客栈"

        if tick_count >= 6:
            active = {event["actor"] for event in recent if event["type"] not in {"narration"}}
            quiet = [name for name in WORLD_STATE["characters"] if name not in active]
            if quiet:
                return "participation", WORLD_STATE["characters"][quiet[0]].location

        if tick_count >= 6 and not any(event["type"] in {"talk", "relationship"} for event in recent):
            return "conflict", "青石街"
        return None

    def maybe_inject(self, tick_count: int) -> dict | None:
        selected = self.choose_event(tick_count)
        if selected is None:
            return None
        category, location = selected
        from tools.remote_world import active_backend
        backend = active_backend()
        if backend is not None:
            event = backend.introduce_event(category, location, tick_count)
        else:
            descriptions = {
                "stagnation": "客栈里出现一张匿名纸条，似乎与失踪案有关。",
                "participation": "附近传来一条尚未查证的新线索。",
                "conflict": "商会与县衙的争执引起街上议论。",
            }
            event = record_event("director", "世界", descriptions[category], location=location,
                                 payload={"category": category, "tick_count": tick_count})
        self.last_event_tick = tick_count
        return event
