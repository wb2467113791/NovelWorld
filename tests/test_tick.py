import unittest

from agent.tick import WorldTickScheduler
from tools.world_tools import move_character
from world.state import WORLD_STATE


class WorldTickSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.original_time = WORLD_STATE["time"]
        self.original_energy = {
            name: character.energy
            for name, character in WORLD_STATE["characters"].items()
        }
        self.original_locations = {
            name: character.location
            for name, character in WORLD_STATE["characters"].items()
        }
        self.original_memories = {
            name: character.memory.recent()
            for name, character in WORLD_STATE["characters"].items()
        }
        self.original_events = WORLD_STATE["events"].copy()

    def tearDown(self):
        WORLD_STATE["time"] = self.original_time
        for name, energy in self.original_energy.items():
            WORLD_STATE["characters"][name].energy = energy
        for name, location in self.original_locations.items():
            WORLD_STATE["characters"][name].location = location
        for name, memories in self.original_memories.items():
            WORLD_STATE["characters"][name].memory.entries[:] = memories
        WORLD_STATE["events"][:] = self.original_events

    def test_characters_take_turns_in_world_order(self):
        scheduler = WorldTickScheduler()

        chosen_names = [
            scheduler.choose_next_character().name
            for _ in range(4)
        ]

        self.assertEqual(chosen_names, ["林默", "苏晚", "赵无极", "林默"])

    def test_character_with_no_energy_is_skipped(self):
        WORLD_STATE["characters"]["苏晚"].energy = 0
        scheduler = WorldTickScheduler()

        chosen_names = [
            scheduler.choose_next_character().name
            for _ in range(3)
        ]

        self.assertEqual(chosen_names, ["林默", "赵无极", "林默"])

    def test_scheduler_rejects_tick_when_everyone_has_no_energy(self):
        for character in WORLD_STATE["characters"].values():
            character.energy = 0

        scheduler = WorldTickScheduler()

        with self.assertRaisesRegex(RuntimeError, "没有可行动的角色"):
            scheduler.choose_next_character()

    def test_run_tick_passes_selected_character_to_decider(self):
        scheduler = WorldTickScheduler()
        received_characters = []

        def fake_decide_action(character) -> str:
            received_characters.append(character)
            return "林默决定前往晚风客栈调查。"

        result = scheduler.run_tick(fake_decide_action)

        self.assertEqual(result["character"], "林默")
        self.assertEqual(
            result["action_result"],
            "林默决定前往晚风客栈调查。",
        )
        self.assertEqual(received_characters, [WORLD_STATE["characters"]["林默"]])
        self.assertEqual(WORLD_STATE["events"][-1]["type"], "narration")
        self.assertTrue(
            any(
                "林默决定前往晚风客栈调查。" in memory
                for memory in WORLD_STATE["characters"]["林默"].memory.recent()
            )
        )

    def test_each_run_tick_uses_the_next_character(self):
        WORLD_STATE["time"] = "08:00"
        scheduler = WorldTickScheduler()

        first_result = scheduler.run_tick(
            lambda character: "第一次行动"
        )
        second_result = scheduler.run_tick(
            lambda character: "第二次行动"
        )

        self.assertEqual(first_result["character"], "林默")
        self.assertEqual(second_result["character"], "苏晚")
        self.assertEqual(WORLD_STATE["time"], "08:10")

    def test_run_tick_can_update_world_event_and_related_memory(self):
        scheduler = WorldTickScheduler()

        def fake_decide_action(character) -> str:
            return move_character("林默", "晚风客栈")

        result = scheduler.run_tick(fake_decide_action)

        action_result = "林默从县衙移动到晚风客栈。"
        self.assertEqual(result["action_result"], action_result)
        self.assertEqual(
            WORLD_STATE["characters"]["林默"].location,
            "晚风客栈",
        )
        self.assertEqual(WORLD_STATE["events"][-1]["type"], "move")
        self.assertEqual(
            WORLD_STATE["events"][-1]["description"],
            action_result,
        )
        self.assertIn(
            action_result,
            WORLD_STATE["characters"]["林默"].memory.recent(),
        )
        self.assertNotIn(
            action_result,
            WORLD_STATE["characters"]["苏晚"].memory.recent(),
        )

    def test_run_ticks_continues_for_ten_ticks(self):
        scheduler = WorldTickScheduler()

        results = scheduler.run_ticks(
            10,
            lambda character: "完成一次行动",
        )

        self.assertEqual(len(results), 10)
        self.assertEqual(
            [result["character"] for result in results],
            [
                "林默",
                "苏晚",
                "赵无极",
                "林默",
                "苏晚",
                "赵无极",
                "林默",
                "苏晚",
                "赵无极",
                "林默",
            ],
        )

    def test_run_ticks_requires_a_positive_count(self):
        scheduler = WorldTickScheduler()

        with self.assertRaisesRegex(ValueError, "至少为 1"):
            scheduler.run_ticks(0, lambda character: "不会执行")


if __name__ == "__main__":
    unittest.main()
