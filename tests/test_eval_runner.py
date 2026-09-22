"""离线运行全部固定场景，检查状态隔离和角色视角。"""

import unittest
from types import SimpleNamespace

from eval.runner import run_scenario
from eval.scenarios import SCENARIOS
from world.state import WORLD_STATE


class ScenarioRunnerTest(unittest.TestCase):
    def test_all_scenarios_run_without_leaking_setup_or_mutating_world(self):
        original_characters = WORLD_STATE["characters"]
        original_events = WORLD_STATE["events"]
        original_time = WORLD_STATE["time"]
        prompts = {}

        for scenario in SCENARIOS:
            def fake_model(conversation, allow_tools):
                prompts[scenario.id] = conversation[0]["content"]
                return SimpleNamespace(output=[], output_text="本轮先观察。")

            run = run_scenario(scenario, fake_model)
            self.assertEqual(run.final_answer, "本轮先观察。")
            self.assertEqual(run.tool_results, [])
            self.assertIs(WORLD_STATE["characters"], original_characters)
            self.assertIs(WORLD_STATE["events"], original_events)
            self.assertEqual(WORLD_STATE["time"], original_time)

        self.assertIn("我刚调查了晚风客栈", prompts["lin_avoids_repeat_inspection"])
        self.assertIn("有人建议去皇宫", prompts["lin_invalid_destination"])
        for scenario in SCENARIOS:
            for secret in scenario.forbidden_facts:
                self.assertNotIn(secret, prompts[scenario.id])
            self.assertNotIn(scenario.expected_behavior, prompts[scenario.id])

    def test_real_tool_change_stays_inside_one_scenario(self):
        scenario = next(s for s in SCENARIOS if s.id == "lin_follows_inn_clue")
        original_character = WORLD_STATE["characters"]["林默"]
        original_location = original_character.location
        original_events = WORLD_STATE["events"]
        responses = iter([
            SimpleNamespace(output=[SimpleNamespace(
                type="function_call", name="move_character",
                arguments='{"character":"林默","location":"晚风客栈"}',
                call_id="move-1",
            )], output_text=""),
            SimpleNamespace(output=[], output_text="我到了客栈。"),
        ])

        run = run_scenario(scenario, lambda conversation, allow_tools: next(responses))

        self.assertIn("移动到晚风客栈", run.tool_results[0]["output"])
        self.assertEqual(run.final_answer, "我到了客栈。")
        self.assertIs(WORLD_STATE["characters"]["林默"], original_character)
        self.assertEqual(original_character.location, original_location)
        self.assertIs(WORLD_STATE["events"], original_events)


if __name__ == "__main__":
    unittest.main()
