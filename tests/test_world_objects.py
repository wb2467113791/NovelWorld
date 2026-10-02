"""物件的角色视角、迁移和 Java 边界；只使用服务/模型替身。"""
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.graph import build_agent_loop_graph
from agent.perception import observe
from agent.state import create_initial_agent_state
from characters.prompt import build_action_prompt
from tests.support import committed_event
from tools.remote_world import RemoteWorld
from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS, execute_tool
from world.objects import current_objects, inventory, make_object, visible_objects, validate
from world.persistence import restore_snapshot, snapshot_world
from world.state import WORLD_STATE


class WorldObjectsTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))
        self.person = WORLD_STATE["characters"]["林默"]
        self.person.location = "晚风客栈"
        self.objects = current_objects()
        self.book = next(obj for obj in self.objects.values() if obj["name"] == "住客登记簿")
        self.chest = next(obj for obj in self.objects.values() if obj["name"] == "木箱")

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def prompt(self):
        return build_action_prompt(self.person, active_goal=self.person.goals[0], memories=[],
                                   retrieved_context=[], lore_context=[], observations=observe(self.person))

    def test_old_snapshot_migrates_stably_and_inventory_is_not_ground_location(self):
        old = deepcopy(snapshot_world())
        old.pop("objects")
        restore_snapshot(deepcopy(old))
        first = deepcopy(current_objects())
        restore_snapshot(deepcopy(old))
        self.assertEqual(first, current_objects())
        self.assertEqual(len(first), len({obj["id"] for obj in first.values()}))
        self.assertTrue(any(obj["holder"] == "林默" and obj["location"] is None for obj in first.values()))

    def test_legacy_hidden_trace_migrates_without_leaking_original(self):
        old = deepcopy(snapshot_world())
        old.pop("objects")
        original = old["inspectable_objects"]["晚风客栈"].pop("住客登记簿")
        trace = "住客登记簿被移动的痕迹"
        old["inspectable_objects"]["晚风客栈"][trace] = "移走痕迹"
        old["concealed_objects"] = {"晚风客栈": {"住客登记簿": {
            "observation": original, "trace_name": trace, "concealed_at_event_count": 0}}}
        restore_snapshot(old)
        names = [obj["name"] for obj in visible_objects(WORLD_STATE["characters"]["林默"])]
        self.assertIn(trace, names)
        self.assertNotIn("住客登记簿", names)
        hidden = next(obj for obj in current_objects().values() if obj["name"] == "住客登记簿")
        self.assertFalse(hidden["visible"])
        self.assertIsNone(hidden["holder"])

    def test_prompt_omits_hidden_closed_contents_owner_and_private_description(self):
        self.book.update(location=None, container=self.chest["id"], owner="苏晚", description="不可外泄的账目")
        text = self.prompt()
        self.assertNotIn(self.book["id"], text)
        self.assertNotIn("不可外泄的账目", text)
        self.assertNotIn('"owner"', text)
        self.assertNotIn("legacy_concealable", text)
        self.chest["state"] = "open"  # 模拟 Java 已提交后刷新
        self.assertIn(self.book["id"], self.prompt())
        self.assertNotIn("不可外泄的账目", self.prompt())  # 内容需要 inspect
        self.book["visible"] = False
        self.assertNotIn(self.book["id"], self.prompt())

    def test_remote_and_other_holders_are_not_in_ordinary_perception(self):
        self.book.update(location=None, holder="苏晚")
        self.assertNotIn(self.book["id"], self.prompt())
        self.book.update(holder=None, location="县衙")
        self.assertNotIn(self.book["id"], self.prompt())

    def test_items_and_legacy_dictionaries_cannot_override_canonical_objects(self):
        self.book.update(location=None, holder="林默")
        self.person.items = ["伪造钥匙"]
        WORLD_STATE["inspectable_objects"] = {"县衙": {"住客登记簿": "伪造"}}
        saved = deepcopy(snapshot_world())
        self.assertIn("住客登记簿", inventory(self.person))
        self.assertNotIn("伪造钥匙", saved["characters"]["林默"]["items"])
        self.assertNotIn("住客登记簿", saved["inspectable_objects"].get("县衙", {}))
        restore_snapshot(saved)
        self.assertEqual("林默", current_objects()[self.book["id"]]["holder"])

    def test_restore_keeps_container_state_holder_and_world_isolation(self):
        first = deepcopy(snapshot_world())
        self.book.update(location=None, holder="林默")
        held = deepcopy(snapshot_world())
        self.book.update(holder=None, container=self.chest["id"])
        self.chest["state"] = "open"
        inside = deepcopy(snapshot_world())
        inside["world_id"] = "object-other-world"
        restore_snapshot(first)
        self.assertEqual("晚风客栈", current_objects()[self.book["id"]]["location"])
        restore_snapshot(held)
        self.assertEqual("林默", current_objects()[self.book["id"]]["holder"])
        restore_snapshot(inside)
        self.assertEqual(self.chest["id"], current_objects()[self.book["id"]]["container"])
        self.assertEqual("open", current_objects()[self.chest["id"]]["state"])
        restore_snapshot(first)
        self.assertEqual("closed", current_objects()[self.chest["id"]]["state"])

    def test_invalid_snapshot_fails_before_replacing_world(self):
        saved = deepcopy(snapshot_world())
        saved["objects"][self.book["id"]]["holder"] = "林默"
        before = deepcopy(snapshot_world())
        with self.assertRaises(ValueError):
            restore_snapshot(saved)
        self.assertEqual(before, snapshot_world())

    def test_unknown_properties_and_affordances_are_rejected(self):
        for field, value in (("properties", {"script": "change world"}), ("affordances", ["偷偷毁掉证据"])):
            invalid = deepcopy(self.objects)
            invalid[self.book["id"]][field] = value
            with self.assertRaises(ValueError):
                validate(invalid, WORLD_STATE["characters"], WORLD_STATE["locations"])

    def test_same_display_name_distinct_ids_and_verified_facts(self):
        other = make_object("住客登记簿", "县衙", "另一册")
        self.objects[other["id"]] = other
        self.assertNotEqual(other["id"], self.book["id"])
        for obj in (self.book, other):
            committed_event("inspect", "林默", "调查物件", location="晚风客栈",
                            payload={"object_id": obj["id"], "object_name": obj["name"], "observation": obj["description"]})
        self.assertEqual(2, len([fact for fact in self.person.semantic_memory.current_facts() if fact.object_name == "住客登记簿"]))
        self.assertFalse(WORLD_STATE["characters"]["苏晚"].semantic_memory.current_facts())

    def test_primitive_dispatch_never_mutates_objects_locally(self):
        backend = Mock()
        backend.execute.return_value = "Java 工具结果"
        before = deepcopy(self.objects)
        with patch("tools.remote_world.active_backend", return_value=backend):
            for tool in ("take", "put", "give", "use", "interact"):
                execute_tool(tool, {"character": "林默", "object_id": self.book["id"]}, "林默")
        self.assertEqual(before, self.objects)
        self.assertEqual(5, backend.execute.call_count)
        with patch("tools.remote_world.active_backend", return_value=None):
            with self.assertRaises(ValueError):
                execute_tool("take", {"character": "林默", "object_id": self.book["id"]}, "林默")

    def test_two_object_calls_in_one_tick_dispatch_only_one_and_model_text_has_no_physics(self):
        calls = [SimpleNamespace(type="function_call", name="take", arguments=json.dumps({"character": "林默", "object_id": self.book["id"]}), call_id=str(i)) for i in range(2)]
        responses = iter([SimpleNamespace(output=calls, output_text=""),
                          SimpleNamespace(output=[], output_text="我已经拿了书，并把木箱打开了。")])
        index = Mock()
        index.retrieve_memory.return_value = []
        index.retrieve_lore.return_value = []
        backend = Mock()
        backend.execute.return_value = "Java 已结算"
        before = deepcopy(self.objects)
        with patch("tools.remote_world.active_backend", return_value=backend):
            build_agent_loop_graph(lambda *_: next(responses)).invoke(create_initial_agent_state(self.person, index))
        backend.execute.assert_called_once()
        self.assertEqual(before, self.objects)

    def test_refresh_uses_java_objects_and_save_payload_has_no_physical_state(self):
        remote = deepcopy(snapshot_world())
        remote["objects"][self.book["id"]].update(location=None, holder="苏晚")
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call", return_value=json.dumps(remote, ensure_ascii=False)):
            backend._refresh_business_state()
        self.assertEqual("苏晚", current_objects()[self.book["id"]]["holder"])
        with patch.object(backend, "_call", return_value="saved") as request:
            backend.save_agent_state({"tick_count": 1})
        payload = json.loads(request.call_args.args[1]["agentStateJson"])
        self.assertNotIn("objects", payload)
        for person in payload["characters"].values():
            self.assertNotIn("items", person)

    def test_new_schemas_expose_ids_and_no_deprecated_conceal_sequence(self):
        names = {schema["name"]: schema for schema in NPC_ACTION_TOOL_SCHEMAS}
        self.assertNotIn("conceal_clue", names)
        self.assertNotIn("recover_clue", names)
        for tool in ("take", "put", "give", "use", "interact"):
            self.assertIn("object_id", names[tool]["parameters"]["required"])
        self.assertEqual(["attack", "flee", "follow"], names["world_action"]["parameters"]["properties"]["action"]["enum"])


if __name__ == "__main__":
    unittest.main()
