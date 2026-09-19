import unittest

from characters.model import Character
from characters.presets import CHARACTERS


class CharacterTest(unittest.TestCase):
    def test_three_character_presets_exist(self):
        self.assertEqual(set(CHARACTERS), {"林默", "苏晚", "赵无极"})
        self.assertTrue(all(isinstance(character, Character) for character in CHARACTERS.values()))

    def test_each_character_has_goal_and_independent_knowledge(self):
        for character in CHARACTERS.values():
            self.assertTrue(character.role)
            self.assertTrue(character.background)
            self.assertTrue(character.goals)
            self.assertTrue(character.location)
            self.assertGreater(character.energy, 0)
            self.assertIsInstance(character.known_facts, list)

    def test_world_state_reuses_the_preset_character_objects(self):
        from world.state import WORLD_STATE

        self.assertIs(WORLD_STATE["characters"]["苏晚"], CHARACTERS["苏晚"])

        self.assertIn("他知道失踪案背后的交易，并安排人销毁过证据", CHARACTERS["赵无极"].secrets)
        self.assertNotIn(
            "他知道失踪案背后的交易，并安排人销毁过证据",
            CHARACTERS["林默"].known_facts,
        )


if __name__ == "__main__":
    unittest.main()
