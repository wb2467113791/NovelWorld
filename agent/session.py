"""Web Runtime 中一次 NPC 决策与世界 Tick 的会话封装。"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.graph import build_agent_loop_graph
from agent.conversation import DecisionResult
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.model import Character
from retrieval.chroma_index import ChromaIndex
from tools.remote_world import active_backend
from world.persistence import save_world
from world.state import WORLD_STATE


def make_graph_decide_action(
    request_model: Callable[[list[dict[str, Any]], bool], Any],
    index: ChromaIndex,
) -> Callable[[Character], str]:
    graph = build_agent_loop_graph(request_model)

    def decide_npc_action(character: Character) -> str:
        result = graph.invoke(create_initial_agent_state(character, index))
        answer = result["final_answer"]
        if answer is None:
            raise RuntimeError("NPC Graph 未返回最终回答")
        return DecisionResult(answer, result.get("continue_conversation"))

    return decide_npc_action


class WorldSession:
    """按事件和 Agenda 调度 NPC，并在每个 Tick 后保存记忆与调度进度。"""

    def __init__(self, decide_action: Callable[[Character], str], *,
                 save_path: Path, index: ChromaIndex,
                 scheduler_state: dict | None = None, director=None) -> None:
        self.decide_action = decide_action
        self.scheduler = WorldTickScheduler(director=director)
        if scheduler_state is not None:
            self.scheduler.restore(scheduler_state)
        self.completed_ticks = self.scheduler.snapshot()["tick_count"]
        self.save_path = save_path
        self.index = index

    def next_tick(self) -> dict[str, str]:
        backend = active_backend()
        if backend is None:
            raise RuntimeError("世界会话需要已连接的世界服务")
        try:
            result = self.scheduler.run_tick(self.decide_action)
            return result
        finally:
            # 时钟已推进但后续 Director 失败时，状态展示仍应与保存的累计 Tick 一致。
            self.completed_ticks = self.scheduler.snapshot()["tick_count"]
            backend.save_agent_state(self.scheduler.snapshot())
            save_world(self.save_path, scheduler_state=self.scheduler.snapshot())
            self.index.sync_world(WORLD_STATE["characters"])
