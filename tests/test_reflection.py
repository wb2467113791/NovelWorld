import unittest

from memory.reflection import reflect_on_new_memories
from memory.short_term import ShortTermMemory


class ReflectionTest(unittest.TestCase):
    def test_reflection_selects_important_new_experiences_once(self):
        memory = ShortTermMemory()
        memory.add("我走到了客栈", importance=2, actors=("林默",))
        memory.add("我发现失踪案线索", importance=5, actors=("林默",), tags=("inspect",))
        memory.add("我又走到了街上", importance=2, actors=("林默",))
        memory.add("本轮没有执行工具", importance=5, tags=("narration",))

        reflection = reflect_on_new_memories(memory)

        self.assertIn("我发现失踪案线索", reflection)
        self.assertIn("我又走到了街上", reflection)
        self.assertNotIn("我走到了客栈", reflection)
        self.assertNotIn("本轮没有执行工具", reflection)
        self.assertEqual(memory.recent_entries()[-1].tags, ("reflection",))
        self.assertEqual(memory.recent_entries()[-1].actors, ("林默",))
        self.assertIsNone(reflect_on_new_memories(memory))

    def test_reflection_uses_archived_experiences_and_advances_progress(self):
        memory = ShortTermMemory(max_items=2)
        memory.add("最早的重要线索", importance=5, tags=("inspect",))
        memory.add("较早的行动", importance=2)
        memory.add("最近的行动", importance=2)

        first = reflect_on_new_memories(memory)
        self.assertIn("最早的重要线索", first)
        self.assertIsNone(reflect_on_new_memories(memory))

        memory.add("新的重要线索", importance=5, tags=("inspect",))
        second = reflect_on_new_memories(memory)
        self.assertIn("新的重要线索", second)
        self.assertNotIn("最早的重要线索", second)
        self.assertIsNone(reflect_on_new_memories(memory))

    def test_reflection_skips_an_observation_replaced_by_new_inspection(self):
        memory = ShortTermMemory(max_items=2)
        memory.add("旧调查结果", importance=5, source_event_id="old")
        memory.add("新调查结果", importance=3, source_event_id="new")

        reflection = reflect_on_new_memories(
            memory, superseded_event_ids={"old"}
        )

        self.assertIn("新调查结果", reflection)
        self.assertNotIn("旧调查结果", reflection)
        self.assertEqual(memory.recent_entries()[-1].derived_event_ids, ("new",))


if __name__ == "__main__":
    unittest.main()
