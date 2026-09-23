"""无模型费用的 V3 Director / Skills / MCP 固定演示。"""

import json

from agent.director import Director
from agent.tick import WorldTickScheduler
from tools.remote_world import RemoteWorld, use_backend
from world.persistence import restore_snapshot, snapshot_world, start_new_world
from world.state import WORLD_STATE


def main() -> None:
    start_new_world()
    backend = RemoteWorld(WORLD_STATE["world_id"])
    restore_snapshot(backend.open(snapshot_world()))
    use_backend(backend)
    try:
        scheduler = WorldTickScheduler(director=Director())
        for _ in range(3):
            scheduler.run_tick(lambda character: f"{character.name}暂时观察周围")
            backend.save_agent_state(scheduler.snapshot())
        director_events = [event for event in WORLD_STATE["events"] if event["type"] == "director"]
        assert len(director_events) == 1
        event = director_events[0]
        assert event["actor"] == "世界"
        assert event["payload"]["object_name"] in WORLD_STATE["inspectable_objects"][event["location"]]
        assert any(entry.source_event_id == event["id"] for entry in WORLD_STATE["characters"]["苏晚"].memory.recent_entries())
        assert all(entry.source_event_id != event["id"] for entry in WORLD_STATE["characters"]["林默"].memory.recent_entries())
        persisted = json.loads(backend._call("get_world", {"worldId": backend.world_id}))
        assert [item["type"] for item in persisted["events"][-2:]] == ["narration", "director"]
        print(f"V3 验收通过：{WORLD_STATE['time']}，Director 新增 {event['payload']['object_name']}，仅现场角色感知。")
    finally:
        use_backend(None)


if __name__ == "__main__":
    main()
