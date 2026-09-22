"""用真实 Graph 工具执行结果检查非法行动率。"""

import unittest
from types import SimpleNamespace

from agent.graph import build_agent_loop_graph
from agent.state import create_initial_agent_state
from characters.presets import CHARACTERS
from eval.metrics import (
    goal_consistency_stats,
    invalid_action_stats,
    knowledge_leakage_stats,
    repetition_stats,
)
from eval.scenarios import SCENARIOS
from world.state import WORLD_STATE


class InvalidActionMetricsTest(unittest.TestCase):
    def test_counts_rejected_action_but_not_time_query(self):
        lin_mo = CHARACTERS["林默"]
        original_location = lin_mo.location
        original_events = WORLD_STATE["events"].copy()
        original_memories = {
            name: character.memory.recent_entries()
            for name, character in CHARACTERS.items()
        }
        responses = iter([
            SimpleNamespace(output=[
                SimpleNamespace(
                    type="function_call", name="move_character",
                    arguments='{"character":"林默","location":"皇宫"}',
                    call_id="invalid-move",
                ),
                SimpleNamespace(
                    type="function_call", name="get_world_time",
                    arguments="{}", call_id="time-query",
                ),
                SimpleNamespace(
                    type="function_call", name="move_character",
                    arguments='{"character":"林默","location":"晚风客栈"}',
                    call_id="valid-move",
                ),
            ], output_text=""),
            SimpleNamespace(output=[], output_text="我已抵达客栈。"),
        ])

        try:
            graph = build_agent_loop_graph(
                lambda conversation, allow_tools: next(responses)
            )
            result = graph.invoke(create_initial_agent_state(lin_mo))
            stats = invalid_action_stats(result["tool_results"])

            self.assertEqual((stats.rejected, stats.attempted), (1, 2))
            self.assertEqual(stats.rate, 0.5)
            self.assertEqual(lin_mo.location, "晚风客栈")
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "move")
        finally:
            lin_mo.location = original_location
            WORLD_STATE["events"][:] = original_events
            for name, entries in original_memories.items():
                CHARACTERS[name].memory.entries[:] = entries

    def test_no_action_is_unmeasured(self):
        stats = invalid_action_stats([])
        self.assertEqual((stats.rejected, stats.attempted), (0, 0))
        self.assertIsNone(stats.rate)

    def test_remaining_metrics_use_model_output_human_labels_and_action_history(self):
        secret_case = next(s for s in SCENARIOS if s.id == "lin_does_not_know_zhao_secret")
        repeat_case = next(s for s in SCENARIOS if s.id == "lin_avoids_repeat_inspection")
        goal_cases = [s for s in SCENARIOS if s.focus == "goal_consistency"]
        secret = secret_case.forbidden_facts[0]
        inspect_result = {
            "name": "inspect", "arguments": '{"character": "林默"}',
            "call_id": "inspect-1", "output": "林默调查了晚风客栈。",
            "location_before": "晚风客栈",
        }

        leakage = knowledge_leakage_stats([
            (secret_case, [], f"我知道：{secret}"),
            (next(s for s in SCENARIOS if s.id == "lin_does_not_know_su_secret"), [], "继续查问。"),
        ])
        goals = goal_consistency_stats([
            (goal_cases[0], True), (goal_cases[1], False), (goal_cases[2], None)
        ])
        repetition = repetition_stats([(repeat_case, [inspect_result, inspect_result])])

        self.assertEqual((leakage.leaked_scenarios, leakage.checked_scenarios, leakage.rate), (1, 2, 0.5))
        self.assertEqual((goals.consistent, goals.reviewed, goals.pending, goals.rate), (1, 2, 1, 0.5))
        self.assertEqual((repetition.repeated, repetition.attempted, repetition.rate), (2, 2, 1.0))

        other_place = {**inspect_result, "location_before": "县衙"}
        self.assertEqual(
            repetition_stats([(repeat_case, [other_place, inspect_result])]).repeated,
            1,
        )

        # Python 工具结果即使含秘密，也不能被误算为模型主动泄漏。
        self.assertEqual(
            knowledge_leakage_stats([(secret_case, [{**inspect_result, "output": secret}], "继续调查。")]).leaked_scenarios,
            0,
        )


if __name__ == "__main__":
    unittest.main()
