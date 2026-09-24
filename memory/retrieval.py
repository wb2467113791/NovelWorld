"""为单个角色选出少量与当前目标有关的旧经历和调查事实。"""

from characters.model import Character
from memory.episodic import MemoryEntry


def _still_current(entry: MemoryEntry, superseded_event_ids: set[str]) -> bool:
    return (entry.source_event_id not in superseded_event_ids
            and not superseded_event_ids.intersection(entry.derived_event_ids))


def recent_memory_texts(character: Character) -> list[str]:
    """过滤已被新调查取代的近期观察及基于它们的反思。"""
    superseded = character.semantic_memory.superseded_event_ids
    return [
        entry.content for entry in character.memory.recent_entries()
        if _still_current(entry, superseded)
    ]


def eligible_archived_entries(character: Character) -> list[tuple[int, MemoryEntry]]:
    """排除无工具叙述、已被更新的调查，以及引用旧调查的反思。"""
    semantic = character.semantic_memory
    inspect_event_ids = semantic.superseded_event_ids | {
        fact.source_event_id for fact in semantic.current_facts()
    }
    return [
        (index, entry)
        for index, entry in enumerate(character.memory.archived_entries())
        if "narration" not in entry.tags
        and entry.source_event_id not in inspect_event_ids
        and _still_current(entry, semantic.superseded_event_ids)
    ]
