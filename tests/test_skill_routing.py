import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from agent.tick import WorldTickScheduler
from characters.prompt import build_action_prompt
from skills.investigation.workflow import completed_step, next_step
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
            item["properties"].pop("legacy_concealable", None)
        self.assertIsNone(choose_skill(WORLD_STATE["characters"]["苏晚"]))

    def test_conceal_inspect_recover_chain_uses_only_visible_steps(self):
        su = WORLD_STATE["characters"]["苏晚"]
        lin = self.detective()
        object_name = "住客登记簿"
        trace = object_name + "被移动的痕迹"
        self.assertEqual(current_step(su).tool, "take")
        original_item = next(item for item in current_objects().values() if item["name"] == object_name)
        original = original_item["description"]
        original_item["visible"] = False
        trace_item = make_object(trace, su.location, "异常痕迹")
        trace_item["portable"] = False
        trace_item["properties"]["trace_for"] = original_item["id"]
        current_objects()[trace_item["id"]] = trace_item
        committed_event("conceal", su.name, "苏晚藏起登记簿", location=su.location,
                        payload={"object_name": object_name, "trace_name": trace})
        self.assertIsNone(current_step(su))
        self.assertNotIn(original, self.prompt())

        lin.location = su.location
        committed_event("move", lin.name, "林默到达客栈", location=lin.location,
                        payload={"from": "县衙", "to": lin.location})
        self.assertIn(trace, [item["name"] for item in visible_objects(lin)])
        committed_event("inspect", lin.name, "林默调查痕迹", location=lin.location,
                        payload={"object_name": trace, "observation": "异常痕迹"})
        self.assertNotEqual(current_step(lin).tool, "recover_clue")
        current_objects().pop(trace_item["id"])
        original_item["visible"] = True
        committed_event("recover", lin.name, "林默找回登记簿", location=lin.location,
                        payload={"object_name": object_name})
        self.assertNotEqual(current_step(lin).tool if current_step(lin) else None, "recover_clue")
        self.assertFalse(any(fact.object_name == trace for fact in lin.semantic_memory.current_facts()))

        saved = deepcopy(snapshot_world())
        restore_snapshot(saved)
        self.assertIn(object_name, WORLD_STATE["inspectable_objects"][lin.location])

    def test_unrelated_committed_action_does_not_complete_skill_step(self):
        person = self.detective()
        step = next_step(person, person.goals[0])
        event = {"actor": person.name, "type": "talk", "target": "苏晚",
                 "location": person.location, "payload": {"message": "你好"}}
        self.assertFalse(completed_step(step, event, person.name))
        event = {**event, "type": "move", "location": "晚风客栈"}
        self.assertTrue(completed_step(step, event, person.name))

    def test_committed_step_queues_continuation_across_scheduler_restore(self):
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        scheduler = WorldTickScheduler()
        scheduler.restore({"tick_count": 0, "event_cursor": 0,
                           "pending": [{"name": "林默", "depth": 0}]})

        def move_to_lead(character):
            character.location = "晚风客栈"
            committed_event("move", character.name, "抵达客栈", location=character.location,
                            payload={"from": "县衙", "to": "晚风客栈"})
            return "已移动"

        with patch("tools.remote_world.active_backend", return_value=backend):
            scheduler.run_tick(move_to_lead)
            saved = scheduler.snapshot()
            self.assertIn({"name": "林默", "depth": 0, "source": "skill"}, saved["pending"])
            restored = WorldTickScheduler()
            restored.restore(saved)
            seen = [restored.run_tick(lambda character: "等待")["character"]
                    for _ in saved["pending"]]
            self.assertIn("林默", seen)
            self.assertEqual(restored.snapshot()["pending"], [])

    def test_skill_continuation_ablation_keeps_same_action_and_tools(self):
        opening = deepcopy(snapshot_world())
        backend = Mock()
        backend.advance_time.return_value = "08:05"

        def one_run(skill_enabled):
            restore_snapshot(deepcopy(opening))
            scheduler = WorldTickScheduler()
            scheduler.restore({"tick_count": 0, "event_cursor": 0,
                               "pending": [{"name": "林默", "depth": 0}]})

            def same_action(character):
                character.location = "晚风客栈"
                committed_event("move", character.name, "抵达客栈", location=character.location,
                                payload={"from": "县衙", "to": "晚风客栈"})
                return "已移动"

            with patch("tools.remote_world.active_backend", return_value=backend):
                if skill_enabled:
                    scheduler.run_tick(same_action)
                else:
                    with patch("skills.router.current_step", return_value=None):
                        scheduler.run_tick(same_action)
            return scheduler.snapshot()["pending"], len(WORLD_STATE["events"])

        with_skill, with_events = one_run(True)
        without_skill, without_events = one_run(False)
        self.assertEqual(with_events, without_events)
        self.assertIn({"name": "林默", "depth": 0, "source": "skill"}, with_skill)
        self.assertFalse(any(item["name"] == "林默" for item in without_skill))


if __name__ == "__main__":
    unittest.main()
