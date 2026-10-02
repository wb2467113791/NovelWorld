"""Player 只接收人类输入；全部模型、MCP 与数据库边界使用确定性替身。"""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch

from agent.conversation import accept_talk, context_for, expire, for_participant, sessions
from agent.director import Director
from agent.runtime import AgendaEntry
from agent.session import WorldSession, make_graph_decide_action
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.model import Character, PlayerActor, is_npc
from retrieval.chroma_index import ChromaIndex
from skills.router import choose_skill, current_step, skill_for
from tests.support import committed_event
from tools.remote_world import CommittedActionError, RemoteWorld, active_backend, use_backend
from web_api import WorldController
from world.objects import current_objects, make_object
from world.persistence import load_world, restore_snapshot, save_world, snapshot_world
from world.play import action_schemas, end_conversation, player_actor, state_view, submit_action
from world.state import WORLD_STATE, reconcile_event_memories


class PlayerTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        self.original_backend = active_backend()
        WORLD_STATE.clear(); WORLD_STATE.update(deepcopy(self.original))
        WORLD_STATE["events"] = []; WORLD_STATE["active_conversations"] = []
        for person in WORLD_STATE["characters"].values():
            person.location = "晚风客栈"
        WORLD_STATE["characters"]["玩家"] = PlayerActor("玩家", "晚风客栈")
        self.backend = Mock()
        self.backend.advance_time.return_value = "08:05"
        self.backend.execute.side_effect = self.commit
        use_backend(self.backend)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def tearDown(self):
        WORLD_STATE.clear(); WORLD_STATE.update(self.original)
        use_backend(self.original_backend)

    def commit(self, tool, arguments, actor):
        """模拟 Java 返回真实已提交事件；Java 合法性另由 H2/MCP 测试验证。"""
        target = arguments.get("listener", arguments.get("receiver"))
        kind = {"move_character": "move", "rest_character": "rest"}.get(tool, tool)
        payload = {"message": arguments["message"]} if tool == "talk" else {}
        if tool == "move_character":
            person = WORLD_STATE["characters"][actor]
            payload = {"from": person.location, "to": arguments["location"]}
            person.location = arguments["location"]
        if tool == "inspect":
            payload = {"observation": "普通描述", "object_name": None}
        committed_event(kind, actor, f"{actor} 的 {kind}", target=target, payload=payload)
        return "Java 已提交"

    def scheduler(self):
        scheduler = WorldTickScheduler()
        scheduler.restore({"tick_count": 0, "event_cursor": 0, "pending": []})
        return scheduler

    def start_waiting(self):
        scheduler = self.scheduler()
        scheduler.run_player_action("talk", {"listener": "苏晚", "message": "你好"})
        self.assertEqual(sessions()[0].started_tick, 0)
        first_id = sessions()[0].id
        result = scheduler.run_tick(lambda person: self.commit("talk", {"listener": "玩家", "message": "你好，旅人"}, person.name))
        self.assertEqual((result["character"], result["source"]), ("苏晚", "conversation"))
        self.assertEqual(sessions()[0].next_speaker, "玩家")
        return scheduler, first_id

    def test_player_minimal_model_save_restore_and_no_cognition(self):
        player = player_actor(); player.energy = 83; player.relationships["苏晚"] = 4
        save_world(Path(self.temp.name) / "world.json")
        player.energy = 1
        load_world(Path(self.temp.name) / "world.json")
        restored = player_actor()
        self.assertEqual((restored.energy, restored.relationships), (83, {"苏晚": 4}))
        self.assertIsInstance(restored, PlayerActor)
        for field in ("goals", "runtime_state", "memory", "semantic_memory"):
            self.assertFalse(hasattr(restored, field))
        self.assertNotIn("memory", snapshot_world()["characters"]["玩家"])

    def test_bootstrap_and_restored_pending_skip_player(self):
        scheduler = WorldTickScheduler()
        self.assertNotIn("玩家", [item["name"] for item in scheduler.snapshot()["pending"]])
        scheduler.restore({"tick_count": 0, "pending": [{"name": "玩家", "depth": 0, "source": "bootstrap"}]})
        self.assertEqual(scheduler.snapshot()["pending"], [])

    def test_player_event_recipient_not_reaction_but_npc_memory_receives_action(self):
        scheduler = self.scheduler()
        event = committed_event("take", "玩家", "玩家拿走登记簿")
        self.assertIn("玩家", event["perceived_by"])
        self.assertTrue(WORLD_STATE["characters"]["苏晚"].memory.all_entries())
        scheduler._collect_events()
        self.assertNotIn("玩家", [item["name"] for item in scheduler.snapshot()["pending"]])
        self.assertEqual(reconcile_event_memories(), 0)

    def test_player_never_gets_agenda_or_reflection(self):
        scheduler = self.scheduler()
        decide = Mock(return_value="等待")
        with patch("agent.tick.reflect_on_new_memories") as reflect:
            for _ in range(3): scheduler.run_tick(decide)
        decide.assert_not_called()
        self.assertEqual(reflect.call_count, 3)
        self.assertFalse(hasattr(player_actor(), "runtime_state"))

    def test_player_never_runs_skill_agent_or_chroma(self):
        player = player_actor(); index = Mock(); model = Mock()
        self.assertIsNone(choose_skill(player)); self.assertIsNone(current_step(player)); self.assertEqual(skill_for(player), "")
        with self.assertRaisesRegex(ValueError, "Player"):
            create_initial_agent_state(player, index)
        with self.assertRaisesRegex(ValueError, "Player"):
            make_graph_decide_action(model, index)(player)
        model.assert_not_called(); index.assert_not_called()
        chroma = object.__new__(ChromaIndex); chroma._sync_collection = Mock(); chroma.sync_lore = Mock()
        chroma.sync_character(player); chroma._sync_collection.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Player"):
            chroma.retrieve_memory(player, "目标")
        with patch.object(chroma, "sync_character") as sync:
            chroma.sync_world(WORLD_STATE["characters"])
            self.assertEqual([call.args[0].name for call in sync.call_args_list], ["林默", "苏晚", "赵无极"])

    def test_director_participation_does_not_select_player(self):
        director = Director(Mock())
        for name in ("林默", "苏晚", "赵无极"):
            committed_event("take", name, name)
        self.assertNotEqual(director.choose_event(6), ("participation", player_actor().location))
        player_actor().location = "县衙"
        self.assertNotEqual(director.occupied_location("县衙"), "县衙")

    def test_action_surface_and_injected_identity(self):
        schemas = action_schemas()
        self.assertEqual({value["name"] for value in schemas}, {"inspect", "take", "put", "give", "use", "interact", "move", "talk", "rest"})
        for schema in schemas:
            self.assertFalse({"character", "speaker", "actor", "giver"}.intersection(schema["parameters"]["properties"]))
        submit_action("talk", {"listener": "苏晚", "message": "你好"})
        self.backend.execute.assert_called_once_with("talk", {"listener": "苏晚", "message": "你好", "speaker": "玩家"}, "玩家")

    def test_impersonation_unknown_tools_and_parameters_rejected_before_mcp(self):
        for identity in ("character", "speaker", "actor", "giver", "actingCharacter"):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                submit_action("inspect", {identity: "苏晚"})
        for action in ("update_relationship", "world_action", "give_item", "wait", "save_agent_state"):
            with self.assertRaises(ValueError): submit_action(action, {})
        for args in ({"object_name": "hidden"}, {"object_id": 3}):
            with self.assertRaises(ValueError): submit_action("inspect", args)
        self.backend.execute.assert_not_called()

    def test_success_player_action_one_tick_no_npc_and_no_pending_consumption(self):
        scheduler = WorldTickScheduler()
        pending = scheduler.snapshot()["pending"]
        result = scheduler.run_player_action("inspect", {})
        self.assertTrue(result["committed"]); self.assertEqual(result["tick_count"], 1)
        self.backend.advance_time.assert_called_once_with(5)
        self.assertEqual(scheduler.snapshot()["pending"], pending)
        self.backend.execute.assert_called_once()

    def test_java_rejection_does_not_advance_or_consume_opportunity(self):
        scheduler = WorldTickScheduler(); before = scheduler.snapshot()
        self.backend.execute.side_effect = ValueError("对象不可见")
        with self.assertRaisesRegex(ValueError, "不可见"):
            scheduler.run_player_action("take", {"object_id": "hidden"})
        self.assertEqual(scheduler.snapshot(), before)
        self.assertEqual(WORLD_STATE["events"], [])
        self.backend.advance_time.assert_not_called()

    def test_committed_refresh_or_clock_failure_never_replays(self):
        scheduler = self.scheduler()
        self.backend.execute.side_effect = CommittedActionError("已拿取", RuntimeError("刷新中断"))
        self.backend.advance_time.side_effect = RuntimeError("时钟失败")
        result = scheduler.run_player_action("take", {"object_id": "book"})
        self.assertTrue(result["committed"]); self.assertIn("失败", result["warning"])
        self.assertEqual(scheduler.snapshot()["tick_count"], 1)
        self.backend.execute.assert_called_once()

    def test_talk_creates_npc_turn_then_player_waiting_and_reply_same_session(self):
        scheduler, session_id = self.start_waiting()
        self.assertTrue(context_for("玩家")["your_turn"])
        self.assertTrue(state_view(2)["conversation"]["waiting_for_player"])
        scheduler.run_player_action("talk", {"listener": "苏晚", "message": "再聊聊"})
        self.assertEqual(sessions()[0].id, session_id)
        self.assertEqual(len(sessions()[0].messages), 3)
        self.assertEqual(sessions()[0].next_speaker, "苏晚")

    def test_waiting_player_does_not_block_other_conversation(self):
        scheduler, _ = self.start_waiting()
        event = committed_event("talk", "林默", "另一会话", target="赵无极", payload={"message": "另一会话"})
        accept_talk(event, 2)
        result = scheduler.run_tick(lambda person: self.commit("talk", {"listener": "林默", "message": "好"}, person.name))
        self.assertEqual((result["character"], result["source"]), ("赵无极", "conversation"))
        self.assertEqual(for_participant("玩家").next_speaker, "玩家")

    def test_waiting_player_does_not_block_agenda_event_or_idle(self):
        scheduler, _ = self.start_waiting()
        runtime = WORLD_STATE["characters"]["林默"].runtime_state
        runtime.agenda = [AgendaEntry("now", "林默", 0, "自行观察")]
        result = scheduler.run_tick(lambda person: "等待")
        self.assertEqual((result["source"], result["character"]), ("agenda", "林默"))
        committed_event("intervention", "世界", "县衙有信", location="县衙")
        self.assertEqual(scheduler.run_tick(lambda person: "等待")["source"], "idle")
        committed_event("intervention", "世界", "客栈有信", location="晚风客栈")
        self.assertEqual(scheduler.run_tick(lambda person: "等待")["source"], "event")

    def test_switch_partner_ends_previous_and_explicit_end_has_no_event_or_tick(self):
        scheduler, _ = self.start_waiting()
        old = for_participant("玩家")
        scheduler.run_player_action("talk", {"listener": "林默", "message": "你好"})
        self.assertEqual(old.status, "ended")
        self.assertEqual(context_for("玩家")["partner"], "林默")
        count, tick = len(WORLD_STATE["events"]), scheduler.snapshot()["tick_count"]
        end_conversation()
        self.assertIsNone(for_participant("玩家"))
        self.assertEqual((len(WORLD_STATE["events"]), scheduler.snapshot()["tick_count"]), (count, tick))

    def test_player_departure_and_npc_departure_or_unconscious_end_session(self):
        for name, field, value in (("玩家", "location", "县衙"), ("苏晚", "location", "县衙"), ("苏晚", "status", "unconscious")):
            WORLD_STATE["active_conversations"] = []
            player_actor().location = "晚风客栈"
            WORLD_STATE["characters"]["苏晚"].location = "晚风客栈"
            WORLD_STATE["characters"]["苏晚"].status = "normal"
            event = committed_event("talk", "玩家", "聊", target="苏晚", payload={"message": "聊"})
            accept_talk(event, 0)
            setattr(WORLD_STATE["characters"][name], field, value)
            expire(0); self.assertEqual(sessions(), [])

    def test_perception_excludes_private_state_hidden_contents_other_sessions(self):
        objects = current_objects()
        hidden = make_object("隐藏物件", "晚风客栈", "秘密描述")
        hidden.update(id="secret-id", visible=False)
        objects[hidden["id"]] = hidden
        chest = next(item for item in objects.values() if item["name"] == "木箱")
        note = make_object("箱内信件", None, "私有内容")
        note.update(id="inside-id", container=chest["id"])
        objects[note["id"]] = note
        committed_event("inspect", "林默", "NPC 私有发现", payload={"observation": "NPC 私有发现"})
        event = committed_event("talk", "林默", "私有会话", target="苏晚", payload={"message": "私有会话"})
        accept_talk(event, 0)
        serialized = json.dumps(state_view(0), ensure_ascii=False)
        for private in ("secret-id", "inside-id", "隐藏物件", "箱内信件", "秘密描述", "NPC 私有发现", "私有会话", "runtime_state", "semantic_memory", "goals", "secrets"):
            self.assertNotIn(private, serialized)
        chest["state"] = "open"
        self.assertIn("inside-id", json.dumps(state_view(0)))

    def test_runtime_save_omits_player_and_refresh_preserves_npc_only(self):
        backend = RemoteWorld(WORLD_STATE["world_id"])
        backend._call = Mock(return_value="1")
        backend.save_agent_state({"tick_count": 2})
        payload = json.loads(backend._call.call_args.args[1]["agentStateJson"])
        self.assertNotIn("玩家", payload["characters"])
        remote = deepcopy(snapshot_world())
        remote["characters"]["玩家"]["energy"] = 65
        backend._call.return_value = json.dumps(remote)
        backend._refresh_business_state()
        self.assertEqual(player_actor().energy, 65)
        self.assertFalse(hasattr(player_actor(), "memory"))

    def test_world_switch_restores_independent_player_and_rollback(self):
        controller = WorldController()
        controller.session = WorldSession(Mock(), save_path=Path(self.temp.name) / "world.json", index=Mock(), scheduler_state={"tick_count": 0})
        old = deepcopy(snapshot_world()); new = deepcopy(old)
        new["world_id"] = "player-other"
        new["characters"]["玩家"]["location"] = "县衙"
        new["characters"]["玩家"]["energy"] = 43
        backend = Mock(); backend.load.return_value = new
        with patch("tools.remote_world.RemoteWorld", return_value=backend), patch("web_api.save_world"), patch.object(controller, "_new_session", return_value=controller.session):
            controller.activate_world("player-other")
        self.assertEqual((player_actor().location, player_actor().energy), ("县衙", 43))
        backend.load.return_value = old
        with patch("tools.remote_world.RemoteWorld", return_value=backend), patch("web_api.save_world"), patch.object(controller, "_new_session", side_effect=ValueError("索引失败")):
            with self.assertRaises(ValueError): controller.activate_world(old["world_id"])
        self.assertEqual((WORLD_STATE["world_id"], player_actor().energy), ("player-other", 43))

    def test_controller_serializes_player_and_rejects_stale_world(self):
        controller = WorldController()
        controller.session = WorldSession(Mock(), save_path=Path(self.temp.name) / "world.json", index=Mock(), scheduler_state={"tick_count": 0})
        with self.assertRaisesRegex(RuntimeError, "切换"):
            controller.play("action", world_id="wrong", action="inspect", arguments={})
        entered, release = Event(), Event()
        def hold():
            with controller.lock: entered.set(); release.wait(2)
        thread = Thread(target=hold); thread.start(); entered.wait(1)
        try:
            with self.assertRaisesRegex(RuntimeError, "Tick"):
                controller.play("action", world_id=WORLD_STATE["world_id"], action="inspect", arguments={})
        finally: release.set(); thread.join(2)
        self.backend.execute.assert_not_called()
        result = controller.play("action", world_id=WORLD_STATE["world_id"], action="inspect", arguments={})
        self.assertTrue(result["committed"])
        controller.session.decide_action.assert_not_called()

    def test_player_conversation_persists_without_player_memory(self):
        scheduler, session_id = self.start_waiting()
        saved = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
        restore_snapshot(saved)
        restored = WorldTickScheduler(); restored.restore(saved["scheduler"])
        self.assertEqual(for_participant("玩家").id, session_id)
        self.assertEqual(for_participant("玩家").next_speaker, "玩家")
        self.assertNotEqual(restored._select_opportunity(), {"name": "玩家", "source": "conversation"})

    def test_internal_http_action_rejects_identity_and_never_calls_llm(self):
        from fastapi.testclient import TestClient
        from web_api import app
        controller = WorldController()
        controller.session = WorldSession(Mock(), save_path=Path(self.temp.name) / "http.json", index=Mock(), scheduler_state={"tick_count": 0})
        with patch("web_api.controller", controller):
            client = TestClient(app)
            for identity in ("character", "speaker", "actor", "giver"):
                response = client.post("/internal/play/action", json={"world_id": WORLD_STATE["world_id"], "action": "inspect", "arguments": {identity: "苏晚"}})
                self.assertEqual(response.status_code, 400)
            self.backend.execute.assert_not_called()
            response = client.post("/internal/play/action", json={"world_id": WORLD_STATE["world_id"], "action": "talk", "arguments": {"listener": "苏晚", "message": "你好"}})
            self.assertEqual(response.status_code, 200)
            controller.session.decide_action.assert_not_called()
            self.assertEqual(sessions()[0].next_speaker, "苏晚")
            events = len(WORLD_STATE["events"])
            self.assertEqual(client.get("/internal/play/state").status_code, 200)
            response = client.post("/internal/play/conversation/end", json={"world_id": WORLD_STATE["world_id"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(sessions(), [])
            self.assertEqual(len(WORLD_STATE["events"]), events)

    def test_state_read_does_not_write_unchanged_runtime_and_save_failure_is_committed(self):
        controller = WorldController()
        controller.session = WorldSession(Mock(), save_path=Path(self.temp.name) / "state.json", index=Mock(), scheduler_state={"tick_count": 0})
        controller.play("state")
        self.backend.save_agent_state.assert_not_called()
        self.backend.save_agent_state.side_effect = RuntimeError("保存暂时失败")
        result = controller.play("action", world_id=WORLD_STATE["world_id"], action="inspect", arguments={})
        self.assertTrue(result["committed"])
        self.assertIn("保存失败", result["warning"])
        self.assertEqual(controller.session.completed_ticks, 1)
        self.backend.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
