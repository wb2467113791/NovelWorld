"""从角色近期经历中生成可重复验证的简单反思。"""

from memory.short_term import ShortTermMemory


def reflect_on_new_memories(
    memory: ShortTermMemory,
    *,
    superseded_event_ids: set[str] | None = None,
) -> str | None:
    """处理上次反思后的全部经历，包括已离开近期窗口的经历。"""
    entries = memory.all_entries()
    new_experiences = [
        entry for entry in entries[memory.reflection_cursor:]
        if "reflection" not in entry.tags and "narration" not in entry.tags
        and entry.source_event_id not in (superseded_event_ids or set())
    ]
    if not new_experiences:
        memory.reflection_cursor = len(entries)
        return None

    ranked = sorted(
        enumerate(new_experiences),
        key=lambda item: (item[1].importance, item[0]),
        reverse=True,
    )
    selected_entries = [entry for _, entry in ranked[:2]]
    selected = [entry.content for entry in selected_entries]
    actors = tuple(dict.fromkeys(
        actor for entry in selected_entries for actor in entry.actors
    ))
    reflection = "我近期最该留意的是：" + "；".join(selected)
    memory.add(
        reflection, importance=4, actors=actors, tags=("reflection",),
        derived_event_ids=tuple(
            entry.source_event_id
            for entry in selected_entries if entry.source_event_id is not None
        ),
    )
    memory.reflection_cursor = len(memory.all_entries())
    return reflection
