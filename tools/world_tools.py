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
    from world.objects import visible_objects
    object_names = {item["name"] for item in visible_objects(WORLD_STATE["characters"][character])}
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
        "type": "function", "name": "perform_activity",
        "description": "本人在当前位置进行一轮日常活动过程：duty 原地值守；upkeep 日常整理；administration 事务准备；practice 练习；planning 筹划；social_presence 在场招呼。仅记录过程，不完成交易/登记、不发现事实、不操作对象、不代表他人参与或同意。具体意图写入 cognition；需要状态变化或传达消息须调用专用工具。",
        "parameters": {"type": "object", "properties": {
            "character": {"type": "string"},
            "activity": {"type": "string", "enum": ["duty", "upkeep", "administration", "practice", "planning", "social_presence"]},
        }, "required": ["character", "activity"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "inspect",
        "description": "为当前明确的信息需求调查地点或可见对象；object_id 来自当前环境。可连续核实相关对象，不必逐个扫描环境资源。重复调查未变化的内容不会产生新发现。",
        "parameters": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string", "description": "当前可见对象 ID，优先使用；省略时可调查地点。"},
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
        "name": "rest_character",
        "description": "休息一轮，恢复20点体力，上限100。移动消耗5点，调查3点，对话和交付2点。体力不足时应休息。",
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
        "description": "提出攻击、逃跑或跟随的意图；由世界规则结算。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["attack", "flee", "follow"]},
            "actor": {"type": "string"},
            "target": {"type": "string"},
            "location": {"type": "string"},
        }, "required": ["action", "actor"]},
    },
]



for name, description, extra, required in (
    ("take", "拿起当前可见、可接近且可携带的对象。", {}, []),
    ("put", "放下本人持有的对象，只选择当前 location 或已打开的 container_id。", {"location": {"type": "string"}, "container_id": {"type": "string"}}, []),
    ("give", "把本人持有的对象交给同地点角色，owner 保留，可用于借用。", {"receiver": {"type": "string"}}, ["receiver"]),
    ("use", "仅按对象声明用途使用：consume/light/extinguish。", {"action": {"type": "string", "enum": ["consume", "light", "extinguish"]}}, ["action"]),
    ("interact", "仅按对象 affordance 和当前状态操作：open/close。", {"action": {"type": "string", "enum": ["open", "close"]}}, ["action"]),
):
    NPC_ACTION_TOOL_SCHEMAS.append({"type": "function", "name": name, "description": description,
        "parameters": {"type": "object", "properties": {"character": {"type": "string"}, "object_id": {"type": "string"}, **extra},
                       "required": ["character", "object_id", *required], "additionalProperties": False}})

# Python / Java 正式行动入口均只接受当前 Tool；旧 Event 仅用于历史读取。
TOOL_NAMES = frozenset(schema["name"] for schema in NPC_ACTION_TOOL_SCHEMAS)
TOOL_ACTOR_ARGUMENTS = {
    "perform_activity": "character",
    "take": "character", "put": "character", "give": "character", "use": "character", "interact": "character",
    "world_action": "actor",
    "inspect": "character",
    "talk": "speaker",
    "move_character": "character",
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
    if name == "world_action" and arguments.get("action") not in {"attack", "flee", "follow"}:
        raise ValueError("正式 world_action 仅支持 attack、flee、follow")
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
