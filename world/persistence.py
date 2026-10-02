"""把一个世界的状态、事件与角色记忆一起保存到本地 JSON。"""

import json
from copy import deepcopy
from dataclasses import asdict, fields
from pathlib import Path

from characters.model import Character, PlayerActor, is_npc
from agent.runtime import AgentRuntimeState
from agent.conversation import restore_sessions, sessions
from lore.catalog import load_lore
from memory.episodic import EpisodicArchive, MemoryEntry
from memory.semantic import SemanticFact, SemanticMemory
from memory.short_term import ShortTermMemory
from world.state import WORLD_STATE
from world.objects import current_objects, inventory, legacy_views, migrate, validate


SAVE_VERSION = 1
DEFAULT_SAVE_PATH = Path(__file__).resolve().parents[1] / "data" / "world.json"


def _memory_entry_from_dict(data: dict) -> MemoryEntry:
    return MemoryEntry(
        **{
            **data,
            "actors": tuple(data["actors"]),
            "tags": tuple(data["tags"]),
            "derived_event_ids": tuple(data["derived_event_ids"]),
        }
    )


def _character_to_dict(character: Character) -> dict:
    if not is_npc(character):
        result = asdict(character)
        result["items"] = inventory(character)
        return result
    result = {
        item.name: deepcopy(getattr(character, item.name))
        for item in fields(Character)
        if item.name not in {"memory", "semantic_memory", "runtime_state"}
    }
    memory = character.memory
    result["memory"] = {
        "max_items": memory.max_items,
        "entries": [asdict(entry) for entry in memory.recent_entries()],
        "archive": [asdict(entry) for entry in memory.archived_entries()],
        "reflection_cursor": memory.reflection_cursor,
    }
    semantic = character.semantic_memory
    result["semantic_memory"] = {
        "facts": [asdict(fact) for fact in semantic.current_facts()],
        "superseded_event_ids": sorted(semantic.superseded_event_ids),
    }
    character.runtime_state.select_goal(character.goals)
    result["runtime_state"] = character.runtime_state.to_dict()
    result["items"] = inventory(character)
    return result


def _character_from_dict(data: dict) -> Character:
    if data.get("actor_type", "npc") == "player":
        return PlayerActor(**{item.name: data[item.name] for item in fields(PlayerActor) if item.name in data})
    if data.get("actor_type", "npc") != "npc":
        raise ValueError("未知 actor_type")
    memory_data = data["memory"]
    memory = ShortTermMemory(
        max_items=memory_data["max_items"],
        entries=[_memory_entry_from_dict(item) for item in memory_data["entries"]],
        archive=EpisodicArchive(
            [_memory_entry_from_dict(item) for item in memory_data["archive"]]
        ),
        reflection_cursor=memory_data["reflection_cursor"],
    )
    semantic_data = data["semantic_memory"]
    facts = [SemanticFact(**item) for item in semantic_data["facts"]]
    semantic = SemanticMemory(
        facts={(fact.location, fact.object_id or fact.object_name): fact for fact in facts},
        superseded_event_ids=set(semantic_data["superseded_event_ids"]),
    )
    ordinary_fields = {
        item.name: (data.get(item.name, {"hp": 100, "status": "normal", "actor_type": "npc"}[item.name])
                    if item.name in {"hp", "status", "actor_type"} else data[item.name])
        for item in fields(Character)
        if item.name not in {"memory", "semantic_memory", "runtime_state"}
    }
    runtime = AgentRuntimeState.from_dict(data.get("runtime_state", {}), character=data["name"])
    runtime.select_goal(data["goals"])
    return Character(**ordinary_fields, memory=memory, semantic_memory=semantic, runtime_state=runtime)


def snapshot_world(*, scheduler_state: dict | None = None) -> dict:
    """生成可供本地存档和 V2 服务共用的完整快照。"""
    return {
        "version": SAVE_VERSION,
        "world_id": WORLD_STATE["world_id"],
        "time": WORLD_STATE["time"],
        "locations": WORLD_STATE["locations"],
        "inspectables": WORLD_STATE["inspectables"],
        **legacy_views(current_objects(), WORLD_STATE["characters"]),
        "objects": deepcopy(current_objects()),
        "lore": WORLD_STATE["lore"],
        "events": WORLD_STATE["events"],
        "active_conversations": [session.to_dict() for session in sessions() if session.status == "active"],
        "characters": {
            name: _character_to_dict(character)
            for name, character in WORLD_STATE["characters"].items()
        },
        "scheduler": scheduler_state or {"tick_count": 0},
    }


def restore_snapshot(snapshot: dict) -> dict:
    """先完整解析存档，再一次性替换当前世界。"""
    if snapshot.get("version") != SAVE_VERSION:
        raise ValueError("不支持的世界存档版本")
    characters = {
        name: _character_from_dict(data)
        for name, data in snapshot["characters"].items()
    }
    if not snapshot.get("world_id") or not characters:
        raise ValueError("世界存档缺少世界 ID 或角色")
    conversations = restore_sessions(snapshot.get("active_conversations", []), characters, snapshot["events"])
    objects = migrate(snapshot)
    validate(objects, characters, snapshot["locations"])
    for name, character in characters.items():
        character.items = [item["name"] for item in objects.values() if item["holder"] == name]
    restored = {
        key: snapshot[key]
        for key in ("world_id", "time", "locations", "inspectables", "events")
    }
    # V1 存档没有独立 lore；仅旧存档沿用当时的默认设定。
    restored["lore"] = snapshot.get("lore", [asdict(entry) for entry in load_lore()])
    restored["characters"] = characters
    restored["active_conversations"] = conversations
    restored["objects"] = objects
    restored.update(legacy_views(objects, characters))
    WORLD_STATE.clear()
    WORLD_STATE.update(restored)
    return snapshot["scheduler"]


def save_world(path: Path = DEFAULT_SAVE_PATH, *, scheduler_state: dict | None = None) -> None:
    """写入临时文件后替换存档，避免中途退出留下半份 JSON。"""
    snapshot = snapshot_world(scheduler_state=scheduler_state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_world(path: Path = DEFAULT_SAVE_PATH) -> dict:
    """先完整解析存档，再一次性替换当前世界；返回调度进度。"""
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    return restore_snapshot(snapshot)
