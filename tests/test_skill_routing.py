import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from agent.tick import WorldTickScheduler
from characters.prompt import build_action_prompt
from skills.router import choose_skill, skill_for
from world.persistence import snapshot_world
from world.state import WORLD_STATE


class InvestigationSkillTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def test_guidance_is_pure_stable_and_goal_specific(self):
        detective = WORLD_STATE["characters"]["林默"]
        owner = WORLD_STATE["characters"]["苏晚"]
        before = deepcopy(snapshot_world())
        self.assertEqual(choose_skill(detective), "investigation")
        self.assertEqual(choose_skill(owner), "concealment")
        self.assertIsNone(choose_skill(detective, "休息并吃饭"))
        advice = skill_for(detective)
        self.assertIsInstance(advice, str)
        for text in (advice, skill_for(owner)):
            for forbidden in ("object_id", "listener", "destination", "建议参数", "建议工具", "当前阶段"):
                self.assertNotIn(forbidden, text)
            self.assertIn("不是必须执行的计划", text)
        for word in ("verified semantic", "reported belief", "独立证据", "inspect", "talk", "take", "put"):
            self.assertIn(word, advice)
        self.assertEqual(before, snapshot_world())
        detective.energy = 0
        detective.location = "晚风客栈"
        WORLD_STATE["objects"] = {}
        self.assertEqual(advice, skill_for(detective))
        detective.runtime_state.active_goal = "保护线索"
        self.assertEqual(choose_skill(detective), "concealment")

    def test_prompt_knowledge_and_scheduler_independence(self):
        person = WORLD_STATE["characters"]["林默"]
        prompt = build_action_prompt(person, active_goal=person.goals[0], memories=[],
                                     retrieved_context=[], lore_context=[], observations=[])
        self.assertIn("【角色技能知识】", prompt)
        self.assertIn("不是必须执行的计划", prompt)
        self.assertIn("简化社交倾向", prompt)
        self.assertNotIn(WORLD_STATE["characters"]["苏晚"].secrets[0], prompt)
        backend = Mock()
        backend.advance_time.return_value = "08:05"
        scheduler = WorldTickScheduler()
        with patch("tools.remote_world.active_backend", return_value=backend), \
                patch("skills.router.skill_for", side_effect=AssertionError("Scheduler 不读取 Skill")):
            results = [scheduler.run_tick(lambda _: "等待") for _ in range(12)]
        self.assertTrue(any(item["source"] == "agenda" for item in results))
        self.assertNotIn("skill_views", scheduler.snapshot())
        self.assertTrue(all(item["source"] != "skill" for item in results))
