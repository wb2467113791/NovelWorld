"""运行 NovelWorld 的多角色 World Tick。"""

from collections.abc import Callable
import argparse
from threading import Event, Thread
from typing import Any
from pathlib import Path

from agent.graph import build_agent_loop_graph
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.model import Character
from world.state import WORLD_STATE
from world.persistence import DEFAULT_SAVE_PATH, load_world, save_world
from retrieval.chroma_index import ChromaIndex


def make_graph_decide_action(
    request_model: Callable[[list[dict[str, Any]], bool], Any],
    index: ChromaIndex | None = None,
) -> Callable[[Character], str]:
    """把单 NPC Graph 适配为 World Tick 使用的决策函数。"""
    graph = build_agent_loop_graph(request_model)

    def decide_npc_action(character: Character) -> str:
        result = graph.invoke(create_initial_agent_state(character, index=index))
        answer = result["final_answer"]
        if answer is None:
            raise RuntimeError("NPC Graph 未返回最终回答")
        return answer

    return decide_npc_action


def print_next_tick(
    scheduler: WorldTickScheduler,
    decide_action: Callable[[Character], str],
    tick_number: int,
) -> dict[str, str]:
    """执行一轮，并展示这一轮实际新增的事件。"""
    event_count_before = len(WORLD_STATE["events"])
    memory_ids_before = {
        name: {entry.id for entry in character.memory.recent_entries()}
        for name, character in WORLD_STATE["characters"].items()
    }
    result = scheduler.run_tick(decide_action)
    new_events = WORLD_STATE["events"][event_count_before:]
    print(f"[Tick {tick_number} | {result['time']}] {result['character']}")
    for event in new_events:
        print(f"{event['timestamp']} {event['description']}")
    if any(event["type"] != "narration" for event in new_events):
        reason = next(
            (
                line.partition("：")[2].strip()
                for line in result["action_result"].splitlines()
                if line.strip().startswith("原因：")
            ),
            "",
        )
        if reason:
            print(f"模型解释：{reason}")
    for name, character in WORLD_STATE["characters"].items():
        for entry in character.memory.recent_entries():
            if entry.id not in memory_ids_before[name] and entry.importance >= 4:
                print(f"重要记忆（{name}）：{entry.content}")
    return result


def run_world(
    count: int,
    decide_action: Callable[[Character], str],
) -> list[dict[str, str]]:
    """连续运行 World Tick，并打印实际发生的事件时间线。"""
    if count < 1:
        raise ValueError("Tick 次数必须至少为 1")

    scheduler = WorldTickScheduler()
    return [
        print_next_tick(scheduler, decide_action, tick_number)
        for tick_number in range(1, count + 1)
    ]


class WorldSession:
    """保持调度顺序，并允许在连续运行期间请求暂停。"""

    def __init__(self, decide_action: Callable[[Character], str], *,
                 save_path: Path | None = None, index: ChromaIndex | None = None,
                 scheduler_state: dict | None = None, director=None,
                 event_driven: bool = False) -> None:
        self.decide_action = decide_action
        self.scheduler = WorldTickScheduler(director=director, event_driven=event_driven)
        if scheduler_state is not None:
            self.scheduler.restore(scheduler_state)
        self.completed_ticks = self.scheduler.snapshot()["tick_count"]
        self.save_path = save_path
        self.index = index
        self._pause_requested = Event()
        self._worker: Thread | None = None

    def next_tick(self) -> dict[str, str]:
        if self.is_running:
            raise RuntimeError("连续运行中，请先输入 pause")
        return self._step()

    def _step(self) -> dict[str, str]:
        try:
            result = print_next_tick(
                self.scheduler, self.decide_action, self.completed_ticks + 1
            )
            self.completed_ticks += 1
            return result
        finally:
            from tools.remote_world import active_backend
            backend = active_backend()
            if backend is not None:
                backend.save_agent_state(self.scheduler.snapshot())
            if self.save_path is not None:
                save_world(self.save_path, scheduler_state=self.scheduler.snapshot())
            if self.index is not None:
                self.index.sync_world(WORLD_STATE["characters"])

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def run_ten(self) -> None:
        if self.is_running:
            raise RuntimeError("已有连续运行任务，请先输入 pause")
        self._pause_requested.clear()
        self._worker = Thread(target=self._run_batch, daemon=False)
        print("已启动连续运行，最多执行 10 个 Tick；输入 pause 可在当前 Tick 后停止。")
        self._worker.start()

    def _run_batch(self) -> None:
        completed_before = self.completed_ticks
        try:
            for _ in range(10):
                if self._pause_requested.is_set():
                    break
                self._step()
        except Exception as exc:
            print(f"连续运行中断：{exc}")
        finally:
            completed = self.completed_ticks - completed_before
            print(f"连续运行已停止，本次完成 {completed} / 10 个 Tick。")

    def pause(self) -> None:
        self._pause_requested.set()
        if self.is_running:
            print("已请求暂停；当前 Tick 完成后停止。")
        else:
            print("世界已暂停。")

    def wait(self) -> None:
        if self._worker is not None:
            self._worker.join()


def main() -> None:
    """使用真实模型运行可暂停的 World Tick 命令行。"""
    # 延迟导入：普通单元测试不需要安装或调用模型 SDK。
    from llm_client import request_npc_graph_response

    parser = argparse.ArgumentParser(description="NovelWorld 世界 Tick")
    parser.add_argument("--v2", action="store_true", help="通过 MCP 使用 Java 世界服务")
    args = parser.parse_args()

    scheduler_state = load_world(DEFAULT_SAVE_PATH) if DEFAULT_SAVE_PATH.exists() else None
    if args.v2:
        from tools.remote_world import RemoteWorld, use_backend
        from world.persistence import restore_snapshot, snapshot_world
        backend = RemoteWorld(WORLD_STATE["world_id"])
        scheduler_state = restore_snapshot(backend.open(snapshot_world(scheduler_state=scheduler_state)))
        from world.state import reconcile_event_memories
        if reconcile_event_memories():
            backend.save_agent_state(scheduler_state)
        use_backend(backend)
    index = ChromaIndex(WORLD_STATE["world_id"])
    index.sync_world(WORLD_STATE["characters"])
    if not DEFAULT_SAVE_PATH.exists():
        save_world(DEFAULT_SAVE_PATH)
    session = WorldSession(
        make_graph_decide_action(request_npc_graph_response, index),
        save_path=DEFAULT_SAVE_PATH, index=index, scheduler_state=scheduler_state,
    )
    print(f"世界 ID：{WORLD_STATE['world_id']}；存档：{DEFAULT_SAVE_PATH}")
    print("命令：next（下一轮）、run 10（连续十轮）、pause（暂停）、quit（退出）。")
    print("每轮会调用真实模型，可能产生多次 API 请求和费用。")
    try:
        while True:
            command = input("World > ").strip().lower()
            if command == "next":
                try:
                    session.next_tick()
                except RuntimeError as exc:
                    print(exc)
            elif command == "run 10":
                try:
                    session.run_ten()
                except RuntimeError as exc:
                    print(exc)
            elif command == "pause":
                session.pause()
                session.wait()
                print(f"已暂停，当前共完成 {session.completed_ticks} 个 Tick。")
            elif command == "quit":
                break
            else:
                print("未知命令；请输入 next、run 10、pause 或 quit。")
    except EOFError:
        pass
    finally:
        session.pause()
        session.wait()


if __name__ == "__main__":
    main()
