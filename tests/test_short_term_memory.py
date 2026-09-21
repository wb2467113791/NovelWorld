import unittest

from characters.presets import CHARACTERS
from memory.short_term import ShortTermMemory


class ShortTermMemoryTest(unittest.TestCase):
    def test_memory_keeps_only_the_most_recent_items(self):
        memory = ShortTermMemory(max_items=3)

        memory.add("第一条记忆")
        memory.add("第二条记忆")
        memory.add("第三条记忆")
        memory.add("第四条记忆")

        self.assertEqual(
            memory.recent(),
            ["第二条记忆", "第三条记忆", "第四条记忆"],
        )

    def test_each_character_has_independent_memory(self):
        lin_mo_memory = CHARACTERS["林默"].memory
        su_wan_memory = CHARACTERS["苏晚"].memory

        self.assertIsNot(lin_mo_memory, su_wan_memory)

        lin_mo_memory.add("林默发现了一条新线索")
        try:
            self.assertIn("林默发现了一条新线索", lin_mo_memory.recent())
            self.assertNotIn("林默发现了一条新线索", su_wan_memory.recent())
        finally:
            lin_mo_memory.entries.clear()

    def test_memory_capacity_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "容量必须大于 0"):
            ShortTermMemory(max_items=0)

    def test_memory_keeps_metadata_with_each_entry(self):
        memory = ShortTermMemory(max_items=1)
        memory.add("旧记忆", importance=2)
        memory.add(
            "苏晚对我说了线索",
            importance=3,
            actors=("苏晚", "林默"),
            tags=("talk", "晚风客栈"),
        )

        entry = memory.recent_entries()[0]
        self.assertEqual(memory.recent(), ["苏晚对我说了线索"])
        self.assertEqual((entry.importance, entry.actors, entry.tags),
                         (3, ("苏晚", "林默"), ("talk", "晚风客栈")))

    def test_memory_rejects_invalid_importance(self):
        with self.assertRaisesRegex(ValueError, "1 到 5"):
            ShortTermMemory().add("错误记忆", importance=6)


if __name__ == "__main__":
    unittest.main()
