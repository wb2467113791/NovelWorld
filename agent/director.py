"""以可解释的规则检测叙事停滞，并只向世界注入环境事件。"""

from collections.abc import Callable

from world.state import WORLD_STATE
from characters.model import is_npc


DIRECTOR_COOLDOWN = 6
DEFAULT_OBSERVATIONS = {
    "stagnation": "公共区域传来日常安排可能调整的议论，内容尚待核实。",
    "participation": "附近传来寻求日常事务协助的议论，具体情况尚不清楚。",
    "conflict": "附近有人对公共空间使用安排表达不同意见，尚未形成一致意见。",
}


class Director:
    def __init__(self, propose_event: Callable[[str, str], str | dict]) -> None:
        self.propose_event = propose_event
        prior = next((event for event in reversed(WORLD_STATE["events"])
                      if event["type"] == "director"), None)
        self.last_event_tick = prior["payload"].get("tick_count", -DIRECTOR_COOLDOWN) if prior else -DIRECTOR_COOLDOWN

    @staticmethod
    def occupied_location(preferred: str | None = None) -> str:
        characters = [actor for actor in WORLD_STATE["characters"].values() if is_npc(actor)]
        available = next((character for character in characters
                          if character.location == preferred and character.status != "unconscious"), None)
        if available is None:
            available = next((character for character in characters if character.status != "unconscious"), characters[0])
        return available.location

    def choose_event(self, tick_count: int, idle: bool = False) -> tuple[str, str] | None:
        if tick_count - self.last_event_tick < DIRECTOR_COOLDOWN:
            return None
        if idle:
            return "stagnation", self.occupied_location()
        if tick_count < 3:
            return None
        # legacy history only：narration 不计行动，relationship 仍可用于旧历史过滤。
        history = [event for event in WORLD_STATE["events"] if event["type"] not in {"director", "narration"}]
        recent = history[-6:]
        if len(history) >= 3 and len({event["description"] for event in history[-3:]}) == 1:
            return "stagnation", self.occupied_location()

        if tick_count >= 6:
            active = {event["actor"] for event in recent}
            quiet = [name for name, actor in WORLD_STATE["characters"].items() if is_npc(actor) and name not in active]
            if quiet:
                return "participation", WORLD_STATE["characters"][quiet[0]].location

        if tick_count >= 6 and not any(event["type"] in {"talk", "relationship"} for event in recent):
            return "conflict", self.occupied_location()
        return None

    def maybe_inject(self, tick_count: int, idle: bool = False) -> dict | None:
        selected = self.choose_event(tick_count, idle)
        if selected is None:
            return None
        category, location = selected
        observation = DEFAULT_OBSERVATIONS[category]
        form = "ambient"
        try:
            proposed = self.propose_event(category, location)
            if isinstance(proposed, str) and proposed.strip():
                observation = proposed.strip()[:1000]
            elif (isinstance(proposed, dict) and proposed.get("form") in {"ambient", "clue"}
                  and isinstance(proposed.get("observation"), str) and proposed["observation"].strip()):
                observation = proposed["observation"].strip()[:1000]
                form = proposed["form"]
        except Exception as error:
            print(f"Director 模型请求失败，改用环境事件：{error}")
        from tools.remote_world import active_backend
        backend = active_backend()
        if backend is None:
            raise RuntimeError("Director 需要已连接的世界服务")
        # 旧回调的普通文本默认环境事件；只有明确物证提议才新增对象。
        event = (backend.introduce_event(category, location, tick_count, observation, form=form)
                 if form == "clue" else backend.introduce_event(category, location, tick_count, observation))
        self.last_event_tick = tick_count
        return event
