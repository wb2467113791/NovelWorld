import unittest

from tools.world_tools import (
    TOOL_SCHEMAS,
    execute_tool,
    get_world_time,
    move_character,
)
from world.state import WORLD_STATE


class WorldToolsTest(unittest.TestCase):
    def test_get_world_time_returns_current_world_time(self):
        original_time = WORLD_STATE["time"]
        try:
            WORLD_STATE["time"] = "09:30"

            self.assertEqual(get_world_time(), "09:30")
        finally:
            WORLD_STATE["time"] = original_time

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
        original_location = WORLD_STATE["characters"]["苏晚"]["location"]
        try:
            result = move_character("苏晚", "县衙")

            self.assertEqual(WORLD_STATE["characters"]["苏晚"]["location"], "县衙")
            self.assertEqual(result, "苏晚从晚风客栈移动到县衙。")
        finally:
            WORLD_STATE["characters"]["苏晚"]["location"] = original_location

    def test_move_character_rejects_unknown_location(self):
        with self.assertRaisesRegex(ValueError, "地点不存在"):
            move_character("苏晚", "皇宫")


if __name__ == "__main__":
    unittest.main()
