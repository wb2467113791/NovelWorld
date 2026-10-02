"""Conversation 与 Java 已提交事件、调度、保存和知识边界；不调用真实 LLM。"""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.conversation import (CONVERSATION_TIMEOUT, MAX_CONVERSATION_TURNS, DecisionResult,
                                accept_talk, context_for, for_participant, sessions)
from agent.graph import build_agent_loop_graph, build_model_prompt
from agent.runtime import AgentRuntimeState, AgendaEntry
from agent.session import WorldSession, make_graph_decide_action
from agent.state import create_initial_agent_state
from agent.tick import MAX_REACTION_DEPTH, WorldTickScheduler
from characters.model import Character
from tests.support import committed_event
from tools.remote_world import RemoteWorld
from tools.world_tools import execute_tool
from world.persistence import load_world, restore_snapshot, save_world, snapshot_world
from world.state import WORLD_STATE


class ConversationTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))
        WORLD_STATE["active_conversations"] = []
        WORLD_STATE["events"] = []
        for person in WORLD_STATE["characters"].values():
            person.runtime_state = AgentRuntimeState()
            person.location = "晚风客栈"
        self.backend = Mock()
        self.backend.advance_time.return_value = "08:05"
        for target in ("tools.remote_world.active_backend", "agent.session.active_backend"):
            patcher = patch(target, return_value=self.backend)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.index = Mock()
        self.index.retrieve_memory.return_value = []
        self.index.retrieve_lore.return_value = []

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def person(self, name="林默"):
        return WORLD_STATE["characters"][name]

    def scheduler(self, tick=0, pending=None):
        scheduler = WorldTickScheduler(director=None)
        scheduler.restore({"tick_count": tick, "event_cursor": len(WORLD_STATE["events"]),
                           "pending": pending or [], "current_depth": 0})
        return scheduler

    def talk(self, person, target=None, message="你好"):
        partner = target or ("苏晚" if person.name == "林默" else "林默")
        committed_event("talk", person.name, f"{person.name}对{partner}说：{message}",
                        target=partner, payload={"message": message})
        return "Java 已提交 talk"

    def start(self):
        scheduler = self.scheduler(pending=[{"name": "林默", "depth": 0, "source": "bootstrap"}])
        scheduler.run_tick(self.talk)
        return scheduler, sessions()[0]

    def test_first_talk_creates_session_and_keeps_event_memory_without_duplicate_pending(self):
        scheduler, session = self.start()
        self.assertEqual(session.participants, ["林默", "苏晚"])
        self.assertEqual((session.next_speaker, session.started_tick, session.last_activity_tick), ("苏晚", 0, 0))
        self.assertEqual(session.messages[0].content, "你好")
        self.assertEqual(WORLD_STATE["events"][0]["type"], "talk")
        self.assertEqual(scheduler.snapshot()["pending"], [])
        for name in session.participants:
            self.assertEqual(sum(entry.source_event_id == session.messages[0].event_id
                                 for entry in self.person(name).memory.all_entries()), 1)

    def test_second_turn_uses_conversation_and_reply_reuses_session(self):
        scheduler, session = self.start()
        result = scheduler.run_tick(self.talk)
        self.assertEqual((result["character"], result["source"], result["conversation_id"]),
                         ("苏晚", "conversation", session.id))
        self.assertEqual(len(sessions()), 1)
        self.assertEqual([message.speaker for message in session.messages], ["林默", "苏晚"])
        self.assertEqual((session.next_speaker, session.last_activity_tick), ("林默", 1))
        self.assertEqual(scheduler.snapshot()["current_depth"], 0)

    def test_conversation_passes_reaction_depth_and_has_own_safety_limit(self):
        scheduler, session = self.start()
        for _ in range(MAX_REACTION_DEPTH + 2):
            self.assertEqual(scheduler.run_tick(self.talk)["source"], "conversation")
        self.assertEqual(session.status, "active")
        while len(session.messages) < MAX_CONVERSATION_TURNS:
            scheduler.run_tick(self.talk)
        self.assertEqual((session.status, len(session.messages)), ("ended", MAX_CONVERSATION_TURNS))
        self.assertEqual(sessions(), [])
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.assertEqual(len(WORLD_STATE["events"]), MAX_CONVERSATION_TURNS)

    def test_event_priority_interrupts_then_conversation_resumes(self):
        scheduler, session = self.start()
        committed_event("intervention", "世界", "新线索", location="晚风客栈")
        first = scheduler.run_tick(lambda person: "先考虑新线索")
        self.assertEqual(first["source"], "event")
        self.assertEqual(session.status, "active")
        while scheduler.snapshot()["pending"]:
            scheduler.run_tick(lambda person: "先考虑新线索")
        self.assertEqual(scheduler.run_tick(self.talk)["source"], "conversation")

    def test_departure_ends_and_releases_participants(self):
        scheduler, session = self.start()
        def leave(person):
            person.location = "县衙"
            committed_event("move", person.name, "离开客栈", payload={"from": "晚风客栈", "to": "县衙"})
            return "已离开"
        scheduler.run_tick(leave)
        self.assertEqual(session.status, "ended")
        self.assertIsNone(for_participant("林默"))
        self.assertEqual(sessions(), [])

    def test_unconscious_ends_before_selection(self):
        scheduler, session = self.start()
        self.person("苏晚").status = "unconscious"
        result = scheduler.run_tick(lambda person: "等待")
        self.assertNotEqual(result["source"], "conversation")
        self.assertEqual((session.status, sessions()), ("ended", []))

    def test_inactivity_timeout_ends(self):
        scheduler, session = self.start()
        state = scheduler.snapshot()
        state["tick_count"] = CONVERSATION_TIMEOUT
        scheduler.restore(state)
        scheduler.run_tick(lambda person: "等待")
        self.assertEqual((session.status, sessions()), ("ended", []))

    def test_wait_consumes_conversation_opportunity_without_consuming_agenda(self):
        scheduler, session = self.start()
        reminder = AgendaEntry("reminder", "苏晚", 0, "继续经营")
        self.person("苏晚").runtime_state.agenda = [reminder]
        result = scheduler.run_tick(lambda person: "等待")
        self.assertEqual(result["source"], "conversation")
        self.assertEqual(session.status, "ended")
        self.assertEqual(reminder.status, "pending")
        self.assertGreater(reminder.due_tick, scheduler.snapshot()["tick_count"])

    def test_busy_until_does_not_block_conversation_or_get_overwritten(self):
        scheduler, _ = self.start()
        self.person("苏晚").runtime_state.busy_until = 100
        self.assertEqual(scheduler.run_tick(self.talk)["source"], "conversation")
        self.assertEqual(self.person("苏晚").runtime_state.busy_until, 100)

    def test_active_participant_agenda_and_bootstrap_do_not_duplicate_turn(self):
        scheduler, session = self.start()
        self.person("苏晚").runtime_state.agenda = [AgendaEntry("due", "苏晚", 0, "自己的安排")]
        state = scheduler.snapshot()
        state["pending"] = [{"name": "苏晚", "depth": 0, "source": "bootstrap"}]
        scheduler.restore(state)
        self.assertEqual(scheduler.run_tick(self.talk)["source"], "conversation")
        self.assertEqual(self.person("苏晚").runtime_state.agenda[0].status, "pending")
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.assertEqual(session.status, "active")

    def test_new_pair_replaces_conflict_without_two_sessions_per_person(self):
        scheduler, old = self.start()
        committed_event("talk", "赵无极", "询问林默", target="林默", payload={"message": "请问？"})
        scheduler.run_tick(lambda person: self.talk(person, target="赵无极"))
        self.assertEqual(old.status, "ended")
        self.assertEqual(len(sessions()), 1)
        self.assertEqual(set(sessions()[0].participants), {"林默", "赵无极"})

    def test_committed_talk_summary_failure_is_appended_once_and_restores_next_turn(self):
        scheduler, session = self.start()
        def fail_summary(person):
            self.talk(person, message="已经说过")
            raise RuntimeError("总结失败")
        result = scheduler.run_tick(fail_summary)
        self.assertIn("行动已发生", result["action_result"])
        self.assertEqual(len(session.messages), 2)
        saved = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        restored = WorldTickScheduler()
        restored.restore(restore_snapshot(saved))
        self.assertEqual(restored.run_tick(self.talk)["character"], "林默")
        self.assertEqual(len(sessions()[0].messages), 3)
        self.assertEqual(sum(event["payload"].get("message") == "已经说过" for event in WORLD_STATE["events"]), 1)

    def test_pre_action_failure_preserves_turn_and_does_not_add_pending(self):
        scheduler, session = self.start()
        with self.assertRaisesRegex(RuntimeError, "模型失败"):
            scheduler.run_tick(Mock(side_effect=RuntimeError("模型失败")))
        self.assertEqual((len(session.messages), session.next_speaker), (1, "苏晚"))
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.assertEqual(scheduler.run_tick(self.talk)["character"], "苏晚")

    def test_clock_failure_after_talk_does_not_replay_speaker(self):
        scheduler, session = self.start()
        self.backend.advance_time.side_effect = RuntimeError("时钟失败")
        with self.assertRaisesRegex(RuntimeError, "时钟失败"):
            scheduler.run_tick(self.talk)
        self.assertEqual((len(session.messages), session.next_speaker), (2, "林默"))
        self.backend.advance_time.side_effect = None
        self.assertEqual(scheduler.run_tick(self.talk)["character"], "林默")
        self.assertEqual(len(session.messages), 3)

    def test_java_refresh_during_reply_updates_live_session_not_old_object(self):
        scheduler, old = self.start()
        def reply(person):
            self.talk(person)
            remote = deepcopy(snapshot_world())
            backend = RemoteWorld(WORLD_STATE["world_id"])
            with patch.object(backend, "_call", return_value=json.dumps(remote, ensure_ascii=False)):
                backend._refresh_business_state()
            return "已回复"
        scheduler.run_tick(reply)
        self.assertEqual(sessions()[0].id, old.id)
        self.assertEqual((len(sessions()[0].messages), sessions()[0].next_speaker), (2, "林默"))
        self.assertEqual(len(old.messages), 1)

    def test_talk_at_ordinary_reaction_depth_limit_still_starts_conversation(self):
        scheduler = self.scheduler(pending=[{"name": "林默", "depth": MAX_REACTION_DEPTH, "source": "event"}])
        scheduler.run_tick(self.talk)
        self.assertEqual(scheduler.snapshot()["pending"], [])
        self.assertEqual(scheduler.run_tick(self.talk)["source"], "conversation")
        self.assertEqual(len(sessions()[0].messages), 2)

    def test_world_session_finally_saves_turn_after_committed_talk_summary_failure(self):
        scheduler, session = self.start()
        def fail(person):
            self.talk(person)
            raise RuntimeError("总结失败")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            world_session = WorldSession(fail, save_path=path, index=self.index, scheduler_state=scheduler.snapshot())
            world_session.next_tick()
            restored = WorldTickScheduler()
            restored.restore(load_world(path))
            self.assertEqual((len(sessions()[0].messages), sessions()[0].next_speaker), (2, "林默"))
            self.assertEqual(restored.run_tick(self.talk)["character"], "林默")
        self.backend.save_agent_state.assert_called_once()

    def test_ended_snapshot_does_not_reserve_participant_or_keep_full_text(self):
        scheduler, _ = self.start()
        raw = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        raw["active_conversations"][0]["status"] = "ended"
        restore_snapshot(raw)
        self.assertEqual(snapshot_world()["active_conversations"], [])
        self.assertIsNone(context_for("林默"))

    def test_event_end_intent_ends_current_session_without_a_talk(self):
        scheduler, session = self.start()
        committed_event("intervention", "世界", "新线索", location="晚风客栈")
        result = scheduler.run_tick(lambda person: DecisionResult("先忙别的，结束交流", False))
        self.assertEqual(result["source"], "event")
        self.assertEqual((session.status, sessions()), ("ended", []))

    def test_duplicate_event_is_idempotent_and_uncommitted_text_rejected(self):
        scheduler, session = self.start()
        event = WORLD_STATE["events"][0]
        self.assertTrue(accept_talk(event, 1))
        self.assertEqual(len(session.messages), 1)
        fake = {**event, "id": "not-committed"}
        with self.assertRaisesRegex(ValueError, "已提交"):
            accept_talk(fake, 1)

    def test_failed_java_talk_does_not_create_session(self):
        self.backend.execute.side_effect = ValueError("双方不在同一地点")
        with self.assertRaisesRegex(ValueError, "同一地点"):
            execute_tool("talk", {"speaker": "林默", "listener": "苏晚", "message": "你好"}, "林默")
        self.assertEqual((sessions(), WORLD_STATE["events"]), ([], []))

    def test_prompt_private_context_only_for_participants_and_recent_messages(self):
        scheduler, session = self.start()
        for number in range(7):
            scheduler.run_tick(lambda person: self.talk(person, message=f"私有消息-{number}"))
        prompt = build_model_prompt(create_initial_agent_state(self.person(session.next_speaker), self.index))
        self.assertIn('"your_turn": true', prompt)
        self.assertIn("私有消息-6", prompt)
        section = prompt.split("【当前交流（只读，仅本人会话）】\n")[1].splitlines()[0]
        self.assertEqual(len(json.loads(section)["messages"]), 6)
        self.assertNotIn(session.id, prompt)
        other = build_model_prompt(create_initial_agent_state(self.person("赵无极"), self.index))
        self.assertNotIn("私有消息", other)
        self.assertNotIn("【当前交流", other)
        self.assertFalse(any(entry.source_event_id == session.messages[-1].event_id
                             for entry in self.person("赵无极").memory.all_entries()))

    def test_session_file_and_java_payload_restore_active_conversation(self):
        scheduler, session = self.start()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(path, scheduler_state=scheduler.snapshot())
            WORLD_STATE["active_conversations"] = []
            restored = WorldTickScheduler()
            restored.restore(load_world(path))
            self.assertEqual(sessions()[0].to_dict(), session.to_dict())
            self.assertEqual(restored.run_tick(self.talk)["character"], "苏晚")
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call") as call:
            backend.save_agent_state(restored.snapshot())
        payload = json.loads(call.call_args.args[1]["agentStateJson"])
        self.assertEqual(payload["active_conversations"], snapshot_world()["active_conversations"])

    def test_multi_world_and_old_snapshot_do_not_import_conversations(self):
        scheduler, session = self.start()
        first = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        other = deepcopy(first)
        other["world_id"] = "other-world"
        other.pop("active_conversations")
        restore_snapshot(other)
        self.assertEqual(sessions(), [])
        restore_snapshot(first)
        self.assertEqual(sessions()[0].id, session.id)

    def test_controller_world_switch_isolates_sessions_and_rolls_back_on_failure(self):
        from web_api import WorldController
        scheduler, session = self.start()
        controller = WorldController()
        controller.session = SimpleNamespace(scheduler=scheduler, completed_ticks=1)
        other = deepcopy(snapshot_world(scheduler_state={"tick_count": 0, "pending": []}))
        other["world_id"] = "other-world"
        other["active_conversations"] = []
        new_backend = Mock()
        new_backend.load.return_value = other
        new_session = SimpleNamespace(scheduler=Mock(), completed_ticks=0)
        with patch("tools.remote_world.RemoteWorld", return_value=new_backend), \
                patch("tools.remote_world.use_backend"), patch("web_api.save_world"), \
                patch.object(controller, "_new_session", side_effect=ValueError("索引失败")):
            with self.assertRaisesRegex(ValueError, "索引失败"):
                controller.activate_world("other-world")
        self.assertEqual(sessions()[0].to_dict(), session.to_dict())
        with patch("tools.remote_world.RemoteWorld", return_value=new_backend), \
                patch("tools.remote_world.use_backend"), patch("web_api.save_world"), \
                patch.object(controller, "_new_session", return_value=new_session):
            controller.activate_world("other-world")
        self.assertEqual((WORLD_STATE["world_id"], sessions()), ("other-world", []))

    def test_remote_refresh_retains_unsaved_conversation_only_in_same_world(self):
        scheduler, session = self.start()
        remote = deepcopy(snapshot_world())
        remote["active_conversations"] = []
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call", return_value=json.dumps(remote, ensure_ascii=False)):
            backend._refresh_business_state()
        self.assertEqual(sessions()[0].id, session.id)
        other = deepcopy(remote)
        other["world_id"] = "other-world"
        backend = RemoteWorld("other-world")
        with patch.object(backend, "_call", return_value=json.dumps(other, ensure_ascii=False)):
            backend._refresh_business_state()
        self.assertEqual(sessions(), [])

    def test_model_explicit_end_is_an_intent_not_session_structure_write(self):
        scheduler, session = self.start()
        response = SimpleNamespace(output=[], output_text=json.dumps({"continue_conversation": False, "answer": "没什么可说了"}))
        result = scheduler.run_tick(make_graph_decide_action(Mock(return_value=response), self.index))
        self.assertEqual(result["action_result"], "没什么可说了")
        self.assertEqual((session.status, sessions()), ("ended", []))
        self.assertEqual(len(WORLD_STATE["events"]), 1)

    def test_model_cognition_cannot_modify_conversation(self):
        scheduler, session = self.start()
        response = SimpleNamespace(output=[], output_text=json.dumps({"cognition": {"active_conversations": []}, "answer": "结束"}))
        result = build_agent_loop_graph(Mock(return_value=response)).invoke(create_initial_agent_state(self.person(), self.index))
        self.assertIn("认知更新未保存", result["final_answer"])
        self.assertEqual(sessions()[0].id, session.id)

    def test_invalid_end_intent_is_not_interpreted_as_false(self):
        scheduler, session = self.start()
        response = SimpleNamespace(output=[], output_text=json.dumps({"continue_conversation": "false", "answer": "结束"}))
        result = build_agent_loop_graph(Mock(return_value=response)).invoke(create_initial_agent_state(self.person(), self.index))
        self.assertIsNone(result["continue_conversation"])
        self.assertEqual(session.status, "active")

    def test_disjoint_conversations_are_scheduled_deterministically(self):
        fourth = Character("第四人", "居民", "", "", ["生活"], "晚风客栈", 100)
        WORLD_STATE["characters"][fourth.name] = fourth
        scheduler, first = self.start()
        self.talk(self.person("赵无极"), target=fourth.name)
        scheduler._collect_events()
        second = for_participant(fourth.name)
        self.assertEqual(scheduler.run_tick(self.talk)["conversation_id"], first.id)
        # 两会话 last_activity_tick 此时同为 1，稳定顺序再选第一；更新后第二成为最早。
        self.assertEqual(scheduler.run_tick(self.talk)["conversation_id"], first.id)
        result = scheduler.run_tick(lambda person: self.talk(person, target="赵无极"))
        self.assertEqual(result["conversation_id"], second.id)

    def test_conversation_tick_still_has_one_successful_world_action(self):
        scheduler, _ = self.start()
        calls = [SimpleNamespace(type="function_call", name="talk", call_id=str(i),
                                 arguments='{"speaker":"苏晚","listener":"林默","message":"回复"}') for i in range(2)]
        requests = Mock(side_effect=[SimpleNamespace(output=calls, output_text=""),
                                     SimpleNamespace(output=[], output_text="已回复")])
        self.backend.execute.side_effect = lambda *_: self.talk(self.person("苏晚"), message="回复")
        scheduler.run_tick(make_graph_decide_action(requests, self.index))
        self.backend.execute.assert_called_once()
        self.assertEqual(len(WORLD_STATE["events"]), 2)
        self.assertEqual(len(sessions()[0].messages), 2)

    def test_completed_sessions_do_not_accumulate_runtime_history(self):
        scheduler = self.scheduler(pending=[{"name": "林默", "depth": 0, "source": "bootstrap"}])
        for _ in range(100):
            # 程序提供一次开场机会，talk 后下一位选择等待结束。
            state = scheduler.snapshot()
            state["pending"] = [{"name": "林默", "depth": 0, "source": "event"}]
            scheduler.restore(state)
            scheduler.run_tick(self.talk)
            self.assertEqual(len(sessions()), 1)
            scheduler.run_tick(lambda person: "等待")
            self.assertEqual(snapshot_world()["active_conversations"], [])

    def test_invalid_snapshot_cannot_forge_messages_or_duplicate_participants(self):
        scheduler, _ = self.start()
        valid = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        for invalid in ("message", "participants", "order"):
            bad = deepcopy(valid)
            if invalid == "message":
                bad["active_conversations"][0]["messages"][0]["content"] = "未真实说过"
            elif invalid == "participants":
                extra = deepcopy(bad["active_conversations"][0])
                extra["id"] = "other-session"
                bad["active_conversations"].append(extra)
            else:
                bad["active_conversations"][0]["next_speaker"] = "林默"
            before = deepcopy(snapshot_world())
            with self.assertRaises(ValueError):
                restore_snapshot(bad)
            self.assertEqual(snapshot_world(), before)
