"""不用模型费用的 V2 MCP 端到端演示；需先启动 world-service。"""

import json

from tools.remote_world import RemoteWorld, use_backend
from tools.world_tools import execute_tool
from agent.tick import WorldTickScheduler
from world.persistence import restore_snapshot, snapshot_world, start_new_world
from world.state import WORLD_STATE


def main() -> None:
    start_new_world()
    backend = RemoteWorld(WORLD_STATE["world_id"])
    restore_snapshot(backend.open(snapshot_world()))
    use_backend(backend)
    try:
        scheduler = WorldTickScheduler()
        result = scheduler.run_tick(lambda actor: execute_tool(
            "move_character", {"character": actor.name, "location": "晚风客栈"},
            acting_character=actor.name,
        ))["action_result"]
        assert WORLD_STATE["characters"]["林默"].location == "晚风客栈"
        assert WORLD_STATE["characters"]["林默"].memory.recent_entries()
        try:
            execute_tool("give_item", {"giver": "林默", "receiver": "苏晚", "item": "私人账本"}, acting_character="林默")
        except ValueError:
            pass
        else:
            raise AssertionError("未拥有的物品被错误地交付")
        backend.save_agent_state(scheduler.snapshot())
        saved = json.loads(backend._call("get_world", {"worldId": backend.world_id}))
        assert saved["characters"]["林默"]["location"] == "晚风客栈"
        assert saved["characters"]["林默"]["memory"]["entries"]
        assert saved["time"] == "08:05"
        assert len(saved["events"]) == 1
        assert saved["scheduler"]["tick_count"] == 1
        print(result)
        print(f"V2 MCP 验收通过：{saved['world_id']}，时间 {saved['time']}，事件 {len(saved['events'])} 条")
    finally:
        use_backend(None)


if __name__ == "__main__":
    main()
