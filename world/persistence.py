"""只存当前世界ID，不再在 Python 保存另一份世界业务快照。"""

import json
from pathlib import Path

POINTER = Path(__file__).resolve().parents[1] / "data" / "runtime.json"


def current_world_id():
    if not POINTER.exists():
        return None
    data = json.loads(POINTER.read_text(encoding="utf-8"))
    if not isinstance(data.get("world_id"), str) or not data["world_id"]:
        raise ValueError("Runtime 世界指针损坏；原数据库存档仍然保留")
    return data["world_id"]


def remember_world(world_id):
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    temporary = POINTER.with_suffix(".tmp")
    temporary.write_text(json.dumps({"world_id": world_id}), encoding="utf-8")
    temporary.replace(POINTER)
