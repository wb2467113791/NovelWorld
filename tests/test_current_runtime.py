"""当前 Web 运行路径的关键边界；全部使用模型与服务替身。"""

import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.director import Director
from agent.graph import build_agent_loop_graph, execute_pending_tools
from agent.session import WorldSession
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.prompt import build_action_prompt
from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS, execute_tool
from world.persistence import restore_snapshot, snapshot_world
from tests.support import committed_event
from world.state import WORLD_STATE, reconcile_event_memories


class CurrentRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def test_tool_route_allows_wait_and_delegates_actions_to_java(self):
        backend = Mock()
        backend.execute.return_value = "Java 已结算"
        with patch("tools.remote_world.active_backend", return_value=backend):
            self.assertEqual(execute_tool("wait", {}, "林默"), "等待")
            backend.execute.assert_not_called()
            with self.assertRaisesRegex(ValueError, "替其他角色行动"):
                execute_tool("move_character", {"character": "苏晚", "location": "县衙"}, "林默")
            self.assertEqual(execute_tool("move_character", {"character": "林默", "location": "晚风客栈"}, "林默"),
                             "Java 已结算")
        backend.execute.assert_called_once_with(
            "move_character", {"character": "林默", "location": "晚风客栈"}, "林默")
        self.assertNotIn("get_character", {schema["name"] for schema in NPC_ACTION_TOOL_SCHEMAS})

    def test_graph_returns_java_tool_result_to_model_without_local_mutation(self):
        responses = iter([
            SimpleNamespace(output=[SimpleNamespace(type="function_call", name="move_character",
                arguments='{"character":"林默","location":"晚风客栈"}', call_id="move-1")], output_text=""),
            SimpleNamespace(output=[], output_text="我准备前往客栈。"),
        ])
        requests = []
        backend = Mock()
        backend.execute.return_value = "Java 已结算移动"
        index = Mock()
        index.retrieve_memory.return_value = []
        index.retrieve_lore.return_value = []

        def request_model(conversation, allow_tools):
            requests.append((list(conversation), allow_tools))
            return next(responses)

        with patch("tools.remote_world.active_backend", return_value=backend):
            result = build_agent_loop_graph(request_model).invoke(
                create_initial_agent_state(WORLD_STATE["characters"]["林默"], index))
        self.assertEqual(result["final_answer"], "我准备前往客栈。")
        self.assertEqual(result["tool_results"][0]["output"], "Java 已结算移动")
        self.assertEqual([allowed for _, allowed in requests], [True, False])
        self.assertEqual(requests[1][0][-1]["type"], "function_call_output")
        self.assertEqual(WORLD_STATE["characters"]["林默"].location, "县衙")

    def test_failed_tool_keeps_professional_guidance_without_claiming_progress(self):
        su = WORLD_STATE["characters"]["苏晚"]
        responses = iter([
            SimpleNamespace(output=[SimpleNamespace(type="function_call", name="take",
                arguments='{"character":"苏晚","object_id":"test-ledger"}', call_id="hide-1")], output_text=""),
            SimpleNamespace(output=[], output_text="线索已变化，我先等待。"),
        ])
        requests = []
        backend = Mock()

        def reject_changed_clue(*_):
            from world.objects import current_objects
            for item in current_objects().values():
                if item["portable"] and item["holder"] is None:
                    item["visible"] = False
            raise ValueError("线索已不在现场")

        backend.execute.side_effect = reject_changed_clue
        index = Mock()
        index.retrieve_memory.return_value = []
        index.retrieve_lore.return_value = []

        def request_model(conversation, allow_tools):
            requests.append((list(conversation), allow_tools))
            return next(responses)

        before = len(WORLD_STATE["events"])
        with patch("tools.remote_world.active_backend", return_value=backend):
            result = build_agent_loop_graph(request_model).invoke(create_initial_agent_state(su, index))
        self.assertEqual(result["final_answer"], "线索已变化，我先等待。")
        self.assertEqual(len(WORLD_STATE["events"]), before)
        self.assertIn("线索已不在现场", result["tool_results"][0]["output"])
        self.assertIn("保护与隐瞒专业知识", requests[1][0][-1]["content"])
        self.assertNotIn("建议参数", requests[1][0][-1]["content"])
        self.assertTrue(requests[1][1])

    def test_old_snapshot_without_concealment_fields_restores(self):
        snapshot = deepcopy(snapshot_world())
        snapshot.pop("objects")  # 模拟真正的旧存档；新存档只信任 objects。
        snapshot.pop("concealable_objects")
        snapshot.pop("concealed_objects")
        restore_snapshot(snapshot)
        self.assertEqual(WORLD_STATE["concealable_objects"], {})
        self.assertEqual(WORLD_STATE["concealed_objects"], {})

    def test_same_failed_tool_is_not_sent_to_java_twice_in_one_tick(self):
        index = Mock()
        index.retrieve_memory.return_value = []
        index.retrieve_lore.return_value = []
        state = create_initial_agent_state(WORLD_STATE["characters"]["苏晚"], index)
        call = {"name": "take", "arguments": '{"character":"苏晚","object_id":"test-ledger"}',
                "call_id": "retry"}
        state["pending_tool_calls"] = [call]
        state["tool_results"] = [{**call, "call_id": "first", "output": "工具错误：线索已不在现场"}]
        backend = Mock()
        with patch("tools.remote_world.active_backend", return_value=backend):
            result = execute_pending_tools(state)
        backend.execute.assert_not_called()
        self.assertIn("相同调用已失败", result["tool_results"][-1]["output"])

    def test_event_scheduler_wakes_only_witness_and_wait_does_not_loop(self):
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        patcher = patch("tools.remote_world.active_backend", return_value=backend)
        patcher.start()
        self.addCleanup(patcher.stop)
        scheduler = WorldTickScheduler()
        calls = []
        decide = lambda character: calls.append(character.name) or "等待"
        for _ in WORLD_STATE["characters"]:
            scheduler.run_tick(decide)
        self.assertEqual(scheduler.run_tick(decide)["character"], "世界")
        self.assertEqual(len(calls), len(WORLD_STATE["characters"]))

        location = WORLD_STATE["characters"]["苏晚"].location
        event = committed_event("intervention", "世界", "客栈出现新信", location=location)
        self.assertEqual(event["perceived_by"], ["苏晚"])
        self.assertEqual(scheduler.run_tick(decide)["character"], "苏晚")
        saved = scheduler.snapshot()
        restored = WorldTickScheduler()
        restored.restore(saved)
        # 新事件仍只唤醒知情者，等待不会自造事件循环；到期 Agenda 是独立的长期来源。
        next_result = restored.run_tick(decide)
        self.assertEqual((next_result["character"], next_result["source"]), ("林默", "agenda"))
        self.assertEqual(calls.count("苏晚"), 2)

    def test_director_only_proposes_after_rule_and_never_moves_npc(self):
        calls = []
        backend = Mock()
        def introduce(category, location, tick_count, observation):
            calls.append((category, location, observation))
            return committed_event("director", "世界", observation, location=location,
                                payload={"category": category, "tick_count": tick_count})
        backend.introduce_event.side_effect = introduce
        director = Director(propose_event=lambda category, location: "门边出现一封信")
        with patch("tools.remote_world.active_backend", return_value=backend):
            self.assertIsNone(director.maybe_inject(1))
            for actor in WORLD_STATE["characters"]:
                committed_event("inspect", actor, "重复观察", payload={"observation": "无变化"})
            before = {name: person.location for name, person in WORLD_STATE["characters"].items()}
            event = director.maybe_inject(3)
        self.assertEqual(event["perceived_by"], ["苏晚"])
        self.assertEqual(calls, [("stagnation", "晚风客栈", "门边出现一封信")])
        self.assertEqual(before, {name: person.location for name, person in WORLD_STATE["characters"].items()})

    def test_first_empty_tick_revives_world_after_scheduler_restore(self):
        backend = Mock()
        backend.advance_time.return_value = "09:35"
        backend.introduce_event.side_effect = lambda category, location, tick_count, observation: committed_event(
            "director", "世界", observation, location=location,
            payload={"category": category, "tick_count": tick_count})
        names = list(WORLD_STATE["characters"])
        for index, name in enumerate(names):
            committed_event("talk", name, f"各不相同的历史对话 {index}",
                            target=names[(index + 1) % len(names)],
                            payload={"message": f"历史对话 {index}"})
        director = Director(propose_event=lambda category, location: "客栈门边出现一封新信")
        decide = Mock(return_value="等待")
        with patch("tools.remote_world.active_backend", return_value=backend):
            scheduler = WorldTickScheduler(director=director)
            scheduler.restore({"tick_count": 17, "event_cursor": len(WORLD_STATE["events"]),
                               "pending": [], "current_depth": 0})
            restored = WorldTickScheduler(director=director)
            restored.restore(scheduler.snapshot())
            self.assertEqual(restored.run_tick(decide)["character"], "世界")
            event = WORLD_STATE["events"][-1]
            self.assertEqual(event["type"], "director")
            self.assertTrue(event["perceived_by"])
            backend.introduce_event.assert_called_once()
            self.assertEqual(restored.snapshot()["pending"][0]["name"], event["perceived_by"][0])
            self.assertEqual(restored.run_tick(decide)["character"], event["perceived_by"][0])
        decide.assert_called_once()

    def test_snapshot_replay_preserves_original_witnesses(self):
        location = WORLD_STATE["characters"]["苏晚"].location
        event = committed_event("intervention", "世界", "现场出现一封信", location=location)
        saved = deepcopy(snapshot_world(scheduler_state={"tick_count": 2}))
        restore_snapshot(saved)
        WORLD_STATE["characters"]["苏晚"].memory.entries.clear()
        WORLD_STATE["characters"]["林默"].location = location
        self.assertEqual(reconcile_event_memories(), 1)
        self.assertEqual(reconcile_event_memories(), 0)
        self.assertEqual(WORLD_STATE["characters"]["苏晚"].memory.recent_entries()[-1].source_event_id,
                         event["id"])
        self.assertFalse(WORLD_STATE["characters"]["林默"].memory.recent_entries())

    def test_session_saves_scheduler_after_idle_tick(self):
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        index = Mock()
        with patch("tools.remote_world.active_backend", return_value=backend), \
                patch("agent.session.active_backend", return_value=backend), \
                patch("agent.session.save_world") as save_world:
            session = WorldSession(lambda character: "等待", save_path=Path("unused.json"), index=index)
            session.next_tick()
        self.assertEqual(session.completed_ticks, 1)
        backend.save_agent_state.assert_called_once()
        save_world.assert_called_once()
        index.sync_world.assert_called_once()

    def test_action_prompt_contains_only_current_character_secret(self):
        lin = WORLD_STATE["characters"]["林默"]
        prompt = build_action_prompt(lin, active_goal=lin.goals[0], memories=[],
                                     retrieved_context=[], lore_context=[], observations=[])
        self.assertIn(lin.goals[0], prompt)
        self.assertNotIn(WORLD_STATE["characters"]["苏晚"].secrets[0], prompt)
