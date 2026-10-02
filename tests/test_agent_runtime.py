"""V4 Phase 1：模型和 MCP 均使用替身，不请求真实 API。"""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.graph import build_agent_loop_graph, build_model_prompt
from agent.runtime import AgendaEntry, AgentRuntimeState
from agent.session import WorldSession
from agent.state import create_initial_agent_state
from agent.tick import WorldTickScheduler
from characters.model import Character
from characters.prompt import build_action_prompt
from skills.router import current_step
from tools.remote_world import RemoteWorld
from world.persistence import load_world, restore_snapshot, save_world, snapshot_world
from world.state import WORLD_STATE
from tests.support import committed_event


class AgentRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))
        self.index = Mock()
        self.index.retrieve_memory.return_value = []
        self.index.retrieve_lore.return_value = []

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def lin(self):
        return WORLD_STATE["characters"]["林默"]

    def cognition(self):
        return AgentRuntimeState(
            active_goal=self.lin().goals[1], current_intention="确认客栈方向的线索",
            current_plan="继续调查客栈相关情况，根据新信息调整方向。",
            agenda=[AgendaEntry("visit", "林默", 300, "继续调查", "pending")], busy_until=290)

    def response(self, changes=None, answer="等待", calls=None):
        text = json.dumps({"cognition": changes, "answer": answer}, ensure_ascii=False) if changes is not None else answer
        return SimpleNamespace(output=calls or [], output_text=text)

    def test_explicit_goal_is_used_by_graph_retrieval_and_skill(self):
        lin = self.lin()
        lin.goals = ["调查失踪案", "保护线索"]
        lin.location = "晚风客栈"
        lin.runtime_state.active_goal = lin.goals[1]
        state = create_initial_agent_state(lin, self.index)
        self.assertEqual(state["goal"], "保护线索")
        self.index.retrieve_memory.assert_called_once_with(lin, "保护线索 晚风客栈")
        # 使用不带捕快角色的角色区分两种 Skill。
        lin.role = "守卫"
        self.assertEqual(current_step(lin).tool, "take")
        self.assertIn("当前目标：保护线索", build_model_prompt(state))

    def test_goal_selection_keeps_choice_and_handles_removed_or_empty_goals(self):
        runtime = self.cognition()
        self.assertEqual(runtime.select_goal(self.lin().goals), self.lin().goals[1])
        self.assertEqual(runtime.select_goal(["新目标"]), "新目标")
        self.assertIsNone(runtime.current_plan)
        self.assertEqual(runtime.select_goal([]), "")
        empty = Character("无目标", "居民", "", "", [], "县衙", 80)
        self.assertEqual(create_initial_agent_state(empty, self.index)["goal"], "")

    def test_runtime_agenda_busy_and_scheduler_survive_file_restart(self):
        self.lin().runtime_state = self.cognition()
        scheduler = WorldTickScheduler()
        expected = self.lin().runtime_state.to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(path, scheduler_state=scheduler.snapshot())
            self.lin().runtime_state = AgentRuntimeState()
            saved_scheduler = load_world(path)
        restored_scheduler = WorldTickScheduler()
        restored_scheduler.restore(saved_scheduler)
        self.assertEqual(self.lin().runtime_state.to_dict(), expected)
        self.assertEqual(restored_scheduler.snapshot(), scheduler.snapshot())
        self.lin().runtime_state.agenda[0].status = "completed"
        self.assertEqual(expected["agenda"][0]["status"], "pending")

    def test_same_named_characters_do_not_share_cognition_across_worlds(self):
        self.lin().runtime_state = self.cognition()
        first = deepcopy(snapshot_world())
        second = deepcopy(first)
        second["world_id"] = "other-world"
        for person in second["characters"].values():
            person.pop("runtime_state")  # 旧快照迁移，也必须清空上一世界状态。
        restore_snapshot(second)
        self.assertIsNone(self.lin().runtime_state.current_plan)
        self.assertEqual(self.lin().runtime_state.agenda, [])
        self.assertIsNone(self.lin().runtime_state.busy_until)
        restore_snapshot(first)
        self.assertEqual(self.lin().runtime_state.to_dict(), self.cognition().to_dict())

    def test_java_refresh_preserves_unsaved_cognition_but_uses_remote_business_state(self):
        remote = deepcopy(snapshot_world())
        self.lin().runtime_state = self.cognition()
        remote["characters"]["林默"]["location"] = "晚风客栈"
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call", return_value=json.dumps(remote, ensure_ascii=False)):
            backend._refresh_business_state()
        self.assertEqual(self.lin().location, "晚风客栈")
        self.assertEqual(self.lin().runtime_state.to_dict(), self.cognition().to_dict())

    def test_cognition_is_saved_over_existing_mcp_payload(self):
        self.lin().runtime_state = self.cognition()
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call") as call:
            backend.save_agent_state({"tick_count": 7})
        name, args = call.call_args.args
        self.assertEqual(name, "save_agent_state")
        payload = json.loads(args["agentStateJson"])
        self.assertEqual(payload["characters"]["林默"]["runtime_state"], self.cognition().to_dict())
        self.assertEqual(set(payload["characters"]["林默"]), {"memory", "semantic_memory", "runtime_state", "belief_memory"})
        self.assertEqual(args["worldId"], WORLD_STATE["world_id"])

    def test_observed_event_allows_plan_revision_without_world_mutation_or_extra_call(self):
        self.lin().runtime_state = self.cognition()
        committed_event("intervention", "世界", "县衙出现新信", location="县衙")
        before = deepcopy(snapshot_world())
        request = Mock(return_value=self.response({"current_intention": "核对新信",
                                                  "current_plan": "先核对新信息，再决定调查方向。"}))
        graph = build_agent_loop_graph(request)
        result = graph.invoke(create_initial_agent_state(self.lin(), self.index))
        self.assertIn("县衙出现新信", request.call_args.args[0][0]["content"])
        self.assertEqual(self.lin().runtime_state.current_intention, "核对新信")
        self.assertEqual(result["goal"], self.lin().goals[1])
        self.assertEqual(request.call_count, 1)
        after = snapshot_world()
        before["characters"]["林默"]["runtime_state"] = after["characters"]["林默"]["runtime_state"]
        self.assertEqual(after, before)

    def test_model_goal_switch_resets_old_plan_and_plain_reply_preserves_state(self):
        self.lin().runtime_state = self.cognition()
        graph = build_agent_loop_graph(Mock(return_value=self.response({"active_goal": self.lin().goals[0]})))
        graph.invoke(create_initial_agent_state(self.lin(), self.index))
        self.assertEqual(self.lin().runtime_state.active_goal, self.lin().goals[0])
        self.assertIsNone(self.lin().runtime_state.current_plan)
        self.lin().runtime_state.current_plan = "继续观察"
        graph = build_agent_loop_graph(Mock(return_value=self.response()))
        graph.invoke(create_initial_agent_state(self.lin(), self.index))
        self.assertEqual(self.lin().runtime_state.current_plan, "继续观察")

    def test_invalid_updates_are_atomic_and_cannot_store_tools_or_other_actor_state(self):
        self.lin().runtime_state = self.cognition()
        before = self.lin().runtime_state.to_dict()
        for changes in ({"current_plan": ["move", "inspect"]}, {"location": "晚风客栈"},
                        {"active_goal": "别人的目标"}, {"busy_until": True},
                        {"agenda": [{"id": "x", "character": "苏晚", "due_tick": 1, "intention": "藏匿"}]}):
            with self.subTest(changes=changes):
                result = build_agent_loop_graph(Mock(return_value=self.response(changes))).invoke(
                    create_initial_agent_state(self.lin(), self.index))
                self.assertIn("认知更新未保存", result["final_answer"])
                self.assertEqual(self.lin().runtime_state.to_dict(), before)

    def test_cognition_in_model_reply_does_not_allow_two_world_actions(self):
        calls = [SimpleNamespace(type="function_call", name="move_character", call_id=str(i),
                                 arguments='{"character":"林默","location":"晚风客栈"}') for i in range(2)]
        requests = Mock(side_effect=[self.response({"current_plan": "继续了解客栈情况"}, calls=calls),
                                     self.response({"current_intention": "评估移动结果"})])
        backend = Mock()
        backend.execute.return_value = "Java 已结算"
        with patch("tools.remote_world.active_backend", return_value=backend):
            result = build_agent_loop_graph(requests).invoke(create_initial_agent_state(self.lin(), self.index))
        backend.execute.assert_called_once()
        self.assertIn("本轮已完成一次行动", result["tool_results"][1]["output"])
        self.assertFalse(requests.call_args.args[1])
        self.assertEqual(self.lin().runtime_state.current_intention, "评估移动结果")

    def test_model_cannot_create_replace_clear_or_complete_system_schedule(self):
        self.lin().runtime_state = self.cognition()
        before = self.lin().runtime_state.to_dict()
        proposed_agendas = [None, []]
        for status in ("pending", "completed", "cancelled"):
            entry = {**before["agenda"][0], "status": status, "id": "model-generated", "due_tick": 999}
            proposed_agendas.append([entry])
        changes_list = [{"agenda": agenda} for agenda in proposed_agendas]
        changes_list.extend({"busy_until": value} for value in (None, 0, 999))
        for changes in changes_list:
            with self.subTest(changes=changes):
                # 即使同时提出有效目标切换，也必须整次拒绝，不能部分落地。
                request = Mock(return_value=self.response({"active_goal": self.lin().goals[0], **changes}))
                result = build_agent_loop_graph(request).invoke(create_initial_agent_state(self.lin(), self.index))
                self.assertIn("调度状态由程序维护", result["final_answer"])
                self.assertEqual(self.lin().runtime_state.to_dict(), before)

    def test_activity_wishes_do_not_change_schedule_and_system_statuses_restore(self):
        for status in ("pending", "completed", "cancelled"):
            with self.subTest(status=status):
                runtime = self.cognition()
                runtime.agenda[0].status = status  # 程序维护的持久化 fixture。
                self.lin().runtime_state = runtime
                restore_snapshot(deepcopy(snapshot_world()))
                request = Mock(return_value=self.response({"current_intention": "希望明早继续调查",
                                                          "current_plan": "等新线索出现再调整方向"}))
                build_agent_loop_graph(request).invoke(create_initial_agent_state(self.lin(), self.index))
                self.assertEqual(self.lin().runtime_state.agenda, runtime.agenda)
                self.assertEqual(self.lin().runtime_state.busy_until, runtime.busy_until)
                self.assertEqual(self.lin().runtime_state.current_intention, "希望明早继续调查")

    def test_prompt_separates_writable_cognition_from_readonly_schedule(self):
        self.lin().runtime_state = self.cognition()
        prompt = build_model_prompt(create_initial_agent_state(self.lin(), self.index))
        cognition = json.loads(prompt.split("【本人认知状态（意图，不是世界事实）】\n")[1].splitlines()[0])
        scheduling = json.loads(prompt.split("【系统调度状态（只读）】\n")[1].splitlines()[0])
        self.assertEqual(set(cognition), {"active_goal", "current_intention", "current_plan"})
        self.assertEqual(scheduling, {"agenda": [{"intention": "继续调查", "due_tick": 300}], "busy_until": 290})
        self.assertNotIn('"id": "visit"', prompt)
        self.assertIn("不得在 cognition 中写入或清空 agenda、busy_until", prompt)

    def test_old_snapshot_history_is_pruned_but_pending_and_busy_restore(self):
        saved = deepcopy(snapshot_world())
        raw = self.cognition().to_dict()
        raw["agenda"] += [dict(id=f"old-{i}", character="林默", due_tick=i,
                               intention="已结束的活动", status="completed" if i % 2 else "cancelled")
                          for i in range(1000)]
        saved["characters"]["林默"]["runtime_state"] = raw
        restore_snapshot(saved)
        self.assertEqual(self.lin().runtime_state.to_dict(), self.cognition().to_dict())
        self.assertEqual(len(self.lin().runtime_state.agenda), 1)

    def test_mcp_payload_and_local_snapshot_exclude_terminal_agenda(self):
        runtime = self.cognition()
        runtime.agenda.extend(AgendaEntry(f"old-{i}", "林默", i, "历史安排", "cancelled") for i in range(1000))
        self.lin().runtime_state = runtime
        backend = RemoteWorld(WORLD_STATE["world_id"])
        with patch.object(backend, "_call") as call:
            backend.save_agent_state({"tick_count": 7})
        payload = json.loads(call.call_args.args[1]["agentStateJson"])
        self.assertEqual(payload["characters"]["林默"]["runtime_state"], self.cognition().to_dict())
        self.assertEqual(snapshot_world()["characters"]["林默"]["runtime_state"], self.cognition().to_dict())
        self.assertEqual(len(runtime.agenda), 1)

    def test_prompt_projects_pending_only_even_with_historical_runtime_context(self):
        raw = self.cognition().to_dict()
        raw["agenda"][0]["id"] = "private-internal-uuid"
        raw["agenda"].extend(dict(id=f"old-{status}", character="林默", due_tick=1,
                                 intention=f"hidden-{status}-history", status=status)
                             for status in ("completed", "cancelled"))
        prompt = build_action_prompt(self.lin(), active_goal=self.lin().goals[1], memories=[],
                                     retrieved_context=[], lore_context=[], observations=[], runtime_context=raw)
        scheduling = json.loads(prompt.split("【系统调度状态（只读）】\n")[1].splitlines()[0])
        self.assertEqual(scheduling, {"agenda": [{"intention": "继续调查", "due_tick": 300}], "busy_until": 290})
        for private in ("private-internal-uuid", "hidden-completed-history", "hidden-cancelled-history"):
            self.assertNotIn(private, prompt)

    def test_private_cognition_only_enters_owner_prompt(self):
        WORLD_STATE["characters"]["苏晚"].runtime_state.current_plan = "秘密计划：保护弟弟"
        self.assertNotIn("秘密计划", build_model_prompt(create_initial_agent_state(self.lin(), self.index)))
        self.assertIn("秘密计划", build_model_prompt(create_initial_agent_state(
            WORLD_STATE["characters"]["苏晚"], self.index)))

    def test_agenda_and_busy_do_not_change_event_scheduler(self):
        self.lin().runtime_state = self.cognition()
        self.lin().runtime_state.agenda[0].due_tick = 0
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        with patch("tools.remote_world.active_backend", return_value=backend):
            scheduler = WorldTickScheduler()
            seen = [scheduler.run_tick(lambda character: "等待")["character"] for _ in WORLD_STATE["characters"]]
            self.assertIn("林默", seen)  # busy 目前不阻塞开局或事件机会。
            self.assertEqual(scheduler.run_tick(lambda character: "等待")["character"], "世界")
        self.assertEqual(self.lin().runtime_state.agenda[0].status, "pending")

    def test_session_saves_cognition_when_model_summary_fails_after_action(self):
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        def decide(character):
            character.runtime_state = self.cognition()
            committed_event("inspect", character.name, "核对现场", payload={"observation": "没有异常"})
            raise RuntimeError("总结失败")
        with patch("tools.remote_world.active_backend", return_value=backend), \
                patch("agent.session.active_backend", return_value=backend), \
                patch("agent.session.save_world") as save:
            session = WorldSession(decide, save_path=Path("unused"), index=self.index)
            result = session.next_tick()
        self.assertIn("行动已发生", result["action_result"])
        backend.save_agent_state.assert_called_once()
        save.assert_called_once()
        self.assertEqual(self.lin().runtime_state.to_dict(), self.cognition().to_dict())
