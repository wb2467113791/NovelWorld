"""Python 初始 seed 与 Java 创建世界共用同一 canonical 模板。"""

import json
from pathlib import Path

from characters.model import Character

DEFAULT_TEMPLATE = json.loads(
    (Path(__file__).resolve().parents[1] / "world-service" / "src" / "main" /
     "resources" / "default-world-template.json").read_text(encoding="utf-8")
)
CHARACTERS = {name: Character(**data) for name, data in DEFAULT_TEMPLATE["characters"].items()}
for name, character in CHARACTERS.items():
    character.items = [item["name"] for item in DEFAULT_TEMPLATE["objects"].values() if item["holder"] == name]
