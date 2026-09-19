import json
import unittest

from tools.world_tools import (
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    execute_tool,
    get_character,
    get_world_time,
    inspect,
    move_character,
    talk,
    update_relationship,
)
from world.state import WORLD_STATE


class WorldToolsTest(unittest.TestCase):
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

    def test_inspect_uses_character_current_location_and_records_event(self):
        original_events = WORLD_STATE["events"].copy()
        try:
            result = inspect("苏晚")

            self.assertIn("苏晚调查了晚风客栈", result)
            self.assertIn(WORLD_STATE["inspectables"]["晚风客栈"], result)
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "inspect")
            self.assertEqual(WORLD_STATE["events"][-1]["actor"], "苏晚")
            self.assertEqual(WORLD_STATE["events"][-1]["description"], result)
        finally:
            WORLD_STATE["events"][:] = original_events

    def test_inspect_rejects_unknown_character(self):
        with self.assertRaisesRegex(ValueError, "角色不存在"):
            inspect("王五")

    def test_inspect_is_available_to_the_model(self):
        schema = next(item for item in TOOL_SCHEMAS if item["name"] == "inspect")

        self.assertEqual(schema["parameters"]["required"], ["character"])
        self.assertIn("inspect", TOOL_FUNCTIONS)

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
        finally:
            WORLD_STATE["characters"]["林默"].location = original_location
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

    def test_move_character_changes_world_state(self):
        original_location = WORLD_STATE["characters"]["苏晚"].location
        original_events = WORLD_STATE["events"].copy()
        try:
            result = move_character("苏晚", "县衙")

            self.assertEqual(WORLD_STATE["characters"]["苏晚"].location, "县衙")
            self.assertEqual(result, "苏晚从晚风客栈移动到县衙。")
            self.assertEqual(
                WORLD_STATE["events"][-1],
                {
                    "time": WORLD_STATE["time"],
                    "type": "move",
                    "actor": "苏晚",
                    "description": result,
                },
            )
        finally:
            WORLD_STATE["characters"]["苏晚"].location = original_location
            WORLD_STATE["events"][:] = original_events

    def test_move_character_rejects_unknown_location(self):
        with self.assertRaisesRegex(ValueError, "地点不存在"):
            move_character("苏晚", "皇宫")


if __name__ == "__main__":
    unittest.main()
