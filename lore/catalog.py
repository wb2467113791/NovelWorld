"""读取经人工编写的世界设定，并在检索前检查角色可见范围。"""

import json
from dataclasses import dataclass
from pathlib import Path



LORE_PATH = Path(__file__).with_name("world_lore.json")


@dataclass(frozen=True)
class LoreEntry:
    id: str
    category: str
    audience: str
    text: str

def load_lore(path: Path = LORE_PATH) -> list[LoreEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [LoreEntry(**item) for item in data]
    if len({entry.id for entry in entries}) != len(entries):
        raise ValueError("世界设定 ID 不能重复")
    return entries
