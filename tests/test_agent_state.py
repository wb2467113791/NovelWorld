import unittest
from unittest.mock import Mock

from agent.state import create_initial_agent_state
from characters.presets import CHARACTERS


class AgentStateTest(unittest.TestCase):
    def setUp(self):
        self.index = Mock()
        self.index.retrieve_memory.return_value = []
        self.index.retrieve_lore.return_value = []

    def test_initial_state_contains_required_graph_fields(self):
        state = create_initial_agent_state(CHARACTERS["林默"], self.index)

        self.assertEqual(
            set(state),
            {
                "npc_id", "goal", "runtime_context", "memories", "retrieved_context", "lore_context", "perception", "observations", "step",
                "pending_tool_calls", "tool_results", "conversation",
                "final_answer", "continue_conversation",
            },
        )
        self.assertEqual(state["npc_id"], "林默")
        self.assertEqual(state["goal"], "调查失踪案")
        self.assertEqual(state["observations"], [])
        self.assertEqual(state["step"], 0)
        self.assertEqual(state["pending_tool_calls"], [])
        self.assertEqual(state["tool_results"], [])
        self.assertEqual(state["conversation"], [])
        self.assertIsNone(state["final_answer"])

    def test_initial_state_copies_current_character_memories(self):
        character = CHARACTERS["林默"]
        character.memory.add("我发现卷宗里缺少一页")
        try:
            state = create_initial_agent_state(character, self.index)

            self.assertEqual(state["memories"], character.memory.recent())
            self.assertIsNot(state["memories"], character.memory.entries)
        finally:
            character.memory.entries.pop()

if __name__ == "__main__":
    unittest.main()
