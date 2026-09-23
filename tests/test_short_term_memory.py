import unittest

from characters.model import Character
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

    def test_evicted_memory_is_archived_with_its_metadata(self):
        memory = ShortTermMemory(max_items=1)
        memory.add("旧线索", importance=4, actors=("林默",), tags=("inspect",))
        memory.add("新线索")

        self.assertEqual(memory.recent(), ["新线索"])
        archived = memory.archived_entries()
        self.assertEqual(len(archived), 1)
        self.assertEqual(
            (archived[0].content, archived[0].importance, archived[0].actors, archived[0].tags),
            ("旧线索", 4, ("林默",), ("inspect",)),
        )
        archived.clear()
        self.assertEqual(len(memory.archived_entries()), 1)

    def test_archives_belong_to_separate_characters(self):
        lin_mo = Character("林默", "捕快", "", "", [], "县衙", 90)
        su_wan = Character("苏晚", "掌柜", "", "", [], "晚风客栈", 80)
        for number in range(6):
            lin_mo.memory.add(f"林默的第{number}条线索")

        self.assertEqual(len(lin_mo.memory.recent()), 5)
        self.assertEqual(lin_mo.memory.archived_entries()[0].content, "林默的第0条线索")
        self.assertEqual(su_wan.memory.archived_entries(), [])

    def test_memory_rejects_invalid_importance(self):
        with self.assertRaisesRegex(ValueError, "1 到 5"):
            ShortTermMemory().add("错误记忆", importance=6)


if __name__ == "__main__":
    unittest.main()
