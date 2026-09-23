import unittest

from agent.graph import build_model_prompt
from agent.state import create_initial_agent_state
from characters.model import Character
from characters.prompt import build_character_prompt
from memory.reflection import reflect_on_new_memories
from memory.retrieval import retrieve_character_memory
from memory.short_term import ShortTermMemory
from tools.world_tools import inspect, talk
from world.state import WORLD_STATE


def make_character(name: str, goal: str) -> Character:
    return Character(name, "", "", "", [goal], "晚风客栈", 90)


class SemanticRetrievalTest(unittest.TestCase):
    def test_old_relevant_memory_is_ranked_and_stays_private(self):
        lin_mo = make_character("林默", "查找失踪案线索")
        su_wan = make_character("苏晚", "经营客栈")
        lin_mo.memory = ShortTermMemory(max_items=2)
        lin_mo.memory.add("失踪案的旧线索在后门", importance=5)
        lin_mo.memory.add("我猜失踪案后门藏着宝物", tags=("narration",))
        lin_mo.memory.add("我吃了早饭", importance=1)
        lin_mo.memory.add("我回到街上")
        lin_mo.memory.add("我查看天气")

        result = retrieve_character_memory(lin_mo, "失踪案后门", max_items=1)

        self.assertEqual(result, ["历史经历：失踪案的旧线索在后门"])
        self.assertEqual(retrieve_character_memory(su_wan, "失踪案后门"), [])
        self.assertEqual(retrieve_character_memory(lin_mo, "失踪案后门", max_chars=3), [])
        self.assertIn("历史经历：失踪案的旧线索在后门", build_character_prompt(lin_mo, "后门有什么失踪案线索？"))
        self.assertNotIn("失踪案的旧线索在后门", build_character_prompt(su_wan, "后门有什么失踪案线索？"))

    def test_verified_inspection_updates_own_fact_and_action_prompt(self):
        original_characters = WORLD_STATE["characters"]
        original_events = WORLD_STATE["events"]
        objects = WORLD_STATE["inspectable_objects"]["晚风客栈"]
        original_description = objects["住客登记簿"]
        lin_mo = make_character("林默", "核查住客登记簿")
        su_wan = make_character("苏晚", "经营客栈")
        WORLD_STATE["characters"] = {"林默": lin_mo, "苏晚": su_wan}
        WORLD_STATE["events"] = []
        try:
            objects["住客登记簿"] = "登记簿写着甲住在二号房。"
            inspect("林默", "住客登记簿")
            first = lin_mo.semantic_memory.current_facts()[0]
            self.assertEqual(first.source_event_id, WORLD_STATE["events"][-1]["id"])
            self.assertEqual(first.owner, "林默")
            self.assertEqual(su_wan.semantic_memory.current_facts(), [])
            talk("苏晚", "林默", "听说登记簿里藏着金条。")
            self.assertEqual(len(lin_mo.semantic_memory.current_facts()), 1)
            self.assertEqual(su_wan.semantic_memory.current_facts(), [])
            reflect_on_new_memories(lin_mo.memory)

            objects["住客登记簿"] = "登记簿改为写着乙住在二号房。"
            inspect("林默", "住客登记簿")
            current = lin_mo.semantic_memory.current_facts()
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0].id, first.id)
            self.assertNotEqual(current[0].source_event_id, first.source_event_id)
            self.assertIn(first.source_event_id, lin_mo.semantic_memory.superseded_event_ids)
            prompt = build_model_prompt(create_initial_agent_state(lin_mo))
            self.assertIn("登记簿改为写着乙住在二号房", prompt)
            self.assertNotIn("登记簿写着甲住在二号房", prompt)

            for number in range(5):
                lin_mo.memory.add(f"后续经历{number}")
            prompt = build_model_prompt(create_initial_agent_state(lin_mo))
            self.assertIn("已核实调查：晚风客栈的住客登记簿：登记簿改为写着乙住在二号房。", prompt)
            self.assertNotIn("登记簿写着甲住在二号房", build_model_prompt(create_initial_agent_state(su_wan)))

            objects["住客登记簿"] = "登记簿写着甲住在二号房。"
            inspect("林默", "住客登记簿")
            current = lin_mo.semantic_memory.current_facts()
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0].id, first.id)
            self.assertNotEqual(current[0].source_event_id, first.source_event_id)
            updated_prompt = build_model_prompt(create_initial_agent_state(lin_mo))
            self.assertIn("登记簿写着甲住在二号房", updated_prompt)
            self.assertNotIn("登记簿改为写着乙住在二号房", updated_prompt)
        finally:
            objects["住客登记簿"] = original_description
            WORLD_STATE["characters"] = original_characters
            WORLD_STATE["events"] = original_events


if __name__ == "__main__":
    unittest.main()
