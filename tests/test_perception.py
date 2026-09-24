import unittest

from agent.perception import observe
from agent.state import create_initial_agent_state
from characters.prompt import build_action_prompt
from world.persistence import start_new_world
from world.state import WORLD_STATE, record_event


class PerceptionTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        start_new_world()

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def test_nearby_people_and_witnessed_events_enter_only_owner_prompt(self):
        lin = WORLD_STATE["characters"]["林默"]
        su = WORLD_STATE["characters"]["苏晚"]
        zhao = WORLD_STATE["characters"]["赵无极"]
        lin.location = su.location
        event = record_event("talk", "林默", "林默对苏晚说：秘密线索", target="苏晚",
                             location=lin.location, payload={"message": "秘密线索"})
        self.assertEqual(event["perceived_by"], ["林默", "苏晚"])
        self.assertIn("同地点角色：苏晚", observe(lin))
        self.assertIn("秘密线索", build_action_prompt(lin, observations=create_initial_agent_state(lin)["perception"]))
        self.assertNotIn("秘密线索", build_action_prompt(zhao, observations=create_initial_agent_state(zhao)["perception"]))


if __name__ == "__main__":
    unittest.main()
