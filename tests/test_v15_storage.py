"""V1.5 的隔离、恢复和索引重建核心风险。"""

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agent.tick import WorldTickScheduler
from characters.prompt import build_character_prompt
from lore.catalog import retrieve_lore
from run_world import WorldSession
from world.persistence import load_world, save_world, start_new_world
from world.state import WORLD_STATE, record_event, reconcile_event_memories


class V15StorageTest(unittest.TestCase):
    def setUp(self):
        self.original = deepcopy(WORLD_STATE)
        start_new_world()

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def test_snapshot_restores_events_memories_and_turn_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            scheduler = WorldTickScheduler()
            scheduler.run_tick(lambda character: "本轮观察完成")
            record_event("narration", "林默", "仅用于恢复测试")
            record_event("inspect", "林默", "林默核对了案卷", location="县衙",
                         payload={"object_name": None, "observation": "卷宗缺少一页"})
            original_id = WORLD_STATE["world_id"]
            original_memory = WORLD_STATE["characters"]["林默"].memory.recent()
            WORLD_STATE["characters"]["林默"].memory.reflection_cursor = 2
            save_world(path, scheduler_state=scheduler.snapshot())
            start_new_world()
            self.assertNotEqual(WORLD_STATE["world_id"], original_id)
            restored = load_world(path)
            resumed = WorldTickScheduler()
            resumed.restore(restored)
            self.assertEqual(WORLD_STATE["world_id"], original_id)
            self.assertEqual(WORLD_STATE["characters"]["林默"].memory.recent(), original_memory)
            self.assertIsInstance(WORLD_STATE["characters"]["林默"].memory.recent_entries()[0].tags, tuple)
            self.assertEqual(WORLD_STATE["characters"]["林默"].memory.reflection_cursor, 2)
            self.assertEqual(WORLD_STATE["characters"]["林默"].semantic_memory.current_facts()[0].observation,
                             "卷宗缺少一页")
            self.assertEqual(resumed.choose_next_character().name, "苏晚")

    def test_lore_visibility_in_dialogue(self):
        private = "县衙办案时应先核对卷宗原文"
        self.assertTrue(any(private in item for item in retrieve_lore("林默", "县衙卷宗")))
        self.assertNotIn(private, build_character_prompt(WORLD_STATE["characters"]["苏晚"], "县衙卷宗"))

    def test_tool_event_is_saved_even_if_decision_then_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            def failing_decision(character):
                record_event("narration", character.name, "工具执行后的事件")
                raise RuntimeError("模型响应中断")

            session = WorldSession(failing_decision, save_path=path)
            result = session.next_tick()
            self.assertIn("行动已发生", result["action_result"])
            load_world(path)
            self.assertEqual(WORLD_STATE["events"][-1]["description"], "工具执行后的事件")
            self.assertEqual(session.completed_ticks, 1)

    def test_replay_restores_only_original_witnesses_once(self):
        lin = WORLD_STATE["characters"]["林默"]
        su = WORLD_STATE["characters"]["苏晚"]
        zhao = WORLD_STATE["characters"]["赵无极"]
        lin.location = su.location
        event = record_event("move", "林默", "林默来到客栈", location=su.location,
                             payload={"from": "县衙", "to": su.location})
        self.assertEqual(event["perceived_by"], ["林默", "苏晚"])
        lin.memory.entries.clear()
        su.memory.entries.clear()
        zhao.location = su.location  # 事件之后才到场，不能补看旧事件。
        self.assertEqual(reconcile_event_memories(), 2)
        self.assertEqual(reconcile_event_memories(), 0)
        self.assertTrue(any(entry.source_event_id == event["id"] for entry in su.memory.recent_entries()))
        self.assertFalse(any(entry.source_event_id == event["id"] for entry in zhao.memory.recent_entries()))

    def test_chroma_rebuild_and_world_isolation(self):
        from retrieval.chroma_index import ChromaIndex

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            first = ChromaIndex(WORLD_STATE["world_id"], Path(directory))
            character = WORLD_STATE["characters"]["林默"]
            for number in range(7):
                character.memory.add(f"客栈后门线索{number}" if number == 0 else f"其他事件{number}", importance=4)
            first.sync_world(WORLD_STATE["characters"])
            count = first.memories.count()
            first.sync_world(WORLD_STATE["characters"])
            self.assertEqual(first.memories.count(), count)
            reopened = ChromaIndex(WORLD_STATE["world_id"], Path(directory))
            self.assertTrue(any("后门线索" in item for item in reopened.retrieve_memory(character, "客栈后门")))
            self.assertEqual(reopened.retrieve_memory(WORLD_STATE["characters"]["苏晚"], "客栈后门"), [])
            self.assertFalse(any("县衙办案时" in item for item in reopened.retrieve_lore("苏晚", "县衙卷宗")))
            snapshot = Path(directory) / "world.json"
            save_world(snapshot)
            start_new_world()
            load_world(snapshot)
            rebuilt = ChromaIndex(WORLD_STATE["world_id"], Path(directory) / "rebuilt")
            rebuilt.sync_world(WORLD_STATE["characters"])
            restored_actor = WORLD_STATE["characters"]["林默"]
            self.assertTrue(any("后门线索" in item for item in rebuilt.retrieve_memory(restored_actor, "客栈后门")))
            start_new_world()
            other = ChromaIndex(WORLD_STATE["world_id"], Path(directory))
            self.assertEqual(other.memories.count(), 0)


if __name__ == "__main__":
    unittest.main()
