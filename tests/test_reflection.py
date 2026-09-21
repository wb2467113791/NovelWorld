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


if __name__ == "__main__":
    unittest.main()
