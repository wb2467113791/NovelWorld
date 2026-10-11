"""唯一世界连接：Python 通过 MCP 请求 Spring Boot，不自行结算事实。"""

import asyncio
import json
import os
from copy import deepcopy

ACTIONS = frozenset({"move", "invite", "say", "inspect", "start_activity", "stop_activity",
                     "respond_invitation", "leave_conversation", "wait"})
RUNTIME_FIELDS = {"worldId", "actor", "requestId", "expectedRevision", "cognitionJson"}


class RuleRejected(ValueError):
    """仅MCP明确返回的业务拒绝可以触发模型修正。"""


class RemoteWorld:
    def __init__(self, world_id=None, url=None):
        self.world_id = world_id
        self.url = url or os.getenv("NOVELWORLD_MCP_URL", "http://127.0.0.1:8080/mcp")
        self.snapshot = None
        self._tools = None

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
            raise RuntimeError(content or "MCP服务错误，需要确认提交状态")
        try:
            return json.loads(content)
        except (ValueError, TypeError) as error:
            raise RuntimeError("MCP响应无法解析，需要确认提交状态") from error

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

    def discover_tools(self):
        """缓存业务工具Schema；控制/快照工具绝不提供给模型。"""
        if self._tools is None:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async def discover():
                async with streamable_http_client(self.url) as (reader, writer, _):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        found = []
                        cursor = None
                        while True:
                            page = await session.list_tools(cursor=cursor)
                            found.extend(page.tools)
                            cursor = page.nextCursor
                            if not cursor:
                                return found
            self._tools = {tool.name: tool for tool in asyncio.run(discover()) if tool.name in ACTIONS}
            if set(self._tools) != ACTIONS:
                self._tools = None
                raise RuntimeError("Java MCP 缺少独立业务行动工具")
        return self._tools

    def model_tools(self):
        from characters.prompt import cognition_schema
        result = []
        for name, tool in self.discover_tools().items():
            schema = deepcopy(tool.inputSchema)
            if not RUNTIME_FIELDS <= schema.get("properties", {}).keys():
                raise RuntimeError(f"{name} 缺少 Runtime 提交字段")
            for key in RUNTIME_FIELDS:
                schema["properties"].pop(key)
            schema["required"] = [key for key in schema.get("required", []) if key not in RUNTIME_FIELDS]
            schema["properties"]["cognition"] = cognition_schema()
            schema["required"].append("cognition")
            schema["additionalProperties"] = False
            result.append({"type": "function", "function": {
                "name": name, "description": tool.description, "parameters": schema}})
        return result

    def commit(self, actor, request_id, turn):
        action = turn["action"]
        if action not in ACTIONS:
            raise ValueError("未知业务工具")
        self.discover_tools()
        business_fields = set(self._tools[action].inputSchema["properties"]) - RUNTIME_FIELDS - {"reason"}
        if set(turn["arguments"]) != business_fields:
            raise ValueError(f"{action} 参数应为：{sorted(business_fields)}")
        for key, value in turn["arguments"].items():
            expected_type = self._tools[action].inputSchema["properties"][key].get("type")
            if (expected_type == "string" and not isinstance(value, str)
                    or expected_type == "boolean" and type(value) is not bool):
                raise ValueError(f"{action}.{key} 必须符合 MCP Schema 的 {expected_type} 类型")
        expected_revision = self.snapshot["revision"]
        arguments = {**turn["arguments"], "worldId": self.world_id, "actor": actor,
                     "requestId": request_id, "expectedRevision": expected_revision, "reason": turn["reason"],
                     "cognitionJson": json.dumps({"mind": turn["mind"], "memories": turn["memories"]}, ensure_ascii=False)}
        try:
            result = self._call(action, arguments)
            if result.get("status") == "rejected":
                raise RuleRejected(result["error"])
            if result.get("world", {}).get("version") != 3:
                raise RuntimeError("行动响应世界版本无效，需要确认提交状态")
            self._accept(result["world"])
            return result
        except RuleRejected:
            raise
        except Exception:
            # 传输或反序列化异常不是规则拒绝：只读确认，禁止改选第二次行动。
            receipt = self._call("get_execution", {"worldId": self.world_id, "actor": actor, "requestId": request_id})
            if receipt["status"] == "committed":
                return {"world": self.load(), "execution": receipt}
            raise RuntimeError("提交状态未确认，暂停本轮，禁止自动重放")

    def join(self, name, location):
        return self._accept(self._call("join_player", {"worldId": self.world_id, "name": name, "location": location}))
