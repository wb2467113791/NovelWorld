import unittest
from types import SimpleNamespace
from unittest.mock import patch

from characters.presets import CHARACTERS
from run_world import make_graph_decide_action, run_world
from world.state import WORLD_STATE


class RunWorldTest(unittest.TestCase):
    def setUp(self):
        self.original_time = WORLD_STATE["time"]
        self.original_events = WORLD_STATE["events"].copy()
        self.original_locations = {
            name: character.location for name, character in CHARACTERS.items()
        }
        self.original_memories = {
            name: character.memory.recent() for name, character in CHARACTERS.items()
        }

    def tearDown(self):
        WORLD_STATE["time"] = self.original_time
        WORLD_STATE["events"][:] = self.original_events
        for name, character in CHARACTERS.items():
            character.location = self.original_locations[name]
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
        mock_print.assert_any_call(
            "[Tick 1 | 08:00] 林默 > 完成一次测试行动"
        )
        mock_print.assert_any_call(
            "[Tick 2 | 08:05] 苏晚 > 完成一次测试行动"
        )

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
            SimpleNamespace(output=[], output_text="我已抵达客栈。"),
        ])
        model_requests = []

        def fake_request_model(conversation, allow_tools):
            model_requests.append((list(conversation), allow_tools))
            return next(responses)

        with patch("builtins.print"):
            results = run_world(1, make_graph_decide_action(fake_request_model))

        new_events = WORLD_STATE["events"][len(self.original_events):]
        self.assertEqual(results[0]["character"], "林默")
        self.assertEqual(results[0]["action_result"], "我已抵达客栈。")
        self.assertEqual(CHARACTERS["林默"].location, "晚风客栈")
        self.assertEqual(WORLD_STATE["time"], "08:05")
        self.assertEqual([event["type"] for event in new_events], ["move"])
        self.assertEqual(len(model_requests), 2)


if __name__ == "__main__":
    unittest.main()
