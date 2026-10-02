"""Phase 2 双驱动调度：不请求真实 LLM、MySQL 或向量接口。"""

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.runtime import AgendaEntry, AgentRuntimeState, DEFAULT_AGENDA_DELAY
from agent.session import WorldSession, make_graph_decide_action
from agent.tick import MAX_REACTION_DEPTH, WorldTickScheduler
from tests.support import committed_event
from world.persistence import load_world, restore_snapshot, snapshot_world
from world.state import WORLD_STATE


class AgendaSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))
        for character in WORLD_STATE["characters"].values():
            character.runtime_state = AgentRuntimeState()
        self.backend = Mock()
        self.backend.advance_time.return_value = "08:05"
        patcher = patch("tools.remote_world.active_backend", return_value=self.backend)
        patcher.start()
        self.addCleanup(patcher.stop)
        session_patcher = patch("agent.session.active_backend", return_value=self.backend)
        session_patcher.start()
        self.addCleanup(session_patcher.stop)
        self.decide = Mock(return_value="等待")

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def character(self, name="林默"):
        return WORLD_STATE["characters"][name]

    def agenda(self, name="林默", due=0, intention="继续考虑自己的目标", status="pending"):
        entry = AgendaEntry(f"test-{name}-{len(self.character(name).runtime_state.agenda)}", name, due, intention, status)
        self.character(name).runtime_state.agenda.append(entry)
        return entry

    def scheduler(self, tick=0, pending=None):
        scheduler = WorldTickScheduler(director=None)
        scheduler.restore({"tick_count": tick, "event_cursor": len(WORLD_STATE["events"]),
                           "pending": pending or [], "current_depth": 0})
        return scheduler

    def test_due_agenda_wakes_without_event_or_director(self):
        entry = self.agenda()
        result = self.scheduler().run_tick(self.decide)
        self.assertEqual((result["character"], result["source"], result["agenda_id"]), ("林默", "agenda", entry.id))
        self.decide.assert_called_once_with(self.character())
        self.assertEqual(entry.status, "completed")
        self.assertEqual(WORLD_STATE["events"], [])
        self.backend.execute.assert_not_called()

    def test_event_priority_keeps_other_characters_agenda_pending(self):
        lin_entry = self.agenda()
        scheduler = self.scheduler()
        committed_event("intervention", "世界", "新线索", location="晚风客栈")
        result = scheduler.run_tick(self.decide)
        self.assertEqual((result["character"], result["source"]), ("苏晚", "event"))
        self.assertEqual((lin_entry.status, lin_entry.due_tick), ("pending", 0))
        self.assertEqual(scheduler.run_tick(self.decide)["agenda_id"], lin_entry.id)

    def test_same_actor_event_defers_due_agenda_without_duplicate_tick(self):
        entry = self.agenda()
        scheduler = self.scheduler()
        committed_event("talk", "苏晚", "询问林默", target="林默", payload={"message": "你好"})
        result = scheduler.run_tick(self.decide)
        self.assertEqual(result["source"], "event")
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.due_tick, 1 + DEFAULT_AGENDA_DELAY)
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")
        self.assertEqual(self.decide.call_count, 1)

    def test_future_agenda_waits_until_starting_tick_reaches_due(self):
        entry = self.agenda(due=2)
        scheduler = self.scheduler()
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")
        self.assertEqual(entry.status, "pending")
        self.decide.assert_not_called()
        self.assertEqual(scheduler.run_tick(self.decide)["agenda_id"], entry.id)

    def test_busy_blocks_agenda_until_equal_tick(self):
        entry = self.agenda()
        self.character().runtime_state.busy_until = 2
        scheduler = self.scheduler()
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")
        self.assertEqual(scheduler.run_tick(self.decide)["agenda_id"], entry.id)
        self.assertEqual(self.character().runtime_state.busy_until, 2)

    def test_busy_does_not_block_event_reaction_or_bootstrap(self):
        self.character().runtime_state.busy_until = 999
        scheduler = self.scheduler()
        committed_event("intervention", "世界", "新信", location="县衙")
        result = scheduler.run_tick(self.decide)
        self.assertEqual((result["character"], result["source"]), ("林默", "event"))
        bootstrap = WorldTickScheduler()
        self.assertEqual(bootstrap.run_tick(self.decide)["source"], "bootstrap")

    def test_due_order_is_deterministic_and_does_not_starve_first_tied_actor(self):
        # 插入顺序和 UUID 都不参与跨角色选择；先最早 due_tick，再按世界角色顺序。
        su = self.agenda("苏晚", due=2)
        lin = self.agenda("林默", due=2)
        zhao = self.agenda("赵无极", due=1)
        scheduler = self.scheduler(tick=2)
        results = [scheduler.run_tick(self.decide) for _ in range(3)]
        self.assertEqual([result["agenda_id"] for result in results], [zhao.id, lin.id, su.id])
        self.assertEqual([result["character"] for result in results], ["赵无极", "林默", "苏晚"])

    def test_wait_consumes_and_rearms_with_cooldown(self):
        entry = self.agenda()
        scheduler = self.scheduler()
        scheduler.run_tick(self.decide)
        pending = [item for item in self.character().runtime_state.agenda if item.status == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertNotEqual(pending[0].id, entry.id)
        self.assertEqual(pending[0].due_tick, 1 + DEFAULT_AGENDA_DELAY)
        for _ in range(DEFAULT_AGENDA_DELAY):
            self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")
        self.assertEqual(self.decide.call_count, 1)
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "agenda")
        self.assertEqual(entry.status, "completed")
        self.assertEqual(self.decide.call_count, 2)

    def test_exception_before_action_keeps_agenda_for_retry(self):
        entry = self.agenda()
        scheduler = self.scheduler()
        with self.assertRaisesRegex(RuntimeError, "模型失败"):
            scheduler.run_tick(Mock(side_effect=RuntimeError("模型失败")))
        self.assertEqual(entry.status, "pending")
        self.assertEqual(scheduler.snapshot()["tick_count"], 0)
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.backend.advance_time.assert_not_called()
        self.assertEqual(scheduler.run_tick(self.decide)["agenda_id"], entry.id)

    def test_committed_action_summary_failure_consumes_and_restart_does_not_replay(self):
        entry = self.agenda()
        scheduler = self.scheduler()
        def fail_after_action(character):
            committed_event("inspect", character.name, "检查现场", payload={"observation": "安静"})
            raise RuntimeError("总结失败")
        result = scheduler.run_tick(fail_after_action)
        self.assertIn("行动已发生", result["action_result"])
        self.assertEqual(entry.status, "completed")
        saved = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        restored = WorldTickScheduler()
        restored.restore(restore_snapshot(saved))
        self.assertEqual(restored.run_tick(self.decide)["source"], "idle")
        self.assertEqual(len(WORLD_STATE["events"]), 1)

    def test_clock_failure_after_action_also_preserves_consumption(self):
        entry = self.agenda()
        scheduler = self.scheduler()
        self.backend.advance_time.side_effect = RuntimeError("时钟请求失败")
        def action(character):
            committed_event("inspect", character.name, "检查", payload={"observation": "安静"})
            return "Java 已提交"
        with self.assertRaisesRegex(RuntimeError, "时钟请求失败"):
            scheduler.run_tick(action)
        self.assertEqual(entry.status, "completed")
        self.backend.advance_time.side_effect = None
        self.assertEqual(scheduler.run_tick(self.decide)["source"], "idle")

    def test_refresh_and_cognition_rebuild_do_not_lose_consumption(self):
        entry = self.agenda()
        scheduler = self.scheduler()
        def action(character):
            restore_snapshot(deepcopy(snapshot_world()))  # Java 工具后的 Character 刷新。
            current = self.character()
            current.runtime_state = current.runtime_state.revised(
                {"current_intention": "改为观察新信"}, character=current.name, goals=current.goals)
            committed_event("inspect", current.name, "检查", payload={"observation": "安静"})
            return "完成决策"
        scheduler.run_tick(action)
        current_agenda = self.character().runtime_state.agenda
        self.assertEqual(next(item for item in current_agenda if item.id == entry.id).status, "completed")
        self.assertEqual([item.intention for item in current_agenda if item.status == "pending"], ["改为观察新信"])

    def test_program_creation_deduplicates_and_uses_intention_plan_or_goal(self):
        for intention, plan, expected in (("经营客栈", "留意来客", "经营客栈"),
                                         (None, "留意来客", "留意来客"), (None, None, "保护弟弟")):
            with self.subTest(expected=expected):
                runtime = AgentRuntimeState(active_goal="保护弟弟", current_intention=intention, current_plan=plan)
                entry = runtime.schedule_next_agenda(character="苏晚", current_tick=8, goals=["保护弟弟"])
                self.assertEqual((entry.due_tick, entry.intention, entry.status), (11, expected, "pending"))
                self.assertIs(runtime.schedule_next_agenda(character="苏晚", current_tick=10, goals=["保护弟弟"]), entry)
                self.assertEqual(len(runtime.agenda), 1)

    def test_no_goal_or_unconscious_does_not_create_new_autonomous_agenda(self):
        self.character().goals = []
        bootstrap = WorldTickScheduler()
        bootstrap.run_tick(self.decide)
        self.assertEqual(self.character().runtime_state.agenda, [])
        self.character("苏晚").status = "unconscious"
        bootstrap.run_tick(self.decide)
        self.assertEqual(self.character("苏晚").runtime_state.agenda, [])
        entry = self.agenda("苏晚")
        self.assertEqual(self.scheduler().run_tick(self.decide)["source"], "idle")
        self.assertEqual(entry.status, "pending")

    def test_bootstrap_rearms_without_director_and_continues_multiple_cycles(self):
        scheduler = WorldTickScheduler(director=None)
        opening = [scheduler.run_tick(self.decide) for _ in WORLD_STATE["characters"]]
        self.assertTrue(all(result["source"] == "bootstrap" for result in opening))
        self.assertEqual(scheduler.snapshot()["pending"], [])
        results = [scheduler.run_tick(self.decide) for _ in range(16)]
        for name in WORLD_STATE["characters"]:
            self.assertGreaterEqual(sum(result["character"] == name and result["source"] == "agenda"
                                        for result in results), 3)
            self.assertEqual(sum(item.status == "pending" for item in self.character(name).runtime_state.agenda), 1)
        self.assertEqual(WORLD_STATE["events"], [])

    def test_agenda_selection_does_not_use_skill_steps_or_force_actions(self):
        self.agenda(intention="想继续考虑调查方向")
        with patch("skills.router.current_step", side_effect=AssertionError("Agenda 不能读取 Skill 步骤")):
            result = self.scheduler().run_tick(self.decide)
        self.assertEqual(result["source"], "agenda")
        self.decide.assert_called_once()
        self.backend.execute.assert_not_called()

    def test_reaction_depth_limit_survives_agenda_drive(self):
        entry = self.agenda()
        scheduler = self.scheduler(pending=[{"name": "苏晚", "depth": MAX_REACTION_DEPTH, "source": "event"}])
        def talk_at_limit(character):
            committed_event("talk", character.name, "达到反应上限", target="林默", payload={"message": "你好"})
            return "已交谈"
        scheduler.run_tick(talk_at_limit)
        self.assertFalse(any(item["source"] == "event" for item in scheduler.snapshot()["pending"]))
        result = scheduler.run_tick(self.decide)
        self.assertEqual(result["agenda_id"], entry.id)
        self.assertEqual(scheduler.snapshot()["current_depth"], 0)
        # 新一轮 Agenda 行动产生的事件可正常以 depth=1 唤醒知情者。
        self.agenda(due=scheduler.snapshot()["tick_count"])
        def talk_from_agenda(character):
            committed_event("talk", character.name, "主动问候", target="苏晚", payload={"message": "你好"})
            return "已交谈"
        scheduler.run_tick(talk_from_agenda)
        self.assertIn({"name": "苏晚", "depth": 1, "source": "event"}, scheduler.snapshot()["pending"])

    def test_graph_still_allows_only_one_successful_world_action_on_agenda_tick(self):
        self.agenda()
        scheduler = self.scheduler()
        calls = [SimpleNamespace(type="function_call", name="inspect", call_id=str(i),
                                 arguments='{"character":"林默"}') for i in range(2)]
        request = Mock(side_effect=[SimpleNamespace(output=calls, output_text=""),
                                    SimpleNamespace(output=[], output_text="观察后等待")])
        def java_result(*args):
            committed_event("inspect", "林默", "检查现场", payload={"observation": "安静"})
            return "Java 已结算"
        self.backend.execute.side_effect = java_result
        index = Mock()
        index.retrieve_memory.return_value = []
        index.retrieve_lore.return_value = []
        result = scheduler.run_tick(make_graph_decide_action(request, index))
        self.assertEqual(result["source"], "agenda")
        self.backend.execute.assert_called_once()
        self.assertFalse(request.call_args.args[1])
        self.assertEqual(len(WORLD_STATE["events"]), 1)

    def test_session_persists_consumed_and_next_agenda_and_restores_same_clock(self):
        entry = self.agenda()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            session = WorldSession(self.decide, save_path=path, index=Mock(),
                                   scheduler_state={"tick_count": 0, "pending": []})
            session.next_tick()
            expected = deepcopy(snapshot_world(scheduler_state=session.scheduler.snapshot()))
            restored = WorldTickScheduler()
            restored.restore(load_world(path))
            self.assertEqual(snapshot_world(scheduler_state=restored.snapshot()), expected)
            self.assertEqual(self.character().runtime_state.agenda[0].id, entry.id)
            self.assertEqual(self.character().runtime_state.agenda[0].status, "completed")
            self.assertEqual(restored.run_tick(self.decide)["source"], "idle")
        self.backend.save_agent_state.assert_called_once_with(session.scheduler.snapshot())

    def test_world_restore_does_not_import_other_world_due_agenda(self):
        self.agenda()
        first = deepcopy(snapshot_world(scheduler_state=self.scheduler().snapshot()))
        second = deepcopy(first)
        second["world_id"] = "phase2-other-world"
        second["characters"]["林默"]["runtime_state"]["agenda"] = []
        other = WorldTickScheduler()
        other.restore(restore_snapshot(second))
        self.assertEqual(other.run_tick(self.decide)["source"], "idle")
        restored = WorldTickScheduler()
        restored.restore(restore_snapshot(first))
        self.assertEqual(restored.run_tick(self.decide)["source"], "agenda")

    def test_session_finally_persists_pending_after_pre_action_failure(self):
        entry = self.agenda()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            session = WorldSession(Mock(side_effect=RuntimeError("模型失败")), save_path=path, index=Mock(),
                                   scheduler_state={"tick_count": 0, "pending": []})
            with self.assertRaisesRegex(RuntimeError, "模型失败"):
                session.next_tick()
            saved = load_world(path)
            self.assertEqual(saved["tick_count"], 0)
            self.assertEqual(self.character().runtime_state.agenda[0].status, "pending")
            self.assertEqual(self.character().runtime_state.agenda[0].id, entry.id)
        self.backend.save_agent_state.assert_called_once()

    def test_director_failure_does_not_desynchronize_session_clock_or_replay_agenda(self):
        entry = self.agenda()
        director = Mock()
        director.maybe_inject.side_effect = RuntimeError("Director 失败")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            session = WorldSession(self.decide, save_path=path, index=Mock(), director=director,
                                   scheduler_state={"tick_count": 0, "pending": []})
            with self.assertRaisesRegex(RuntimeError, "Director 失败"):
                session.next_tick()
            self.assertEqual(session.completed_ticks, 1)
            saved = load_world(path)
            self.assertEqual(saved["tick_count"], 1)
            self.assertEqual(self.character().runtime_state.agenda[0].status, "completed")
            self.assertEqual(self.character().runtime_state.agenda[0].id, entry.id)

    def test_done_and_cancelled_agendas_do_not_wake(self):
        self.agenda(status="completed")
        self.agenda(status="cancelled")
        self.assertEqual(self.scheduler().run_tick(self.decide)["source"], "idle")
        self.decide.assert_not_called()

    def test_legacy_pending_restores_and_sources_are_validated(self):
        self.agenda("苏晚")
        scheduler = self.scheduler(pending=[{"name": "林默", "depth": 0}])
        result = scheduler.run_tick(self.decide)
        self.assertEqual((result["character"], result["source"]), ("林默", "legacy"))
        self.assertEqual(self.character("苏晚").runtime_state.agenda[0].status, "pending")
        with self.assertRaisesRegex(ValueError, "待唤醒角色无效"):
            scheduler.restore({"tick_count": 0, "pending": [{"name": "林默", "depth": 0, "source": "agenda"}]})
