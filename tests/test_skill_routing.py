import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from agent.tick import WorldTickScheduler
from characters.prompt import build_action_prompt
from skills.investigation.workflow import next_step
from skills.router import choose_skill, current_step
from tests.support import committed_event
from world.persistence import restore_snapshot, snapshot_world
from world.state import WORLD_STATE
from world.objects import current_objects, make_object, visible_objects


class InvestigationSkillTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def detective(self):
        return WORLD_STATE["characters"]["林默"]

    def step_name(self, step):
        return current_objects()[step.arguments["object_id"]]["name"]

    def prompt(self):
        person = self.detective()
        return build_action_prompt(
            person, active_goal=person.goals[0], memories=[], retrieved_context=[],
            lore_context=[], observations=[],
        )

    def test_workflow_advances_from_lead_to_inspection_to_question_and_stops(self):
        person = self.detective()
        step = next_step(person, person.goals[0])
        self.assertEqual((step.tool, step.arguments["location"]),
                         ("move_character", "晚风客栈"))
        self.assertIn("建议工具：move_character", self.prompt())

        person.location = "晚风客栈"
        committed_event("move", person.name, "到达客栈", location=person.location,
                        payload={"from": "县衙", "to": "晚风客栈"})
        for item in [obj for obj in visible_objects(person) if obj["holder"] is None]:
            object_name = item["name"]
            step = next_step(person, person.goals[0])
            self.assertEqual((step.tool, self.step_name(step)),
                             ("inspect", object_name))
            committed_event("inspect", person.name, "核对现场", location=person.location,
                            payload={"object_name": object_name, "observation": "未发现异常"})

        step = next_step(person, person.goals[0])
        self.assertEqual((step.tool, step.arguments["listener"]), ("talk", "苏晚"))
        committed_event("talk", person.name, "向苏晚询问", target="苏晚",
                        location=person.location, payload={"message": "你看到了什么？"})
        self.assertIsNone(next_step(person, person.goals[0]))
        self.assertNotIn("【当前行动策略】", self.prompt())

        committed_event("talk", "苏晚", "苏晚提到县衙", target=person.name,
                        location=person.location, payload={"message": "我听说县衙有新的案卷。"})
        self.assertEqual(next_step(person, person.goals[0]).arguments["location"], "县衙")

        item = make_object("新线索", person.location, "新出现的物件")
        current_objects()[item["id"]] = item  # 模拟 Java 新物件刷新
        self.assertEqual(self.step_name(next_step(person, person.goals[0])), "新线索")

    def test_progress_survives_snapshot_and_uses_only_owner_knowledge(self):
        person = self.detective()
        person.location = "晚风客栈"
        object_name = "住客登记簿"
        committed_event("inspect", person.name, "核对登记簿", location=person.location,
                        payload={"object_name": object_name, "observation": "未见具体时辰"})
        saved = deepcopy(snapshot_world())
        restore_snapshot(saved)
        self.assertEqual(self.step_name(next_step(self.detective(), self.detective().goals[0])),
                         "后门")
        self.assertNotIn(WORLD_STATE["characters"]["苏晚"].secrets[0], self.prompt())

    def test_only_actionable_skill_is_selected(self):
        self.assertEqual(choose_skill(WORLD_STATE["characters"]["苏晚"]), "concealment")
        self.assertIsNone(choose_skill(WORLD_STATE["characters"]["赵无极"]))
        self.detective().energy = 19
        self.assertIsNone(next_step(self.detective(), self.detective().goals[0]))
        for item in current_objects().values():
            item["visible"] = False
        self.assertIsNone(choose_skill(WORLD_STATE["characters"]["苏晚"]))

    def test_investigation_continues_via_agenda_across_scheduler_restore(self):
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        scheduler = WorldTickScheduler()
        scheduler.restore({"tick_count": 0, "event_cursor": 0,
                           "pending": [{"name": "林默", "depth": 0, "source": "bootstrap"}]})
        def move_to_lead(character):
            character.location = "晚风客栈"  # 模拟 Java 刷新
            committed_event("move", character.name, "抵达客栈", location=character.location,
                            payload={"from": "县衙", "to": "晚风客栈"})
            return "已移动"
        with patch("tools.remote_world.active_backend", return_value=backend):
            scheduler.run_tick(move_to_lead)
            saved = scheduler.snapshot()
            self.assertFalse(any(item.get("source") == "skill" for item in saved["pending"]))
            self.assertNotIn("skill_views", saved)
            entry = self.detective().runtime_state.agenda[0]
            self.assertEqual(entry.status, "pending")
            opening = deepcopy(snapshot_world(scheduler_state=saved))
            restore_snapshot(opening)
            restored = WorldTickScheduler()
            restored.restore(saved)
            opportunities = []
            def inspect_as_agent(character):
                # 建议只作上下文；此处 deterministic Agent 自己选择 inspect。
                step = current_step(character)
                opportunities.append((character.name, step.tool if step else None))
                if character.name == "林默" and step and step.tool == "inspect":
                    item = current_objects()[step.arguments["object_id"]]
                    committed_event("inspect", character.name, "已核对", payload={
                        "object_id": item["id"], "object_name": item["name"], "observation": "观察结果"})
                return "已决定"
            results = [restored.run_tick(inspect_as_agent) for _ in range(12)]
        self.assertGreaterEqual(opportunities.count(("林默", "inspect")), 2)
        self.assertTrue(any(item["source"] == "agenda" and item["character"] == "林默" for item in results))
        self.assertTrue(all(item["source"] != "skill" for item in results))

    def test_skill_context_never_controls_scheduler(self):
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        scheduler = WorldTickScheduler()
        with patch("tools.remote_world.active_backend", return_value=backend), \
                patch("skills.router.current_step", side_effect=AssertionError("Scheduler 不读取 Skill")):
            for _ in range(12):
                scheduler.run_tick(lambda character: "等待")
            self.assertNotIn("skill_views", scheduler.snapshot())
        self.assertTrue(all(person.runtime_state.agenda for person in WORLD_STATE["characters"].values()))


if __name__ == "__main__":
    unittest.main()
