"""读取或修改世界状态的工具。"""

from typing import Any

from world.state import WORLD_STATE


def get_world_time() -> str:
    """返回当前世界时间。"""
    return WORLD_STATE["time"]


# Tool Schema 是给模型看的工具说明书，不负责执行 Python 函数。
TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_world_time",
        "description": "获取 NovelWorld 当前的世界时间。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }
]


# 工具注册表负责把模型返回的工具名称映射到真正的 Python 函数。
TOOL_FUNCTIONS = {
    "get_world_time": get_world_time,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """根据工具名称执行对应的 Python 函数。"""
    function = TOOL_FUNCTIONS.get(name)

    if function is None:
        raise ValueError(f"未知工具：{name}")

    return function(**arguments)
