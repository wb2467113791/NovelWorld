"""以可解释的规则检测叙事停滞，并只向世界注入环境事件。"""

from world.state import WORLD_STATE, record_event


DIRECTOR_COOLDOWN = 6
DEFAULT_OBSERVATIONS = {
    "stagnation": "一张匿名纸条提到失踪案当晚的客栈后门；内容尚待核实。",
    "participation": "有人提及近期去向不明的货箱；传闻尚待核实。",
    "conflict": "县衙与商会互相质疑的告示被贴出；双方说法尚待核实。",
}


class Director:
    def __init__(self, propose_event=None) -> None:
        self.propose_event = propose_event
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
            return "stagnation", "晚风客栈" if "晚风客栈" in WORLD_STATE["locations"] else WORLD_STATE["locations"][0]

        if tick_count >= 6:
            active = {event["actor"] for event in recent if event["type"] not in {"narration"}}
            quiet = [name for name in WORLD_STATE["characters"] if name not in active]
            if quiet:
                return "participation", WORLD_STATE["characters"][quiet[0]].location

        if tick_count >= 6 and not any(event["type"] in {"talk", "relationship"} for event in recent):
            return "conflict", "青石街" if "青石街" in WORLD_STATE["locations"] else WORLD_STATE["locations"][0]
        return None

    def maybe_inject(self, tick_count: int) -> dict | None:
        selected = self.choose_event(tick_count)
        if selected is None:
            return None
        category, location = selected
        observation = DEFAULT_OBSERVATIONS[category]
        if self.propose_event is not None:
            try:
                proposed = self.propose_event(category, location)
                if isinstance(proposed, str) and proposed.strip():
                    observation = proposed.strip()[:1000]
            except Exception as error:
                print(f"Director 模型请求失败，改用固定环境线索：{error}")
        from tools.remote_world import active_backend
        backend = active_backend()
        if backend is not None:
            event = backend.introduce_event(category, location, tick_count,
                                            observation if self.propose_event is not None else None)
        else:
            object_name = f"新线索{len(WORLD_STATE['events']) + 1}"
            WORLD_STATE["inspectable_objects"].setdefault(location, {})[object_name] = observation
            event = record_event(
                "director", "世界", f"{location}出现了可调查的{object_name}。{observation}",
                location=location,
                payload={"category": category, "object_name": object_name,
                         "observation": observation, "tick_count": tick_count},
            )
        self.last_event_tick = tick_count
        return event
