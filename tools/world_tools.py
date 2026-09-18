"""读取或修改世界状态的工具。"""

from typing import Any

from world.state import WORLD_STATE


def get_world_time() -> str:
    """返回当前世界时间。"""
    return WORLD_STATE["time"]


def move_character(character: str, location: str) -> str:
    """把指定角色移动到合法地点，并返回移动结果。"""
    characters = WORLD_STATE["characters"]
    locations = WORLD_STATE["locations"]

    if character not in characters:
        raise ValueError(f"角色不存在：{character}")

    if location not in locations:
        raise ValueError(f"地点不存在：{location}")

    old_location = characters[character]["location"]

    if old_location == location:
        return f"{character}已经在{location}。"

    characters[character]["location"] = location
    return f"{character}从{old_location}移动到{location}。"


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
    },
    {
        "type": "function",
        "name": "move_character",
        "description": "将 NovelWorld 中的指定角色移动到目标地点。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "要移动的角色名称，例如苏晚或林默。",
                },
                "location": {
                    "type": "string",
                    "description": "角色要前往的地点，例如晚风客栈、县衙或青石街。",
                },
            },
            "required": ["character", "location"],
        },
    },
]


# 工具注册表负责把模型返回的工具名称映射到真正的 Python 函数。
TOOL_FUNCTIONS = {
    "get_world_time": get_world_time,
    "move_character": move_character,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """根据工具名称执行对应的 Python 函数。"""
    function = TOOL_FUNCTIONS.get(name)

    if function is None:
        raise ValueError(f"未知工具：{name}")

    return function(**arguments)
