"""读取经人工编写的世界设定，并在检索前检查角色可见范围。"""

import json
from dataclasses import dataclass
from pathlib import Path

from retrieval.text import bigrams


LORE_PATH = Path(__file__).with_name("world_lore.json")


@dataclass(frozen=True)
class LoreEntry:
    id: str
    category: str
    audience: str
    text: str

    def visible_to(self, character_name: str) -> bool:
        return self.audience in ("public", character_name)


def load_lore(path: Path = LORE_PATH) -> list[LoreEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [LoreEntry(**item) for item in data]
    if len({entry.id for entry in entries}) != len(entries):
        raise ValueError("世界设定 ID 不能重复")
    return entries


def visible_lore(character_name: str, entries: list[LoreEntry] | None = None) -> list[LoreEntry]:
    source = load_lore() if entries is None else entries
    return [entry for entry in source if entry.visible_to(character_name)]


def retrieve_lore(
    character_name: str, query: str, *, max_items: int = 2, max_chars: int = 350,
) -> list[str]:
    """无向量索引时的本地检索；同样先过滤可见范围。"""
    query_terms = bigrams(query)
    ranked = sorted(
        visible_lore(character_name),
        key=lambda entry: len(query_terms & bigrams(entry.text + entry.category)),
        reverse=True,
    )
    results: list[str] = []
    for entry in ranked:
        if not query_terms & bigrams(entry.text + entry.category):
            continue
        item = f"世界设定（{entry.category}）：{entry.text}"
        if len(results) < max_items and len(item) <= max_chars:
            results.append(item)
            max_chars -= len(item)
    return results
