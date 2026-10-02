"""人类输入与可见状态；行动只通过既有工具请求 Java。"""

from copy import deepcopy

from agent.conversation import context_for, end, for_participant
from characters.model import is_npc
from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS, TOOL_ACTOR_ARGUMENTS, execute_tool
from world.objects import visible_objects
from world.state import WORLD_STATE

PLAYER_TOOLS = {"inspect": "inspect", "take": "take", "put": "put", "give": "give",
                "use": "use", "interact": "interact", "move": "move_character", "talk": "talk",
                "rest": "rest_character"}
IDENTITY_FIELDS = {"character", "speaker", "actor", "giver", "actingCharacter"}


def player_actor():
    players = [actor for actor in WORLD_STATE["characters"].values() if not is_npc(actor)]
    if len(players) != 1:
        raise RuntimeError("当前世界需要 Java 初始化唯一 Player")
    return players[0]


def action_schemas() -> list[dict]:
    schemas = []
    reverse = {tool: action for action, tool in PLAYER_TOOLS.items()}
    for schema in NPC_ACTION_TOOL_SCHEMAS:
        if schema["name"] not in reverse:
            continue
        value = deepcopy(schema)
        value["name"] = reverse[schema["name"]]
        parameters = value["parameters"]
        parameters["properties"] = {key: raw for key, raw in parameters["properties"].items() if key not in IDENTITY_FIELDS}
        parameters["required"] = [key for key in parameters["required"] if key not in IDENTITY_FIELDS]
        parameters["additionalProperties"] = False
        schemas.append(value)
    return schemas


def submit_action(action: str, arguments: dict) -> str:
    if action not in PLAYER_TOOLS or not isinstance(arguments, dict):
        raise ValueError("不支持的 Player action")
    if IDENTITY_FIELDS.intersection(arguments):
        raise ValueError("Player 身份由服务端决定，不能指定行动者")
    schema = next(value for value in action_schemas() if value["name"] == action)["parameters"]
    if set(arguments) - set(schema["properties"]) or not set(schema["required"]).issubset(arguments):
        raise ValueError("Player action 参数无效")
    for key, value in arguments.items():
        definition = schema["properties"][key]
        if not isinstance(value, str) or not value.strip() or ("enum" in definition and value not in definition["enum"]):
            raise ValueError("Player action 参数必须为有效文字")
    if action == "talk" and len(arguments["message"]) > 2000:
        raise ValueError("消息不能超过 2000 字")
    player = player_actor()
    tool = PLAYER_TOOLS[action]
    return execute_tool(tool, {**arguments, TOOL_ACTOR_ARGUMENTS[tool]: player.name}, acting_character=player.name)


def state_view(tick_count: int) -> dict:
    player = player_actor()
    def object_view(item):
        return {key: deepcopy(item[key]) for key in ("id", "name", "type", "state", "portable", "affordances")}
    objects = visible_objects(player)
    held = [item for item in objects if item["holder"] == player.name]
    conversation = context_for(player.name)
    if conversation is not None:
        conversation["waiting_for_player"] = conversation["your_turn"]
    return {
        "world_id": WORLD_STATE["world_id"], "time": WORLD_STATE["time"], "tick_count": tick_count,
        "player": {key: deepcopy(getattr(player, key)) for key in ("name", "location", "energy", "hp", "status", "relationships")},
        "inventory": [object_view(item) for item in held],
        "location_description": WORLD_STATE["inspectables"].get(player.location, ""),
        "nearby_characters": [{key: getattr(actor, key) for key in ("name", "location", "hp", "status")}
                              for actor in WORLD_STATE["characters"].values()
                              if actor.name != player.name and actor.location == player.location],
        "visible_objects": [object_view(item) for item in objects],
        "conversation": conversation,
        "events": [{key: deepcopy(event[key]) for key in ("id", "timestamp", "type", "actor", "target", "location", "description")}
                   for event in WORLD_STATE["events"] if event["type"] != "narration"
                   and player.name in event.get("perceived_by", [event["actor"]])][-30:],
        "locations": list(WORLD_STATE["locations"]), "actions": action_schemas(),
    }


def end_conversation() -> None:
    session = for_participant(player_actor().name)
    if session is not None:
        end(session)
