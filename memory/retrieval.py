"""为单个角色选出少量与当前目标有关的旧经历和调查事实。"""

from characters.model import Character
from memory.episodic import MemoryEntry
from retrieval.text import bigrams


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


def retrieve_character_memory(
    character: Character,
    query: str,
    *,
    max_items: int = 3,
    max_chars: int = 600,
) -> list[str]:
    """只在当前角色的记忆中筛选，再按相关性、重要性和新近程度排序。"""
    if max_items < 1 or max_chars < 1:
        raise ValueError("检索条数和字符上限必须大于 0")

    all_entries = character.memory.all_entries()
    recent_ids = {entry.source_event_id for entry in character.memory.recent_entries()}
    event_order = {
        entry.source_event_id: index
        for index, entry in enumerate(all_entries)
        if entry.source_event_id is not None
    }
    current_facts = character.semantic_memory.current_facts()
    candidates: list[tuple[str, int, int]] = []

    for index, entry in eligible_archived_entries(character):
        candidates.append((f"历史经历：{entry.content}", entry.importance, index))

    for fact in current_facts:
        if fact.source_event_id in recent_ids:
            continue  # 同一次调查已在近期窗口中，无需重复提供。
        candidates.append((f"已核实调查：{fact.content}", 3,
                           event_order.get(fact.source_event_id, 0)))

    query_terms = bigrams(query)
    total_entries = max(len(all_entries), 1)

    def score(candidate: tuple[str, int, int]) -> float:
        content, importance, order = candidate
        terms = bigrams(content)
        similarity = len(query_terms & terms) / max(len(query_terms), 1)
        return 0.6 * similarity + 0.25 * importance / 5 + 0.15 * (order + 1) / total_entries

    ranked = sorted(candidates, key=score, reverse=True)
    selected: list[str] = []
    remaining = max_chars
    for content, _, _ in ranked:
        if len(selected) >= max_items or remaining <= 0:
            break
        if len(content) > remaining:
            continue
        selected.append(content)
        remaining -= len(content)
    return selected
