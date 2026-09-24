"""V2 模式：Python 通过 MCP 请求 Java 世界服务执行工具。"""

import asyncio
import json
import os
from typing import Any


_active_backend = None


def active_backend():
    return _active_backend


def use_backend(backend) -> None:
    global _active_backend
    _active_backend = backend


class RemoteWorld:
    def __init__(self, world_id: str, url: str | None = None) -> None:
        self.world_id = world_id
        self.url = url or os.environ.get("NOVELWORLD_MCP_URL", "http://127.0.0.1:8080/mcp")

    def _call(self, name: str, arguments: dict[str, Any]) -> str:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async def invoke():
            async with streamable_http_client(self.url) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    if result.isError:
                        message = " ".join(item.text for item in result.content if hasattr(item, "text"))
                        return False, message or f"MCP 工具失败：{name}"
                    return True, "".join(item.text for item in result.content if hasattr(item, "text"))

        success, text = asyncio.run(invoke())
        if not success:
            raise ValueError(text)
        return text

    def open(self, local_snapshot: dict) -> dict:
        """现有世界以服务端为准；首次启动才导入本地存档。"""
        try:
            return json.loads(self._call("get_world", {"worldId": self.world_id}))
        except ValueError as error:
            if "世界不存在" not in str(error):
                raise
            self._call("create_world", {"snapshotJson": json.dumps(local_snapshot, ensure_ascii=False)})
            return json.loads(self._call("get_world", {"worldId": self.world_id}))

    def load(self) -> dict:
        """只读取已存在的世界，切换时不能把本地存档误导入为新世界。"""
        return json.loads(self._call("get_world", {"worldId": self.world_id}))

    def sync_events(self) -> int:
        """只在 Java 出现新事件时刷新状态，供事件调度器读取人为干预。"""
        from world.state import WORLD_STATE

        cursor = len(WORLD_STATE["events"])
        added = 0
        while True:
            page = json.loads(self._call("get_world_events", {
                "worldId": self.world_id, "afterIndex": cursor,
            }))
            events = page["events"]
            added += len(events)
            if not events or len(events) < 100:
                break
            cursor = page["next_cursor"]
        if added:
            self._refresh_business_state()
        return added

    def execute(self, name: str, arguments: dict, acting_character: str | None) -> str:
        from world.state import remember_event

        response = json.loads(self._call("execute_world_tool", {
            "worldId": self.world_id,
            "name": name,
            "argumentsJson": json.dumps(arguments, ensure_ascii=False),
            "actingCharacter": acting_character or arguments.get("character", ""),
        }))
        event = response["event"]
        if event:
            # 服务端已写入业务状态与事件；重新读取后只补 Python 专属的角色记忆。
            self._refresh_business_state()
            remember_event(event)
        return response["output"]

    def _refresh_business_state(self) -> None:
        from world.persistence import restore_snapshot, snapshot_world
        from world.state import WORLD_STATE, reconcile_event_memories
        remote = json.loads(self._call("get_world", {"worldId": self.world_id}))
        if WORLD_STATE.get("world_id") == self.world_id:
            local = snapshot_world()
            for name, character in remote["characters"].items():
                character["memory"] = local["characters"][name]["memory"]
                character["semantic_memory"] = local["characters"][name]["semantic_memory"]
            remote_ids = {event["id"] for event in remote["events"]}
            remote["events"].extend(
                event for event in local["events"]
                if event["id"] not in remote_ids and event["type"] == "narration"
            )
        restore_snapshot(remote)
        reconcile_event_memories()

    def introduce_event(self, category: str, location: str, tick_count: int,
                        observation: str | None = None) -> dict:
        from world.state import WORLD_STATE, remember_event
        arguments = {
            "worldId": self.world_id,
            "category": category,
            "location": location,
            "tickCount": tick_count,
        }
        if observation is not None:
            arguments["observation"] = observation
        event = json.loads(self._call(
            "introduce_narrative_event" if observation is not None else "introduce_world_event",
            arguments,
        ))
        self._refresh_business_state()
        remember_event(event)
        return event

    def advance_time(self, minutes: int) -> str:
        return self._call("advance_world_time", {"worldId": self.world_id, "minutes": minutes})

    def save_agent_state(self, scheduler_state: dict) -> None:
        from world.persistence import snapshot_world
        snapshot = snapshot_world(scheduler_state=scheduler_state)
        payload = {
            "characters": {
                name: {
                    "memory": character["memory"],
                    "semantic_memory": character["semantic_memory"],
                }
                for name, character in snapshot["characters"].items()
            },
            "scheduler": scheduler_state,
            "events": [event for event in snapshot["events"] if event["type"] == "narration"],
        }
        self._call("save_agent_state", {
            "worldId": self.world_id,
            "agentStateJson": json.dumps(payload, ensure_ascii=False),
        })
