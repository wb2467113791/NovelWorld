import unittest
from copy import deepcopy

from agent.director import Director
from characters.prompt import build_action_prompt
from skills.router import choose_skill
from world.state import INITIAL_WORLD_STATE, WORLD_STATE, record_event


class V3DirectorAndSkillTests(unittest.TestCase):
    def setUp(self):
        self.previous = deepcopy(WORLD_STATE)
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(INITIAL_WORLD_STATE))

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.previous)

    def test_only_relevant_skill_enters_prompt(self):
        lin = WORLD_STATE["characters"]["林默"]
        self.assertEqual(choose_skill(lin), "investigation")
        prompt = build_action_prompt(lin, retrieved_context=[], lore_context=[])
        self.assertIn("先区分亲眼调查", prompt)
        self.assertNotIn("交付物品前确认自己持有", prompt)

    def test_director_event_reaches_only_characters_at_location(self):
        director = Director()
        for actor in ("林默", "苏晚", "赵无极"):
            record_event("narration", actor, f"{actor}没有行动")
        positions = {name: person.location for name, person in WORLD_STATE["characters"].items()}
        event = director.maybe_inject(3)
        self.assertEqual(event["type"], "director")
        self.assertEqual(event["actor"], "世界")
        self.assertEqual(event["location"], "晚风客栈")
        self.assertEqual(WORLD_STATE["inspectable_objects"]["晚风客栈"][event["payload"]["object_name"]],
                         event["payload"]["observation"])
        self.assertEqual(positions, {name: person.location for name, person in WORLD_STATE["characters"].items()})
        self.assertTrue(WORLD_STATE["characters"]["苏晚"].memory.recent_entries())
        self.assertTrue(any(entry.source_event_id == event["id"] for entry in WORLD_STATE["characters"]["苏晚"].memory.recent_entries()))
        self.assertFalse(any(entry.source_event_id == event["id"] for entry in WORLD_STATE["characters"]["林默"].memory.recent_entries()))
        self.assertIsNone(director.maybe_inject(4))

    def test_participation_and_conflict_detection(self):
        for number in range(6):
            record_event("inspect", "林默", f"林默调查案卷{number}", payload={"observation": "案卷"})
        self.assertEqual(Director().choose_event(6)[0], "participation")

        WORLD_STATE["events"].clear()
        for actor in ("林默", "苏晚", "赵无极") * 2:
            record_event("inspect", actor, f"{actor}调查", payload={"observation": "周围"})
        self.assertEqual(Director().choose_event(6)[0], "conflict")

    def test_director_proposal_runs_only_when_rule_triggers(self):
        calls = []
        director = Director(propose_event=lambda category, location: calls.append((category, location)) or "门边出现一封信")
        self.assertIsNone(director.maybe_inject(1))
        self.assertEqual(calls, [])
        for actor in ("林默", "苏晚", "赵无极"):
            record_event("narration", actor, f"{actor}没有行动")
        event = director.maybe_inject(3)
        self.assertEqual(calls, [("stagnation", "晚风客栈")])
        self.assertEqual(event["payload"]["observation"], "门边出现一封信")
        self.assertIsNone(director.maybe_inject(4))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
