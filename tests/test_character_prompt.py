import unittest

from characters.presets import CHARACTERS
from characters.prompt import build_character_prompt, build_prompt_for_character
from tools.world_tools import update_relationship
from world.state import WORLD_STATE


class CharacterPromptTest(unittest.TestCase):
    def test_prompt_contains_current_character_identity_and_private_knowledge(self):
        su_wan = CHARACTERS["苏晚"]

        prompt = build_character_prompt(su_wan, "你知道什么？")

        self.assertIn("晚风客栈老板", prompt)
        self.assertIn(su_wan.background, prompt)
        self.assertIn(su_wan.personality, prompt)
        self.assertIn(su_wan.goals[0], prompt)
        self.assertIn(su_wan.known_facts[0], prompt)
        self.assertIn(su_wan.secrets[0], prompt)
        self.assertNotIn(CHARACTERS["赵无极"].secrets[0], prompt)

    def test_lin_mo_prompt_excludes_other_characters_secrets(self):
        prompt = build_character_prompt(CHARACTERS["林默"], "案件有什么线索？")

        self.assertNotIn(CHARACTERS["苏晚"].secrets[0], prompt)
        self.assertNotIn(CHARACTERS["赵无极"].secrets[0], prompt)

    def test_prompt_uses_relationships_from_current_world_state(self):
        relationships = WORLD_STATE["characters"]["苏晚"].relationships
        original_value = relationships["林默"]
        original_events = WORLD_STATE["events"].copy()
        try:
            update_relationship("苏晚", "林默", -5)

            prompt = build_character_prompt(CHARACTERS["苏晚"], "你怎么看林默？")

            self.assertIn("对林默的关系值为-5", prompt)
        finally:
            relationships["林默"] = original_value
            WORLD_STATE["events"][:] = original_events

    def test_each_character_prompt_has_an_independent_information_view(self):
        for character_name, character in CHARACTERS.items():
            with self.subTest(character=character_name):
                prompt = build_prompt_for_character(character_name, "你知道什么？")

                for own_fact in character.known_facts + character.secrets:
                    self.assertIn(own_fact, prompt)

                for other_name, other_character in CHARACTERS.items():
                    if other_name == character_name:
                        continue
                    for unknown_fact in (
                        other_character.known_facts + other_character.secrets
                    ):
                        self.assertNotIn(unknown_fact, prompt)

    def test_prompt_rejects_unknown_character(self):
        with self.assertRaisesRegex(ValueError, "角色不存在"):
            build_prompt_for_character("王五", "你是谁？")


if __name__ == "__main__":
    unittest.main()
