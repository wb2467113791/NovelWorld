import io
import unittest
from contextlib import redirect_stdout

from demo_v1 import run_demo
from world.state import WORLD_STATE


class DemoV1Test(unittest.TestCase):
    def test_twenty_ticks_change_real_state_and_restore_caller_world(self):
        original_time = WORLD_STATE["time"]
        original_characters = WORLD_STATE["characters"]
        original_events = WORLD_STATE["events"]

        with redirect_stdout(io.StringIO()) as output:
            summary = run_demo()

        self.assertEqual(summary["ticks"], 20)
        self.assertEqual(summary["end_time"], "09:40")
        self.assertEqual(sum(summary["events"].values()), 20)
        self.assertEqual(summary["events"]["give_item"], 1)
        self.assertIn("私人账本", summary["lin_mo_items"])
        self.assertNotIn("私人账本", summary["su_wan_items"])
        self.assertEqual(summary["relationships"]["苏晚→林默"], 2)
        self.assertIn("[Tick 20 | 09:35] 苏晚", output.getvalue())
        self.assertEqual(WORLD_STATE["time"], original_time)
        self.assertIs(WORLD_STATE["characters"], original_characters)
        self.assertIs(WORLD_STATE["events"], original_events)


if __name__ == "__main__":
    unittest.main()
