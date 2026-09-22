"""运行 NovelWorld 的多角色 World Tick。"""

from collections.abc import Callable
from threading import Event, Thread
from typing import Any

from agent.graph import build_agent_loop_graph
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.model import Character
from world.state import WORLD_STATE


def make_graph_decide_action(
    request_model: Callable[[list[dict[str, Any]], bool], Any],
) -> Callable[[Character], str]:
    """把单 NPC Graph 适配为 World Tick 使用的决策函数。"""
    graph = build_agent_loop_graph(request_model)

    def decide_npc_action(character: Character) -> str:
        result = graph.invoke(create_initial_agent_state(character))
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
        name: {id(entry) for entry in character.memory.recent_entries()}
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
            if id(entry) not in memory_ids_before[name] and entry.importance >= 4:
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

    def __init__(self, decide_action: Callable[[Character], str]) -> None:
        self.decide_action = decide_action
        self.scheduler = WorldTickScheduler()
        self.completed_ticks = 0
        self._pause_requested = Event()
        self._worker: Thread | None = None

    def next_tick(self) -> dict[str, str]:
        if self.is_running:
            raise RuntimeError("连续运行中，请先输入 pause")
        return self._step()

    def _step(self) -> dict[str, str]:
        result = print_next_tick(
            self.scheduler, self.decide_action, self.completed_ticks + 1
        )
        self.completed_ticks += 1
        return result

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

    session = WorldSession(make_graph_decide_action(request_npc_graph_response))
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
