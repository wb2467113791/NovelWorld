import unittest

from agent.state import create_initial_agent_state
from characters.presets import CHARACTERS


class AgentStateTest(unittest.TestCase):
    def test_initial_state_contains_required_graph_fields(self):
        state = create_initial_agent_state(CHARACTERS["林默"])

        self.assertEqual(
            set(state),
            {
                "npc_id", "goal", "memories", "observations", "step",
                "pending_tool_calls", "tool_results", "conversation",
                "final_answer",
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
            state = create_initial_agent_state(character)

            self.assertEqual(state["memories"], character.memory.recent())
            self.assertIsNot(state["memories"], character.memory.entries)
        finally:
            character.memory.entries.remove("我发现卷宗里缺少一页")

    def test_initial_state_accepts_an_explicit_active_goal(self):
        state = create_initial_agent_state(
            CHARACTERS["林默"],
            goal="找到失踪者的下落",
        )

        self.assertEqual(state["goal"], "找到失踪者的下落")


if __name__ == "__main__":
    unittest.main()
