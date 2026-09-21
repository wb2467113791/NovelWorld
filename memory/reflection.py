"""从角色近期经历中生成可重复验证的简单反思。"""

from memory.short_term import ShortTermMemory


def reflect_on_new_memories(memory: ShortTermMemory) -> str | None:
    """只反思上次 Reflection 后的新经历，优先选重要且较新的两条。"""
    entries = memory.recent_entries()
    last_reflection = next(
        (index for index in range(len(entries) - 1, -1, -1)
         if "reflection" in entries[index].tags),
        -1,
    )
    new_experiences = [
        entry for entry in entries[last_reflection + 1:]
        if "reflection" not in entry.tags and "narration" not in entry.tags
    ]
    if not new_experiences:
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
    memory.add(reflection, importance=4, actors=actors, tags=("reflection",))
    return reflection
