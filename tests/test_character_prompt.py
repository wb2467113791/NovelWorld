import unittest

from characters.presets import CHARACTERS
from characters.prompt import (
    build_action_prompt_for_character,
    build_character_prompt,
    build_prompt_for_character,
)
from tools.world_tools import update_relationship
from world.state import WORLD_STATE


class CharacterPromptTest(unittest.TestCase):
    def setUp(self):
        self.original_memories = {
            name: character.memory.recent()
            for name, character in CHARACTERS.items()
        }

    def tearDown(self):
        for name, entries in self.original_memories.items():
            CHARACTERS[name].memory.entries[:] = entries

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

    def test_prompt_contains_only_the_current_characters_recent_memory(self):
        CHARACTERS["林默"].memory.add("我在县衙发现了新的卷宗线索")
        CHARACTERS["赵无极"].memory.add("我命人转移了商会账本")

        prompt = build_character_prompt(CHARACTERS["林默"], "接下来做什么？")

        self.assertIn("【近期记忆】", prompt)
        self.assertIn("我在县衙发现了新的卷宗线索", prompt)
        self.assertNotIn("我命人转移了商会账本", prompt)

    def test_prompt_marks_empty_recent_memory_as_none(self):
        CHARACTERS["苏晚"].memory.entries.clear()

        prompt = build_character_prompt(CHARACTERS["苏晚"], "你记得什么？")

        self.assertIn("【近期记忆】\n- 暂无", prompt)

    def test_dialogue_prompt_requires_tool_for_real_conversation(self):
        prompt = build_character_prompt(CHARACTERS["林默"], "请与苏晚交谈")

        self.assertIn("请调用 talk 工具", prompt)
        self.assertIn("只有工具成功执行才算交谈发生", prompt)

    def test_action_prompt_contains_goal_state_knowledge_and_memory(self):
        character = CHARACTERS["林默"]
        character.memory.add("我刚整理过失踪案卷宗")
        try:
            prompt = build_action_prompt_for_character("林默")

            self.assertIn("调查失踪案", prompt)
            self.assertIn(f"世界时间：{WORLD_STATE['time']}", prompt)
            self.assertIn(f"所在地点：{character.location}", prompt)
            self.assertIn(f"体力：{character.energy}", prompt)
            self.assertIn("失踪案卷宗最后提到了晚风客栈", prompt)
            self.assertIn("我刚整理过失踪案卷宗", prompt)
            self.assertIn("决定此刻最合理的一步行动", prompt)
        finally:
            character.memory.entries.remove("我刚整理过失踪案卷宗")

    def test_action_prompt_does_not_leak_other_characters_secrets(self):
        prompt = build_action_prompt_for_character("林默")

        self.assertNotIn("她的弟弟与最近发生的失踪案有关", prompt)
        self.assertNotIn("他知道失踪案背后的交易", prompt)

    def test_action_prompt_rejects_unknown_character(self):
        with self.assertRaisesRegex(ValueError, "角色不存在"):
            build_action_prompt_for_character("王五")


if __name__ == "__main__":
    unittest.main()
