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

        self.assertIn("商会最近一笔交易收益低于预期，他公开只说合作顺利，担心别人觉得自己判断失准。", CHARACTERS["赵无极"].secrets)
        self.assertNotIn(
            "商会最近一笔交易收益低于预期，他公开只说合作顺利，担心别人觉得自己判断失准。",
            CHARACTERS["林默"].known_facts,
        )


if __name__ == "__main__":
    unittest.main()
