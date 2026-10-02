"""Phase 5A：仅验证正式 Runtime 与迁移边界，使用 deterministic 服务替身。"""
import json
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from agent.director import Director
from agent.tick import WorldTickScheduler
from characters.prompt import build_action_prompt
from memory.retrieval import eligible_archived_entries
from skills.router import choose_skill
from tools.remote_world import RemoteWorld
from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS, execute_tool
from web_api import WorldController
from world.objects import current_objects
from world.persistence import restore_snapshot, snapshot_world
from world.state import WORLD_STATE


class LegacyCleanupTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))
        self.backend = Mock()
        self.backend.advance_time.return_value = "08:05"
        self.patcher = patch("tools.remote_world.active_backend", return_value=self.backend)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def test_missing_pending_in_old_save_does_not_bootstrap_again(self):
        scheduler = WorldTickScheduler(director=None)
        scheduler.restore({"tick_count": 50, "skill_views": {"林默": {"tool": "inspect"}}})
        decide = Mock(return_value="等待")
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.assertEqual(scheduler.run_tick(decide)["source"], "idle")
        decide.assert_not_called()
        self.assertNotIn("skill_views", scheduler.snapshot())

    def test_saved_bootstrap_runs_once_then_only_agenda(self):
        scheduler = WorldTickScheduler(director=None)
        opening = scheduler.snapshot()
        scheduler.restore(opening)
        first = [scheduler.run_tick(lambda _: "等待") for _ in WORLD_STATE["characters"]]
        self.assertTrue(all(result["source"] == "bootstrap" for result in first))
        restored = WorldTickScheduler(director=None)
        restored.restore(restore_snapshot(deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))))
        results = [restored.run_tick(lambda _: "等待") for _ in range(20)]
        self.assertFalse(any(result["source"] in {"bootstrap", "skill"} for result in results))
        self.assertEqual(set(WORLD_STATE["characters"]), {result["character"] for result in results if result["source"] == "agenda"})

    def test_first_local_import_explicitly_supplies_bootstrap_but_existing_java_world_wins(self):
        path = Mock()
        path.exists.return_value = False
        existing = deepcopy(snapshot_world(scheduler_state={"tick_count": 20}))
        for remote_exists in (False, True):
            with self.subTest(remote_exists=remote_exists):
                controller = WorldController()
                backend = Mock()
                backend.open.side_effect = lambda seed: deepcopy(existing) if remote_exists else seed
                with patch("web_api.DEFAULT_SAVE_PATH", path), patch("web_api.save_world"), \
                        patch("tools.remote_world.RemoteWorld", return_value=backend), \
                        patch("tools.remote_world.use_backend"), patch.object(controller, "_new_session") as session:
                    controller.initialize()
                seed = backend.open.call_args.args[0]
                self.assertTrue(all(item["source"] == "bootstrap" for item in seed["scheduler"]["pending"]))
                restored = session.call_args.args[0]
                if remote_exists:
                    self.assertEqual(restored, {"tick_count": 20})
                else:
                    self.assertEqual(len(restored["pending"]), len(WORLD_STATE["characters"]))

    def test_old_skill_pending_migrates_to_agenda_and_is_not_reserialized(self):
        scheduler = WorldTickScheduler(director=None)
        person = WORLD_STATE["characters"]["林默"]
        existing = person.runtime_state.schedule_next_agenda(character=person.name, current_tick=100, goals=person.goals)
        scheduler.restore({"tick_count": 12, "pending": [{"name": person.name, "depth": 0, "source": "skill"}],
                           "skill_views": {person.name: {"phase": "旧阶段"}}})
        self.assertEqual(person.runtime_state.agenda, [existing])
        self.assertEqual(existing.due_tick, 12)
        self.assertEqual(scheduler.snapshot()["pending"], [])
        result = scheduler.run_tick(lambda _: "等待")
        self.assertEqual((result["source"], result["agenda_id"]), ("agenda", existing.id))
        self.assertNotIn("skill_views", scheduler.snapshot())

    def test_legacy_event_source_keeps_reaction_priority_over_migrated_skill(self):
        scheduler = WorldTickScheduler()
        scheduler.restore({"tick_count": 5, "pending": [{"name": "林默", "depth": 0, "source": "skill"},
                                                       {"name": "苏晚", "depth": 1}]})
        self.assertEqual(scheduler.run_tick(lambda _: "等待")["source"], "legacy")
        self.assertEqual(scheduler.run_tick(lambda _: "等待")["source"], "agenda")

    def test_skill_migration_stays_in_current_world(self):
        first = deepcopy(snapshot_world())
        second = deepcopy(first)
        second["world_id"] = "cleanup-other-world"
        scheduler = WorldTickScheduler()
        scheduler.restore({"tick_count": 4, "pending": [{"name": "林默", "depth": 0, "source": "skill"}]})
        migrated = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        restore_snapshot(second)
        self.assertEqual(WORLD_STATE["characters"]["林默"].runtime_state.agenda, [])
        restore_snapshot(migrated)
        self.assertEqual(len(WORLD_STATE["characters"]["林默"].runtime_state.agenda), 1)

    def test_formal_tools_reject_removed_plot_tools_and_hide_old_aliases(self):
        schema = {entry["name"]: entry for entry in NPC_ACTION_TOOL_SCHEMAS}
        self.assertNotIn("give_item", schema)
        for name in ("conceal_clue", "recover_clue", "give_item", "update_relationship"):
            with self.assertRaises(ValueError):
                execute_tool(name, {"character": "苏晚"}, "苏晚")
        for action in ("use_item", "interact"):
            with self.assertRaises(ValueError):
                execute_tool("world_action", {"actor": "林默", "action": action}, "林默")
        self.backend.execute.assert_not_called()
        self.assertNotIn("object_name", schema["inspect"]["parameters"]["properties"])
        self.assertEqual(schema["world_action"]["parameters"]["properties"]["action"]["enum"], ["attack", "flee", "follow"])

    def test_old_views_and_items_do_not_control_holder_visibility_or_skill(self):
        objects = current_objects()
        person = WORLD_STATE["characters"]["苏晚"]
        before = deepcopy(objects)
        for item in objects.values():
            item["properties"].pop("legacy_concealable", None)
        canonical = deepcopy(objects)
        person.items = ["凭空物件"]
        WORLD_STATE["inspectable_objects"] = {}
        WORLD_STATE["concealable_objects"] = {}
        WORLD_STATE["concealed_objects"] = {person.location: {"住客登记簿": {"observation": "伪造隐藏状态"}}}
        person.goals = ["保护私人信息"]
        person.runtime_state.active_goal = "保护私人信息"
        self.assertEqual(choose_skill(person), "concealment")
        prompt = build_action_prompt(person, active_goal=person.goals[0], memories=[], retrieved_context=[], lore_context=[], observations=[])
        self.assertIn("【角色技能知识】", prompt)
        self.assertNotIn("凭空物件", prompt)
        self.assertNotIn("伪造隐藏状态", prompt)
        self.assertNotIn("recover_clue", prompt)
        self.assertNotIn("conceal_clue", prompt)
        self.assertEqual(canonical, objects)
        saved = snapshot_world()
        self.assertFalse({"inspectable_objects", "concealable_objects", "concealed_objects"} & saved.keys())
        self.assertEqual(before.keys(), objects.keys())

    def test_old_narration_is_readable_but_does_not_wake_or_drive_director(self):
        old = deepcopy(snapshot_world())
        for i, actor in enumerate(WORLD_STATE["characters"]):
            old["events"].append(dict(id=f"legacy-text-{i}", type="narration", actor=actor, target=None,
                                      location=old["characters"][actor]["location"], timestamp="08:00",
                                      payload={}, description="我声称拿起了钥匙", perceived_by=[actor]))
        restore_snapshot(old)
        scheduler = WorldTickScheduler(director=None)
        scheduler.restore({"tick_count": 3, "event_cursor": 0, "pending": []})
        self.assertEqual(scheduler.run_tick(lambda _: "等待")["source"], "idle")
        self.assertEqual(len(WORLD_STATE["events"]), 3)
        director = Director(Mock())
        self.assertIsNone(director.choose_event(3))
        self.assertEqual(WORLD_STATE["events"], old["events"])
        # legacy history only：废弃 Tool 的已提交 Event 仍可恢复并生成摘要。
        from memory.event_summary import summarize_event
        for kind in ("give_item", "conceal", "recover", "relationship", "use_item"):
            event = dict(id=f"legacy-{kind}", type=kind, actor="林默", target="苏晚",
                         location="县衙", timestamp="08:00", perceived_by=["林默"],
                         payload={"item": "旧物品", "old_value": 0, "new_value": 1}, description="旧历史")
            old["events"].append(event)
            self.assertTrue(summarize_event(event, "林默"))
        restore_snapshot(old)
        self.assertEqual(old["events"], snapshot_world()["events"])


    def test_save_and_refresh_never_forward_python_narration_as_world_events(self):
        remote = deepcopy(snapshot_world())
        WORLD_STATE["events"].append(dict(id="local-fake", type="narration", actor="林默", target=None,
                                         location="县衙", payload={}, timestamp="08:00", description="伪造物理效果"))
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call", return_value="saved") as call:
            backend.save_agent_state({"tick_count": 4})
        self.assertNotIn("events", json.loads(call.call_args.args[1]["agentStateJson"]))
        with patch.object(backend, "_call", return_value=json.dumps(remote, ensure_ascii=False)):
            backend._refresh_business_state()
        self.assertEqual(remote["events"], WORLD_STATE["events"])
        for person in WORLD_STATE["characters"].values():
            self.assertTrue(all("narration" not in entry.tags for _, entry in eligible_archived_entries(person)))


if __name__ == "__main__":
    unittest.main()
