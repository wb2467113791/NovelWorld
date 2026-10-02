"""Java objects 的只读视角与旧快照迁移；没有动作结算或模型写入口。"""

from copy import deepcopy
from hashlib import sha256


def stable_id(origin: str) -> str:
    return "obj-" + sha256(origin.encode()).hexdigest()[:24]


def make_object(name: str, location: str | None, description: str, *, holder=None) -> dict:
    origin = f"scene\0{location}\0{name}" if holder is None else f"inventory\0{holder}\0{name}"
    result = dict(id=stable_id(origin), name=name, type="item", description=description,
                  location=location, container=None, holder=holder, owner=holder,
                  portable=True, visible=True, state="normal", properties={}, affordances=[])
    if holder is None and name in {"后门", "木箱", "柴房门锁"}:
        result.update(portable=False, type="container" if name == "木箱" else "door", state="closed", affordances=["open", "close"])
        if name == "木箱":
            result["properties"]["container"] = True
    if holder is not None and "药" in name:  # 仅旧 items 的一次迁移，不是运行时 use 规则。
        result.update(affordances=["consume"], properties={"heal": 20})
    return result


def migrate(snapshot: dict) -> dict:
    """legacy migration only：objects 存在时忽略旧物件字段。"""
    if "objects" in snapshot:
        objects = deepcopy(snapshot["objects"])
        if snapshot.get("version", 1) == 1:
            # V1 canonical 快照也可能带有已经退役的能力标记。
            for item in objects.values():
                item["properties"].pop("legacy_concealable", None)
                item["properties"].pop("trace_for", None)
        return objects
    if snapshot.get("version", 1) == 2:
        raise ValueError("V2 存档必须包含 objects")
    result = {}
    for place, names in snapshot.get("inspectable_objects", {}).items():
        for name, description in names.items():
            item = make_object(name, place, description)
            result[item["id"]] = item
    for place, names in snapshot.get("concealed_objects", {}).items():
        for name, old in names.items():
            item = make_object(name, place, old["observation"])
            item["visible"] = False
            item["properties"]["hidden_at_index"] = old.get("concealed_at_event_count", 0)
            result[item["id"]] = item
            trace = result.get(stable_id(f"scene\0{place}\0{old['trace_name']}"))
            if trace:
                trace["portable"] = False
                trace["properties"]["hidden_at_index"] = old.get("concealed_at_event_count", 0)
    for name, person in snapshot["characters"].items():
        for label in person.get("items", []):
            item = make_object(label, None, f"一件{label}。", holder=name)
            if item["id"] in result:
                raise ValueError("旧物品重复")
            result[item["id"]] = item
    return result


def effective_location(objects: dict, item: dict, characters: dict) -> str | None:
    if item["holder"] is not None:
        person = characters[item["holder"]]
        return person.location if hasattr(person, "location") else person["location"]
    return objects[item["container"]]["location"] if item["container"] else item["location"]


def is_visible(objects: dict, item: dict, actor: str, characters: dict) -> bool:
    person = characters[actor]
    place = person.location if hasattr(person, "location") else person["location"]
    if not item["visible"] or effective_location(objects, item, characters) != place or item["holder"] not in (None, actor):
        return False
    if item["container"]:
        parent = objects[item["container"]]
        return parent["visible"] and parent["state"] == "open"
    return True


def current_objects() -> dict:
    from world.state import WORLD_STATE
    return WORLD_STATE["objects"]


def visible_objects(character) -> list[dict]:
    from world.state import WORLD_STATE
    if character.name not in WORLD_STATE["characters"]:
        return []
    objects = current_objects()
    return [item for item in objects.values() if is_visible(objects, item, character.name, WORLD_STATE["characters"])]


def inventory(character) -> list[str]:
    return [item["name"] for item in current_objects().values() if item["holder"] == character.name]


def validate(objects: dict, characters: dict, locations: list) -> None:
    fields = set(make_object("test", "test", "test"))
    states = {"normal", "open", "closed", "locked", "lit", "extinguished", "damaged", "consumed"}
    if not isinstance(objects, dict):
        raise ValueError("objects 必须按 ID 保存")
    for key, item in objects.items():
        if not isinstance(item, dict) or set(item) != fields or item["id"] != key:
            raise ValueError("Object 字段 / ID 无效")
        for field in ("id", "name", "type", "description", "state"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError("Object 文字字段无效")
        if type(item["visible"]) is not bool or type(item["portable"]) is not bool or item["state"] not in states:
            raise ValueError("Object 状态无效")
        props = item["properties"]
        if not isinstance(props, dict) or set(props) - {"container", "heal", "hidden_at_index"}:
            raise ValueError("Object properties 无效")
        if "container" in props and type(props["container"]) is not bool:
            raise ValueError("Object property 必须是布尔值")
        for field in ("heal", "hidden_at_index"):
            if field in props and (type(props[field]) is not int or props[field] < 0 or (field == "heal" and props[field] > 100)):
                raise ValueError("Object 数值属性无效")
        if not isinstance(item["affordances"], list) or any(action not in {"open", "close", "light", "extinguish", "consume"} for action in item["affordances"]):
            raise ValueError("Object affordances 无效")
        positions = sum(item[field] is not None for field in ("location", "holder", "container"))
        if (item["state"] == "consumed" and (positions != 0 or item["visible"])) or (item["state"] != "consumed" and positions != 1):
            raise ValueError("Object 必须只有一个物理位置")
        if item["location"] is not None and item["location"] not in locations:
            raise ValueError("Object 地点无效")
        if item["owner"] is not None and item["owner"] not in characters:
            raise ValueError("Object owner 无效")
        if item["holder"] is not None and (item["holder"] not in characters or not item["portable"]):
            raise ValueError("Object holder 无效")
        if props.get("container") and item["portable"]:
            raise ValueError("本阶段容器必须固定且不可携带")
        if item["container"] is not None:
            parent = objects.get(item["container"])
            if not parent or parent is item or parent["location"] is None or parent["holder"] is not None or not parent["properties"].get("container") or props.get("container"):
                raise ValueError("仅支持一层固定容器")
