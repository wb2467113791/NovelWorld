import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from characters.presets import CHARACTERS
from run_world import WorldSession, make_graph_decide_action, run_world
from tools.world_tools import update_relationship
from world.state import WORLD_STATE


class RunWorldTest(unittest.TestCase):
    def setUp(self):
        self.original_time = WORLD_STATE["time"]
        self.original_events = WORLD_STATE["events"].copy()
        self.original_locations = {
            name: character.location for name, character in CHARACTERS.items()
        }
        self.original_relationships = {
            name: character.relationships.copy()
            for name, character in CHARACTERS.items()
        }
        self.original_memories = {
            name: character.memory.recent_entries() for name, character in CHARACTERS.items()
        }

    def tearDown(self):
        WORLD_STATE["time"] = self.original_time
        WORLD_STATE["events"][:] = self.original_events
        for name, character in CHARACTERS.items():
            character.location = self.original_locations[name]
            character.relationships.clear()
            character.relationships.update(self.original_relationships[name])
            character.memory.entries[:] = self.original_memories[name]

    def test_run_world_prints_results_without_real_model(self):
        with patch("builtins.print") as mock_print:
            results = run_world(
                2,
                lambda character: "完成一次测试行动",
            )

        self.assertEqual(
            [result["character"] for result in results],
            ["林默", "苏晚"],
        )
        self.assertEqual(
            results[0]["action_result"],
            "完成一次测试行动",
        )
        mock_print.assert_any_call("[Tick 1 | 08:00] 林默")
        mock_print.assert_any_call(
            "08:00 林默本轮没有执行工具：完成一次测试行动"
        )
        mock_print.assert_any_call("[Tick 2 | 08:05] 苏晚")

    def test_timeline_shows_real_relationship_change(self):
        old_value = CHARACTERS["林默"].relationships.get("苏晚", 0)

        with patch("builtins.print") as mock_print:
            run_world(1, lambda character: update_relationship(
                character.name, "苏晚", -3
            ))

        new_value = CHARACTERS["林默"].relationships["苏晚"]
        self.assertEqual(new_value, max(-100, old_value - 3))
        mock_print.assert_any_call(
            f"08:00 林默对苏晚的关系值从{old_value}变为{new_value}。"
        )
        mock_print.assert_any_call(
            f"重要记忆（林默）：我对苏晚的关系值从{old_value}变为{new_value}。"
        )

    def test_session_next_and_pause_keep_tick_order(self):
        started = Event()
        release = Event()

        def decide_action(character):
            if character.name == "苏晚":
                started.set()
                self.assertTrue(release.wait(5))
            return "完成测试行动"

        session = WorldSession(decide_action)
        with patch("builtins.print") as mock_print:
            first = session.next_tick()
            session.run_ten()
            try:
                self.assertTrue(started.wait(5))
                session.pause()
            finally:
                release.set()
                session.wait()
            third = session.next_tick()

        self.assertEqual(first["character"], "林默")
        self.assertEqual(third["character"], "赵无极")
        self.assertEqual(session.completed_ticks, 3)
        self.assertEqual(WORLD_STATE["time"], "08:15")
        mock_print.assert_any_call(
            "已启动连续运行，最多执行 10 个 Tick；输入 pause 可在当前 Tick 后停止。"
        )
        mock_print.assert_any_call("连续运行已停止，本次完成 1 / 10 个 Tick。")
        mock_print.assert_any_call("[Tick 3 | 08:10] 赵无极")

    def test_world_tick_uses_graph_to_execute_npc_tool(self):
        WORLD_STATE["time"] = "08:00"
        responses = iter([
            SimpleNamespace(
                output=[SimpleNamespace(
                    type="function_call",
                    name="move_character",
                    arguments='{"character":"林默","location":"晚风客栈"}',
                    call_id="tick-call-1",
                )],
                output_text="",
            ),
            SimpleNamespace(
                output=[],
                output_text="我已抵达客栈。\n原因：昨日线索指向客栈。",
            ),
        ])
        model_requests = []

        def fake_request_model(conversation, allow_tools):
            model_requests.append((list(conversation), allow_tools))
            return next(responses)

        with patch("builtins.print") as mock_print:
            results = run_world(1, make_graph_decide_action(fake_request_model))

        new_events = WORLD_STATE["events"][len(self.original_events):]
        self.assertEqual(results[0]["character"], "林默")
        self.assertEqual(
            results[0]["action_result"],
            "我已抵达客栈。\n原因：昨日线索指向客栈。",
        )
        self.assertEqual(CHARACTERS["林默"].location, "晚风客栈")
        self.assertEqual(WORLD_STATE["time"], "08:05")
        self.assertEqual([event["type"] for event in new_events], ["move"])
        mock_print.assert_any_call("08:00 林默从县衙移动到晚风客栈。")
        mock_print.assert_any_call("模型解释：昨日线索指向客栈。")
        self.assertEqual(len(model_requests), 2)


if __name__ == "__main__":
    unittest.main()
