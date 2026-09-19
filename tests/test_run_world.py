import unittest
from unittest.mock import patch

from run_world import run_world
from world.state import WORLD_STATE


class RunWorldTest(unittest.TestCase):
    def test_run_world_prints_results_without_real_model(self):
        original_time = WORLD_STATE["time"]
        try:
            with patch("builtins.print") as mock_print:
                results = run_world(
                    2,
                    lambda character, prompt: "完成一次测试行动",
                )
        finally:
            WORLD_STATE["time"] = original_time

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


if __name__ == "__main__":
    unittest.main()
