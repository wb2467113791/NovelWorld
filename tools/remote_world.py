"""唯一世界连接：Python 通过 MCP 请求 Spring Boot，不自行结算事实。"""

import asyncio
import json
import os


class RemoteWorld:
    def __init__(self, world_id=None, url=None):
        self.world_id = world_id
        self.url = url or os.getenv("NOVELWORLD_MCP_URL", "http://127.0.0.1:8080/mcp")
        self.snapshot = None

    def _call(self, name, arguments):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async def invoke():
            async with streamable_http_client(self.url) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    content = "".join(block.text for block in result.content if hasattr(block, "text"))
                    return not result.isError, content

        success, content = asyncio.run(invoke())
        # 在MCP异步上下文退出后抛出业务错误，避免TaskGroup把规则拒绝包装成传输异常。
        if not success:
            raise ValueError(content or "Java 世界规则拒绝了请求")
        return json.loads(content)

    def _accept(self, snapshot):
        if snapshot.get("version") != 3:
            raise ValueError("旧世界仅供保留和导出，请创建新版社会沙盒")
        self.world_id = snapshot["world_id"]
        self.snapshot = snapshot
        return snapshot

    def initialize(self):
        return self._accept(self._call("initialize_world", {}))

    def load(self):
        return self._accept(self._call("get_world", {"worldId": self.world_id}))

    def advance(self):
        expected = self.snapshot["tick_count"]
        try:
            return self._accept(self._call("advance_world", {"worldId": self.world_id, "expectedTick": expected}))
        except ValueError:
            raise
        except Exception:
            # 网络返回丢失时只读确认；不会再次推进时钟。
            snapshot = self.load()
            if snapshot["tick_count"] == expected + 1:
                return snapshot
            raise

    def commit(self, actor, request_id, turn):
        try:
            return self._accept(self._call("commit_turn", {
                "worldId": self.world_id, "actor": actor, "requestId": request_id,
                "turnJson": json.dumps(turn, ensure_ascii=False),
            }))
        except ValueError:
            raise
        except Exception:
            # 已提交的轮次不因连接中断重复执行。查询也失败时 Runtime 会暂停。
            snapshot = self.load()
            if any(d["id"] == request_id for d in snapshot["decisions"]):
                return snapshot
            raise

    def join(self, name, location):
        return self._accept(self._call("join_player", {"worldId": self.world_id, "name": name, "location": location}))
