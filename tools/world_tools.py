"""读取或修改世界状态的工具。"""

import json
import re
from typing import Any

from world.state import WORLD_STATE, record_event


REVIEW_CLAIM = re.compile(
    r"(?:我|本人)(?:已|已经)?(?:看过|查过|翻过|过目|调查过|核对过|看了|查了|调查了)"
)
READ_ONLY_TOOLS = frozenset({"get_world_time", "get_character"})
ENERGY_COSTS = {
    "move_character": 5,
    "inspect": 3,
    "talk": 2,
    "give_item": 2,
    "update_relationship": 1,
}
REST_GAIN = 20
MAX_ENERGY = 100


def require_energy(character: str, action: str) -> None:
    cost = ENERGY_COSTS[action]
    if WORLD_STATE["characters"][character].energy < cost:
        raise ValueError(f"{character}体力不足，执行{action}需要{cost}点体力")


def spend_energy(character: str, action: str) -> None:
    WORLD_STATE["characters"][character].energy -= ENERGY_COSTS[action]


OBJECT_ALIASES = {
    "住客登记簿": ("住客登记簿", "登记簿"),
    "后门": ("后门",),
    "柴房门锁": ("柴房门锁", "柴房"),
}


def unverified_inspection_claim(character: str, text: str) -> str | None:
    """找出角色自称已查看、但没有调查事件支持的具体对象。"""
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


def inspect(character: str, object_name: str | None = None) -> str:
    """调查当前地点或该地点的具体对象，并记录调查事件。"""
    characters = WORLD_STATE["characters"]

    if character not in characters:
        raise ValueError(f"角色不存在：{character}")

    location = characters[character].location
    if object_name is None:
        observation = WORLD_STATE["inspectables"].get(location)
        if observation is None:
            raise ValueError(f"地点无法调查：{location}")
        result = f"{character}调查了{location}：{observation}"
    else:
        if not isinstance(object_name, str):
            raise ValueError("调查对象名称必须是文字")
        observation = WORLD_STATE["inspectable_objects"].get(location, {}).get(object_name)
        if observation is None:
            raise ValueError(f"{location}没有可调查对象：{object_name}")
        result = f"{character}调查了{location}的{object_name}：{observation}"
    last_inspection = next((
        event for event in reversed(WORLD_STATE["events"])
        if event["type"] == "inspect"
        and event["actor"] == character
        and event["location"] == location
        and event["payload"].get("object_name") == object_name
    ), None)
    if last_inspection is not None and last_inspection["payload"].get("observation") == observation:
        subject = object_name or location
        raise ValueError(f"{character}已调查过{subject}，目前没有新发现")
    require_energy(character, "inspect")
    spend_energy(character, "inspect")
    record_event(
        "inspect", character, result,
        location=location,
        payload={"observation": observation, **({"object_name": object_name} if object_name else {})},
    )
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

    # 他人的口头承诺不算本人已经调查的证据。
    unverified_object = unverified_inspection_claim(speaker, message)
    if unverified_object:
        raise ValueError(f"{speaker}尚未调查{unverified_object}，不能声称已经查看")

    require_energy(speaker, "talk")
    spend_energy(speaker, "talk")
    result = f"{speaker}对{listener}说：“{message}”"
    record_event(
        "talk", speaker, result,
        target=listener, location=characters[speaker].location,
        payload={"message": message},
    )
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
    require_energy(character, "update_relationship")
    spend_energy(character, "update_relationship")
    relationships[target] = new_value

    result = f"{character}对{target}的关系值从{old_value}变为{new_value}。"
    record_event(
        "relationship", character, result,
        target=target,
        payload={"change": change, "old_value": old_value, "new_value": new_value},
    )
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
    require_energy(character, "move_character")
    spend_energy(character, "move_character")

    if old_location == location:
        result = f"{character}已经在{location}。"
        record_event(
            "move", character, result,
            location=location, payload={"from": old_location, "to": location},
        )
        return result

    characters[character].location = location
    result = f"{character}从{old_location}移动到{location}。"
    record_event(
        "move", character, result,
        location=location, payload={"from": old_location, "to": location},
    )
    return result


def give_item(giver: str, receiver: str, item: str) -> str:
    """同地点交付物品；归属校验通过后才修改双方清单。"""
    characters = WORLD_STATE["characters"]
    if giver not in characters:
        raise ValueError(f"角色不存在：{giver}")
    if receiver not in characters:
        raise ValueError(f"角色不存在：{receiver}")
    if giver == receiver:
        raise ValueError("角色不能把物品交给自己")

    giver_items = characters[giver].items
    if item not in giver_items:
        if any(item in character.items for character in characters.values()):
            raise ValueError(f"{giver}不拥有物品：{item}")
        raise ValueError(f"物品不存在：{item}")

    location = characters[giver].location
    if location != characters[receiver].location:
        raise ValueError(f"{giver}和{receiver}不在同一地点，无法交付物品")

    require_energy(giver, "give_item")
    spend_energy(giver, "give_item")
    giver_items.remove(item)
    characters[receiver].items.append(item)
    result = f"{giver}在{location}把{item}交给了{receiver}。"
    record_event(
        "give_item", giver, result,
        target=receiver, location=location, payload={"item": item},
    )
    return result


def rest_character(character: str) -> str:
    """休息一轮，恢复体力并留下可观察的事件。"""
    characters = WORLD_STATE["characters"]
    if character not in characters:
        raise ValueError(f"角色不存在：{character}")
    current = characters[character]
    if current.energy >= MAX_ENERGY:
        raise ValueError(f"{character}体力已满，无需休息")
    before = current.energy
    current.energy = min(MAX_ENERGY, before + REST_GAIN)
    result = f"{character}休息后体力从{before}恢复到{current.energy}。"
    record_event("rest", character, result, location=current.location,
                 payload={"energy_before": before, "energy_after": current.energy})
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
        "description": "调查角色当前地点；可选 object_name 查看当地具体对象。晚风客栈有住客登记簿、后门、柴房门锁。重复调查未变化的内容不会产生新发现。",
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "执行调查的角色名称，例如苏晚或林默。",
                },
                "object_name": {
                    "type": "string",
                    "description": "可选的具体调查对象：晚风客栈的住客登记簿、后门或柴房门锁。省略时调查所在地点。",
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
]


# NPC 的自身状态已写入行动 Prompt，因此自主行动时不开放全局角色查询。
# 普通对话仍可使用完整的 TOOL_SCHEMAS。
NPC_ACTION_TOOL_SCHEMAS = [
    schema for schema in TOOL_SCHEMAS
    if schema["name"] != "get_character"
]


# 工具注册表负责把模型返回的工具名称映射到真正的 Python 函数。
TOOL_FUNCTIONS = {
    "get_world_time": get_world_time,
    "get_character": get_character,
    "inspect": inspect,
    "talk": talk,
    "update_relationship": update_relationship,
    "move_character": move_character,
    "give_item": give_item,
    "rest_character": rest_character,
}


TOOL_ACTOR_ARGUMENTS = {
    "get_character": "character",
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
    """根据工具名称执行对应的 Python 函数。"""
    function = TOOL_FUNCTIONS.get(name)

    if function is None:
        raise ValueError(f"未知工具：{name}")

    actor_argument = TOOL_ACTOR_ARGUMENTS.get(name)
    if (
        acting_character is not None
        and actor_argument is not None
        and arguments.get(actor_argument) != acting_character
    ):
        raise ValueError(
            f"{acting_character}不能通过{name}替其他角色行动"
        )

    from tools.remote_world import active_backend
    backend = active_backend()
    if backend is not None:
        return backend.execute(name, arguments, acting_character)

    return function(**arguments)
