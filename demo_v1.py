"""可重复、无需 API 的 V1 二十轮演示。"""

import json
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from typing import Iterator

from agent.graph import build_agent_loop_graph
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.presets import CHARACTERS
from run_world import print_next_tick
from world.state import WORLD_STATE


# 每项是一次固定的「模型选择」。工具仍由 Agent Graph 交给 Python 执行。
DEMO_ACTIONS = (
    ("林默", "inspect", {"character": "林默"}, "先核对县衙案卷。"),
    ("苏晚", "inspect", {"character": "苏晚"}, "检查客栈是否留下线索。"),
    ("赵无极", "move_character", {"character": "赵无极", "location": "晚风客栈"}, "去客栈掌握动向。"),
    ("林默", "move_character", {"character": "林默", "location": "晚风客栈"}, "案卷线索指向客栈。"),
    ("苏晚", "talk", {"speaker": "苏晚", "listener": "林默", "message": "昨晚后门确实有人经过，但我还不能确定是谁。"}, "谨慎提供可公开的线索。"),
    ("赵无极", "talk", {"speaker": "赵无极", "listener": "苏晚", "message": "商会不希望这件事闹大。"}, "试图压住调查。"),
    ("林默", "talk", {"speaker": "林默", "listener": "苏晚", "message": "我需要核对案发当晚的客栈记录。"}, "继续追查失踪案。"),
    ("苏晚", "update_relationship", {"character": "苏晚", "target": "林默", "change": 2}, "林默依证据问话，稍增信任。"),
    ("赵无极", "talk", {"speaker": "赵无极", "listener": "林默", "message": "调查商会要讲证据。"}, "阻止调查深入。"),
    ("林默", "update_relationship", {"character": "林默", "target": "赵无极", "change": -3}, "施压使怀疑加深。"),
    ("苏晚", "give_item", {"giver": "苏晚", "receiver": "林默", "item": "私人账本"}, "把账本交给捕快核查，避免线索被销毁。"),
    ("赵无极", "update_relationship", {"character": "赵无极", "target": "苏晚", "change": -4}, "不满账本被交出。"),
    ("林默", "inspect", {"character": "林默", "object_name": "住客登记簿"}, "查看可核实的住客登记资料。"),
    ("苏晚", "talk", {"speaker": "苏晚", "listener": "林默", "message": "请先查清账本上的货物去向。"}, "引导调查关注交易记录。"),
    ("赵无极", "move_character", {"character": "赵无极", "location": "青石街"}, "回商会处理交易风险。"),
    ("林默", "move_character", {"character": "林默", "location": "县衙"}, "回县衙比对账本与卷宗。"),
    ("苏晚", "inspect", {"character": "苏晚", "object_name": "后门"}, "检查后门当前可见的情况。"),
    ("赵无极", "inspect", {"character": "赵无极"}, "查看青石街的动向。"),
    ("林默", "update_relationship", {"character": "林默", "target": "苏晚", "change": 1}, "苏晚交出账本后稍增信任。"),
    ("苏晚", "update_relationship", {"character": "苏晚", "target": "赵无极", "change": -3}, "商会施压后更加警惕。"),
)


@contextmanager
def fresh_demo_world() -> Iterator[None]:
    """从预设创建独立世界，演示结束后恢复调用者原有状态。"""
    original = WORLD_STATE.copy()
    try:
        WORLD_STATE["time"] = "08:00"
        WORLD_STATE["characters"] = deepcopy(CHARACTERS)
        WORLD_STATE["events"] = []
        yield
    finally:
        WORLD_STATE.clear()
        WORLD_STATE.update(original)


def run_demo(index_factory=None) -> dict:
    """通过真实 Graph 和工具执行 20 个固定 Tick，返回最终摘要。"""
    with fresh_demo_world():
        index = index_factory(WORLD_STATE["world_id"]) if index_factory else None
        scheduler = WorldTickScheduler()
        for number, (actor, tool, arguments, reason) in enumerate(DEMO_ACTIONS, 1):
            call_id = f"demo-{number}"
            def request_model(conversation, allow_tools):
                if allow_tools and len(conversation) == 1:
                    return SimpleNamespace(
                        output=[SimpleNamespace(
                            type="function_call", name=tool,
                            arguments=json.dumps(arguments, ensure_ascii=False),
                            call_id=call_id,
                        )],
                        output_text="",
                    )
                return SimpleNamespace(output=[], output_text=f"行动完成。\n原因：{reason}")

            graph = build_agent_loop_graph(request_model)
            def decide_action(character):
                if character.name != actor:
                    raise AssertionError(f"Tick {number} 角色顺序不符：{character.name} != {actor}")
                return graph.invoke(create_initial_agent_state(character, index=index))["final_answer"]

            print(f"预设 Tool Call: {tool}({json.dumps(arguments, ensure_ascii=False)})")
            print_next_tick(scheduler, decide_action, number)
            if index is not None:
                index.sync_world(WORLD_STATE["characters"])

        events = WORLD_STATE["events"]
        if len(events) != 20 or any(event["type"] == "narration" for event in events):
            raise AssertionError("演示未产生 20 个真实工具事件")
        characters = WORLD_STATE["characters"]
        summary = {
            "ticks": len(DEMO_ACTIONS),
            "end_time": WORLD_STATE["time"],
            "events": dict(Counter(event["type"] for event in events)),
            "locations": {name: character.location for name, character in characters.items()},
            "lin_mo_items": list(characters["林默"].items),
            "su_wan_items": list(characters["苏晚"].items),
            "relationships": {
                "苏晚→林默": characters["苏晚"].relationships["林默"],
                "苏晚→赵无极": characters["苏晚"].relationships["赵无极"],
                "林默→赵无极": characters["林默"].relationships["赵无极"],
                "赵无极→苏晚": characters["赵无极"].relationships["苏晚"],
            },
        }
        if index is not None:
            summary["chroma_memory_records"] = index.memories.count()
            summary["chroma_lore_records"] = index.lore.count()
        print("\n=== 最终世界状态 ===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary


if __name__ == "__main__":
    run_demo()
