import json
import unittest

from tools.world_tools import (
    NPC_ACTION_TOOL_SCHEMAS,
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    execute_tool,
    give_item,
    get_character,
    get_world_time,
    inspect,
    move_character,
    talk,
    update_relationship,
)
from world.state import WORLD_STATE


class WorldToolsTest(unittest.TestCase):
    def setUp(self):
        self.original_memories = {
            name: character.memory.recent_entries()
            for name, character in WORLD_STATE["characters"].items()
        }

    def tearDown(self):
        for name, entries in self.original_memories.items():
            WORLD_STATE["characters"][name].memory.entries[:] = entries

    def test_world_state_contains_day4_data(self):
        su_wan = WORLD_STATE["characters"]["苏晚"]

        self.assertEqual(su_wan.energy, 80)
        self.assertEqual(
            su_wan.relationships,
            {"林默": 0, "赵无极": 0},
        )
        self.assertIn("赵无极", WORLD_STATE["characters"])
        self.assertIn("晚风客栈", WORLD_STATE["inspectables"])
        self.assertIsInstance(WORLD_STATE["events"], list)

    def test_get_world_time_returns_current_world_time(self):
        original_time = WORLD_STATE["time"]
        try:
            WORLD_STATE["time"] = "09:30"

            self.assertEqual(get_world_time(), "09:30")
        finally:
            WORLD_STATE["time"] = original_time

    def test_get_character_returns_current_character_state(self):
        result = json.loads(get_character("苏晚"))

        self.assertEqual(result["name"], "苏晚")
        self.assertEqual(result["location"], "晚风客栈")
        self.assertEqual(result["energy"], 80)
        self.assertEqual(result["relationships"], {"林默": 0, "赵无极": 0})
        self.assertNotIn("secrets", result)
        self.assertNotIn("known_facts", result)

    def test_get_character_rejects_unknown_character(self):
        with self.assertRaisesRegex(ValueError, "角色不存在"):
            get_character("王五")

    def test_get_character_is_available_to_the_model(self):
        schema = next(
            item for item in TOOL_SCHEMAS if item["name"] == "get_character"
        )

        self.assertEqual(schema["parameters"]["required"], ["character"])
        self.assertIn("get_character", TOOL_FUNCTIONS)

    def test_npc_action_tools_exclude_global_character_query(self):
        tool_names = {
            schema["name"] for schema in NPC_ACTION_TOOL_SCHEMAS
        }

        self.assertNotIn("get_character", tool_names)
        self.assertIn("move_character", tool_names)

    def test_inspect_uses_character_current_location_and_records_event(self):
        original_events = WORLD_STATE["events"].copy()
        try:
            result = inspect("苏晚")

            self.assertIn("苏晚调查了晚风客栈", result)
            self.assertIn(WORLD_STATE["inspectables"]["晚风客栈"], result)
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "inspect")
            self.assertEqual(WORLD_STATE["events"][-1]["actor"], "苏晚")
            self.assertEqual(WORLD_STATE["events"][-1]["description"], result)
            self.assertEqual(WORLD_STATE["events"][-1]["location"], "晚风客栈")
            self.assertEqual(
                WORLD_STATE["events"][-1]["payload"],
                {"observation": WORLD_STATE["inspectables"]["晚风客栈"]},
            )
            self.assertIn(
                "我调查了晚风客栈：" + WORLD_STATE["inspectables"]["晚风客栈"],
                WORLD_STATE["characters"]["苏晚"].memory.recent(),
            )
            self.assertNotIn(result, WORLD_STATE["characters"]["林默"].memory.recent())
        finally:
            WORLD_STATE["events"][:] = original_events

    def test_inspect_rejects_unknown_character(self):
        with self.assertRaisesRegex(ValueError, "角色不存在"):
            inspect("王五")

    def test_inspect_is_available_to_the_model(self):
        schema = next(item for item in TOOL_SCHEMAS if item["name"] == "inspect")

        self.assertEqual(schema["parameters"]["required"], ["character"])
        self.assertIn("object_name", schema["parameters"]["properties"])
        self.assertIn("inspect", TOOL_FUNCTIONS)

    def test_register_review_requires_real_inspection_event(self):
        lin_mo = WORLD_STATE["characters"]["林默"]
        original_location = lin_mo.location
        original_events = WORLD_STATE["events"].copy()
        claim = "登记簿我已过目，接下来核对卷宗。"
        try:
            with self.assertRaisesRegex(ValueError, "没有可调查对象"):
                inspect("林默", "住客登记簿")
            self.assertEqual(WORLD_STATE["events"], original_events)

            lin_mo.location = "晚风客栈"
            with self.assertRaisesRegex(ValueError, "尚未调查住客登记簿"):
                talk("林默", "苏晚", claim)
            self.assertEqual(WORLD_STATE["events"], original_events)

            inspect("苏晚", "住客登记簿")
            with self.assertRaisesRegex(ValueError, "尚未调查住客登记簿"):
                talk("林默", "苏晚", claim)

            result = inspect("林默", "住客登记簿")
            self.assertIn("现有记录未列出具体住客与时辰", result)
            self.assertEqual(WORLD_STATE["events"][-1]["payload"]["object_name"], "住客登记簿")
            self.assertIn("我调查了晚风客栈的住客登记簿", lin_mo.memory.recent()[-1])
            self.assertIn(claim, talk("林默", "苏晚", claim))
        finally:
            lin_mo.location = original_location
            WORLD_STATE["events"][:] = original_events

    def test_specific_objects_and_repeated_inspection(self):
        original_events = WORLD_STATE["events"].copy()
        try:
            for object_name in ("后门", "柴房门锁"):
                result = inspect("苏晚", object_name)
                self.assertIn(object_name, result)
                self.assertEqual(WORLD_STATE["events"][-1]["payload"]["object_name"], object_name)

            count = len(WORLD_STATE["events"])
            with self.assertRaisesRegex(ValueError, "目前没有新发现"):
                inspect("苏晚", "后门")
            self.assertEqual(len(WORLD_STATE["events"]), count)
            with self.assertRaisesRegex(ValueError, "没有可调查对象"):
                inspect("苏晚", "不存在的房间")
            self.assertEqual(len(WORLD_STATE["events"]), count)
        finally:
            WORLD_STATE["events"][:] = original_events

    def test_talk_records_event_when_characters_share_location(self):
        original_location = WORLD_STATE["characters"]["林默"].location
        original_events = WORLD_STATE["events"].copy()
        try:
            WORLD_STATE["characters"]["林默"].location = "晚风客栈"

            result = talk("苏晚", "林默", "客官，要住店吗？")

            self.assertEqual(result, "苏晚对林默说：“客官，要住店吗？”")
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "talk")
            self.assertEqual(WORLD_STATE["events"][-1]["actor"], "苏晚")
            self.assertEqual(WORLD_STATE["events"][-1]["description"], result)
            self.assertEqual(WORLD_STATE["events"][-1]["target"], "林默")
            self.assertEqual(WORLD_STATE["events"][-1]["location"], "晚风客栈")
            self.assertEqual(WORLD_STATE["events"][-1]["payload"], {"message": "客官，要住店吗？"})
            self.assertIn(
                "我对林默说：“客官，要住店吗？”",
                WORLD_STATE["characters"]["苏晚"].memory.recent(),
            )
            self.assertIn(
                "苏晚对我说：“客官，要住店吗？”",
                WORLD_STATE["characters"]["林默"].memory.recent(),
            )
            entry = WORLD_STATE["characters"]["林默"].memory.recent_entries()[-1]
            self.assertEqual(entry.importance, 3)
            self.assertEqual(entry.actors, ("苏晚", "林默"))
            self.assertEqual(entry.tags, ("talk", "晚风客栈"))
            event = WORLD_STATE["events"][-1]
            self.assertTrue(entry.id)
            self.assertEqual(entry.source_event_id, event["id"])
            self.assertEqual(entry.id, f"{event['id']}:林默")
            self.assertEqual(entry.timestamp, event["timestamp"])
            self.assertEqual(
                WORLD_STATE["characters"]["苏晚"].memory.recent_entries()[-1].source_event_id,
                event["id"],
            )
            self.assertEqual(
                WORLD_STATE["characters"]["赵无极"].memory.recent_entries(),
                self.original_memories["赵无极"],
            )
        finally:
            WORLD_STATE["characters"]["林默"].location = original_location
            WORLD_STATE["events"][:] = original_events

    def test_talk_is_not_heard_by_a_bystander_at_the_same_location(self):
        lin_mo = WORLD_STATE["characters"]["林默"]
        zhao = WORLD_STATE["characters"]["赵无极"]
        original_locations = (lin_mo.location, zhao.location)
        original_events = WORLD_STATE["events"].copy()
        try:
            lin_mo.location = "晚风客栈"
            zhao.location = "晚风客栈"
            result = talk("苏晚", "赵无极", "请保守秘密。")

            self.assertIn("我对赵无极说：“请保守秘密。”", WORLD_STATE["characters"]["苏晚"].memory.recent())
            self.assertIn("苏晚对我说：“请保守秘密。”", zhao.memory.recent())
            self.assertEqual(WORLD_STATE["characters"]["林默"].memory.recent_entries(), self.original_memories["林默"])
        finally:
            lin_mo.location, zhao.location = original_locations
            WORLD_STATE["events"][:] = original_events

    def test_private_events_reach_only_actor_even_when_others_are_present(self):
        lin_mo = WORLD_STATE["characters"]["林默"]
        original_location = lin_mo.location
        original_relationship = WORLD_STATE["characters"]["苏晚"].relationships["林默"]
        original_events = WORLD_STATE["events"].copy()
        try:
            lin_mo.location = "晚风客栈"
            inspection = inspect("苏晚")
            relationship = update_relationship("苏晚", "林默", -1)

            self.assertIn(
                "我调查了晚风客栈：" + WORLD_STATE["inspectables"]["晚风客栈"],
                WORLD_STATE["characters"]["苏晚"].memory.recent(),
            )
            self.assertIn("我对林默的关系值从0变为-1。", WORLD_STATE["characters"]["苏晚"].memory.recent())
            self.assertNotIn(inspection, lin_mo.memory.recent())
            self.assertNotIn(relationship, lin_mo.memory.recent())
        finally:
            lin_mo.location = original_location
            WORLD_STATE["characters"]["苏晚"].relationships["林默"] = original_relationship
            WORLD_STATE["events"][:] = original_events

    def test_talk_rejects_characters_at_different_locations(self):
        with self.assertRaisesRegex(ValueError, "不在同一地点"):
            talk("苏晚", "林默", "能听见吗？")

    def test_talk_is_available_to_the_model(self):
        schema = next(item for item in TOOL_SCHEMAS if item["name"] == "talk")

        self.assertEqual(
            schema["parameters"]["required"],
            ["speaker", "listener", "message"],
        )
        self.assertIn("talk", TOOL_FUNCTIONS)

    def test_update_relationship_changes_state_and_records_event(self):
        relationships = WORLD_STATE["characters"]["苏晚"].relationships
        original_value = relationships["林默"]
        original_events = WORLD_STATE["events"].copy()
        try:
            result = update_relationship("苏晚", "林默", -5)

            self.assertEqual(relationships["林默"], -5)
            self.assertEqual(result, "苏晚对林默的关系值从0变为-5。")
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "relationship")
            self.assertEqual(WORLD_STATE["events"][-1]["actor"], "苏晚")
            self.assertEqual(WORLD_STATE["events"][-1]["description"], result)
            self.assertEqual(WORLD_STATE["events"][-1]["target"], "林默")
            self.assertEqual(
                WORLD_STATE["events"][-1]["payload"],
                {"change": -5, "old_value": 0, "new_value": -5},
            )
            self.assertIn("我对林默的关系值从0变为-5。", WORLD_STATE["characters"]["苏晚"].memory.recent())
            self.assertNotIn(result, WORLD_STATE["characters"]["林默"].memory.recent())
            self.assertNotIn(result, WORLD_STATE["characters"]["赵无极"].memory.recent())
        finally:
            relationships["林默"] = original_value
            WORLD_STATE["events"][:] = original_events

    def test_update_relationship_stays_within_allowed_range(self):
        relationships = WORLD_STATE["characters"]["苏晚"].relationships
        original_value = relationships["林默"]
        original_events = WORLD_STATE["events"].copy()
        try:
            update_relationship("苏晚", "林默", 150)

            self.assertEqual(relationships["林默"], 100)
        finally:
            relationships["林默"] = original_value
            WORLD_STATE["events"][:] = original_events

    def test_update_relationship_rejects_self_target(self):
        with self.assertRaisesRegex(ValueError, "不能修改与自己的关系"):
            update_relationship("苏晚", "苏晚", 5)

    def test_update_relationship_is_available_to_the_model(self):
        schema = next(
            item for item in TOOL_SCHEMAS
            if item["name"] == "update_relationship"
        )

        self.assertEqual(
            schema["parameters"]["required"],
            ["character", "target", "change"],
        )
        self.assertIn("update_relationship", TOOL_FUNCTIONS)

    def test_tool_schema_describes_get_world_time(self):
        schema = TOOL_SCHEMAS[0]

        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["name"], "get_world_time")
        self.assertEqual(schema["parameters"]["properties"], {})

    def test_execute_tool_calls_registered_function(self):
        self.assertEqual(execute_tool("get_world_time", {}), WORLD_STATE["time"])

    def test_execute_tool_rejects_unknown_tool(self):
        with self.assertRaisesRegex(ValueError, "未知工具"):
            execute_tool("open_treasure_chest", {})

    def test_execute_tool_rejects_acting_for_another_character(self):
        with self.assertRaisesRegex(ValueError, "不能.*替其他角色行动"):
            execute_tool(
                "move_character",
                {"character": "苏晚", "location": "县衙"},
                acting_character="林默",
            )

    def test_move_character_changes_world_state(self):
        original_location = WORLD_STATE["characters"]["苏晚"].location
        original_events = WORLD_STATE["events"].copy()
        try:
            result = move_character("苏晚", "县衙")

            self.assertEqual(WORLD_STATE["characters"]["苏晚"].location, "县衙")
            self.assertEqual(result, "苏晚从晚风客栈移动到县衙。")
            event = WORLD_STATE["events"][-1]
            self.assertTrue(event["id"])
            self.assertEqual(
                event,
                {
                    "id": event["id"],
                    "timestamp": WORLD_STATE["time"],
                    "type": "move",
                    "actor": "苏晚",
                    "target": None,
                    "location": "县衙",
                    "payload": {"from": "晚风客栈", "to": "县衙"},
                    "description": result,
                },
            )
            self.assertIn("我从晚风客栈来到县衙。", WORLD_STATE["characters"]["苏晚"].memory.recent())
            self.assertIn("我在县衙看到苏晚来到这里。", WORLD_STATE["characters"]["林默"].memory.recent())
            self.assertEqual(WORLD_STATE["characters"]["赵无极"].memory.recent_entries(), self.original_memories["赵无极"])
        finally:
            WORLD_STATE["characters"]["苏晚"].location = original_location
            WORLD_STATE["events"][:] = original_events

    def test_move_character_rejects_unknown_location(self):
        with self.assertRaisesRegex(ValueError, "地点不存在"):
            move_character("苏晚", "皇宫")

    def test_give_item_transfers_ownership_and_records_private_event(self):
        su_wan = WORLD_STATE["characters"]["苏晚"]
        lin_mo = WORLD_STATE["characters"]["林默"]
        original_location = lin_mo.location
        original_items = (su_wan.items.copy(), lin_mo.items.copy())
        original_events = WORLD_STATE["events"].copy()
        try:
            lin_mo.location = su_wan.location
            result = execute_tool(
                "give_item",
                {"giver": "苏晚", "receiver": "林默", "item": "私人账本"},
                acting_character="苏晚",
            )

            self.assertEqual(result, "苏晚在晚风客栈把私人账本交给了林默。")
            self.assertNotIn("私人账本", su_wan.items)
            self.assertIn("私人账本", lin_mo.items)
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "give_item")
            self.assertIn("我把私人账本交给了林默。", su_wan.memory.recent())
            self.assertIn("苏晚把私人账本交给了我。", lin_mo.memory.recent())
        finally:
            lin_mo.location = original_location
            su_wan.items[:], lin_mo.items[:] = original_items
            WORLD_STATE["events"][:] = original_events

    def test_give_item_rejects_missing_and_foreign_items_without_changes(self):
        original_items = {
            name: character.items.copy()
            for name, character in WORLD_STATE["characters"].items()
        }
        original_events = WORLD_STATE["events"].copy()

        with self.assertRaisesRegex(ValueError, "物品不存在：不存在的钥匙"):
            give_item("苏晚", "林默", "不存在的钥匙")
        with self.assertRaisesRegex(ValueError, "苏晚不拥有物品：捕快腰牌"):
            give_item("苏晚", "林默", "捕快腰牌")

        self.assertEqual(
            {name: character.items for name, character in WORLD_STATE["characters"].items()},
            original_items,
        )
        self.assertEqual(WORLD_STATE["events"], original_events)


if __name__ == "__main__":
    unittest.main()
