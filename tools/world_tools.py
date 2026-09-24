"""Web Agent 的工具声明与 Java 世界服务请求路由。"""

import re
from typing import Any

from world.state import WORLD_STATE

REVIEW_CLAIM = re.compile(
    r"(?:我|本人)(?:已|已经)?(?:看过|查过|翻过|过目|调查过|核对过|看了|查了|调查了)"
)
OBJECT_ALIASES = {
    "住客登记簿": ("住客登记簿", "登记簿"),
    "后门": ("后门",),
    "柴房门锁": ("柴房门锁", "柴房"),
}


def unverified_inspection_claim(character: str, text: str) -> str | None:
    """检查角色自称调查过的对象是否有对应的已提交事件。"""
    object_names = {
        name
        for objects in WORLD_STATE["inspectable_objects"].values()
        for name in objects
    }
    for sentence in re.split(r"[。！？\n]", text):
        if not REVIEW_CLAIM.search(sentence):
            continue
        for object_name in object_names:
            aliases = OBJECT_ALIASES.get(object_name, (object_name,))
            if not any(alias in sentence for alias in aliases):
                continue
            if not any(
                event["type"] == "inspect"
                and event["actor"] == character
                and event["payload"].get("object_name") == object_name
                for event in WORLD_STATE["events"]
            ):
                return object_name
    return None


# Tool Schema 是给模型看的工具说明书，不负责执行 Python 函数。
NPC_ACTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "inspect",
        "description": "调查角色当前地点；可选 object_name 查看本轮 Prompt 列出的当地对象。重复调查未变化的内容不会产生新发现。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "执行调查的角色名称，例如苏晚或林默。",
                },
                "object_name": {
                    "type": "string",
                    "description": "可选的当地调查对象名称；省略时调查所在地点。",
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
        "description": "让当前角色移动到世界中的合法目标地点。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "要移动的角色名称，例如苏晚或林默。",
                },
                "location": {
                    "type": "string",
                    "description": "角色要前往的世界地点。",
                },
            },
            "required": ["character", "location"],
        },
    },
    {
        "type": "function",
        "name": "give_item",
        "description": "把自己持有的物品交给同一地点的另一名角色。",
        "parameters": {
            "type": "object",
            "properties": {
                "giver": {"type": "string", "description": "交付物品的角色名称。"},
                "receiver": {"type": "string", "description": "接收物品的角色名称。"},
                "item": {"type": "string", "description": "要交付的物品名称。"},
            },
            "required": ["giver", "receiver", "item"],
        },
    },
    {
        "type": "function",
        "name": "rest_character",
        "description": "休息一轮，恢复20点体力，上限100。移动消耗5点，调查3点，对话和交付2点，修改关系1点。体力不足时应休息。",
        "parameters": {
            "type": "object",
            "properties": {"character": {"type": "string", "description": "休息的角色名称。"}},
            "required": ["character"],
        },
    },
    {
        "type": "function", "name": "wait",
        "description": "本轮明确等待，不改变世界，不产生事件，也不再行动。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function", "name": "world_action",
        "description": "提出攻击、使用药物、逃跑、跟随或与场景对象互动的意图；由世界规则结算。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["attack", "use_item", "flee", "follow", "interact"]},
            "actor": {"type": "string"},
            "target": {"type": "string"},
            "item": {"type": "string"},
            "location": {"type": "string"},
            "object_name": {"type": "string"},
        }, "required": ["action", "actor"]},
    },
]



TOOL_NAMES = frozenset(schema["name"] for schema in NPC_ACTION_TOOL_SCHEMAS)
TOOL_ACTOR_ARGUMENTS = {
    "world_action": "actor",
    "inspect": "character",
    "talk": "speaker",
    "update_relationship": "character",
    "move_character": "character",
    "give_item": "giver",
    "rest_character": "character",
}


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    acting_character: str | None = None,
) -> str:
    """校验当前角色并通过 MCP 请求 Java；等待不生成世界事件。"""
    if name not in TOOL_NAMES:
        raise ValueError(f"未知工具：{name}")
    actor_argument = TOOL_ACTOR_ARGUMENTS.get(name)
    if actor_argument and arguments.get(actor_argument) != acting_character:
        raise ValueError(f"{acting_character}不能通过{name}替其他角色行动")
    if name == "wait":
        return "等待"

    from tools.remote_world import active_backend
    backend = active_backend()
    if backend is None:
        raise ValueError("世界服务尚未连接")
    return backend.execute(name, arguments, acting_character)
