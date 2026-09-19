"""读取或修改世界状态的工具。"""

import json
from typing import Any

from world.state import WORLD_STATE, record_event


def get_world_time() -> str:
    """返回当前世界时间。"""
    return WORLD_STATE["time"]


def get_character(character: str) -> str:
    """以 JSON 文本返回指定角色的当前状态。"""
    characters = WORLD_STATE["characters"]

    if character not in characters:
        raise ValueError(f"角色不存在：{character}")

    current_character = characters[character]
    # 这个公共查询工具不返回秘密和独立知识，避免模型越权读取。
    character_state = {
        "name": current_character.name,
        "role": current_character.role,
        "location": current_character.location,
        "energy": current_character.energy,
        "relationships": current_character.relationships,
    }
    return json.dumps(character_state, ensure_ascii=False)


def inspect(character: str) -> str:
    """调查角色当前所在地点，并记录调查事件。"""
    characters = WORLD_STATE["characters"]

    if character not in characters:
        raise ValueError(f"角色不存在：{character}")

    location = characters[character].location
    observation = WORLD_STATE["inspectables"].get(location)

    if observation is None:
        raise ValueError(f"地点无法调查：{location}")

    result = f"{character}调查了{location}：{observation}"
    record_event("inspect", character, result, participants=[character])
    return result


def talk(speaker: str, listener: str, message: str) -> str:
    """让同一地点的两个角色交谈，并记录对话事件。"""
    characters = WORLD_STATE["characters"]

    if speaker not in characters:
        raise ValueError(f"角色不存在：{speaker}")

    if listener not in characters:
        raise ValueError(f"角色不存在：{listener}")

    if speaker == listener:
        raise ValueError("角色不能和自己交谈")

    if characters[speaker].location != characters[listener].location:
        raise ValueError(f"{speaker}和{listener}不在同一地点，无法交谈")

    message = message.strip()
    if not message:
        raise ValueError("对话内容不能为空")

    result = f"{speaker}对{listener}说：“{message}”"
    record_event("talk", speaker, result, participants=[speaker, listener])
    return result


def update_relationship(character: str, target: str, change: int) -> str:
    """增减角色对目标角色的关系值，并记录关系变化事件。"""
    characters = WORLD_STATE["characters"]

    if character not in characters:
        raise ValueError(f"角色不存在：{character}")

    if target not in characters:
        raise ValueError(f"角色不存在：{target}")

    if character == target:
        raise ValueError("角色不能修改与自己的关系")

    if isinstance(change, bool) or not isinstance(change, int):
        raise ValueError("关系变化值必须是整数")

    relationships = characters[character].relationships
    old_value = relationships.get(target, 0)
    new_value = max(-100, min(100, old_value + change))
    relationships[target] = new_value

    result = f"{character}对{target}的关系值从{old_value}变为{new_value}。"
    record_event("relationship", character, result, participants=[character])
    return result


def move_character(character: str, location: str) -> str:
    """把指定角色移动到合法地点，并返回移动结果。"""
    characters = WORLD_STATE["characters"]
    locations = WORLD_STATE["locations"]

    if character not in characters:
        raise ValueError(f"角色不存在：{character}")

    if location not in locations:
        raise ValueError(f"地点不存在：{location}")

    old_location = characters[character].location

    if old_location == location:
        result = f"{character}已经在{location}。"
        record_event("move", character, result, participants=[character])
        return result

    characters[character].location = location
    result = f"{character}从{old_location}移动到{location}。"
    record_event("move", character, result, participants=[character])
    return result


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
        "name": "get_character",
        "description": "获取 NovelWorld 中指定角色的当前状态，包括位置、体力和关系。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "要查询的角色名称，例如苏晚或林默。",
                },
            },
            "required": ["character"],
        },
    },
    {
        "type": "function",
        "name": "inspect",
        "description": "调查指定角色当前所在地点，获取该地点可观察到的信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "执行调查的角色名称，例如苏晚或林默。",
                },
            },
            "required": ["character"],
        },
    },
    {
        "type": "function",
        "name": "talk",
        "description": "让位于同一地点的两个角色进行一次对话。",
        "parameters": {
            "type": "object",
            "properties": {
                "speaker": {
                    "type": "string",
                    "description": "说话者的角色名称。",
                },
                "listener": {
                    "type": "string",
                    "description": "听话者的角色名称。",
                },
                "message": {
                    "type": "string",
                    "description": "说话者要表达的内容。",
                },
            },
            "required": ["speaker", "listener", "message"],
        },
    },
    {
        "type": "function",
        "name": "update_relationship",
        "description": "增加或减少一个角色对另一个角色的关系值，结果限制在 -100 到 100。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "关系发生变化的角色名称。",
                },
                "target": {
                    "type": "string",
                    "description": "该角色态度所指向的目标角色名称。",
                },
                "change": {
                    "type": "integer",
                    "description": "关系值的增减量，正数表示改善，负数表示恶化。",
                },
            },
            "required": ["character", "target", "change"],
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
    "get_character": get_character,
    "inspect": inspect,
    "talk": talk,
    "update_relationship": update_relationship,
    "move_character": move_character,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """根据工具名称执行对应的 Python 函数。"""
    function = TOOL_FUNCTIONS.get(name)

    if function is None:
        raise ValueError(f"未知工具：{name}")

    return function(**arguments)
