"""把一个世界的状态、事件与角色记忆一起保存到本地 JSON。"""

import json
from copy import deepcopy
from dataclasses import asdict, fields
from pathlib import Path
from uuid import uuid4

from characters.model import Character
from memory.episodic import EpisodicArchive, MemoryEntry
from memory.semantic import SemanticFact, SemanticMemory
from memory.short_term import ShortTermMemory
from world.state import INITIAL_WORLD_STATE, WORLD_STATE


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
    result = {
        item.name: deepcopy(getattr(character, item.name))
        for item in fields(Character)
        if item.name not in {"memory", "semantic_memory"}
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
    return result


def _character_from_dict(data: dict) -> Character:
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
        facts={(fact.location, fact.object_name): fact for fact in facts},
        superseded_event_ids=set(semantic_data["superseded_event_ids"]),
    )
    ordinary_fields = {
        item.name: data[item.name]
        for item in fields(Character)
        if item.name not in {"memory", "semantic_memory"}
    }
    return Character(**ordinary_fields, memory=memory, semantic_memory=semantic)


def snapshot_world(*, scheduler_state: dict | None = None) -> dict:
    """生成可供本地存档和 V2 服务共用的完整快照。"""
    return {
        "version": SAVE_VERSION,
        "world_id": WORLD_STATE["world_id"],
        "time": WORLD_STATE["time"],
        "locations": WORLD_STATE["locations"],
        "inspectables": WORLD_STATE["inspectables"],
        "inspectable_objects": WORLD_STATE["inspectable_objects"],
        "events": WORLD_STATE["events"],
        "characters": {
            name: _character_to_dict(character)
            for name, character in WORLD_STATE["characters"].items()
        },
        "scheduler": scheduler_state or {"next_index": 0, "tick_count": 0},
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
    restored = {
        key: snapshot[key]
        for key in ("world_id", "time", "locations", "inspectables", "inspectable_objects", "events")
    }
    restored["characters"] = characters
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


def start_new_world() -> None:
    """显式新建世界时隔离旧存档和旧世界的检索索引。"""
    WORLD_STATE.clear()
    WORLD_STATE.update(deepcopy(INITIAL_WORLD_STATE))
    WORLD_STATE["world_id"] = uuid4().hex
