import unittest
from copy import deepcopy
from unittest.mock import Mock

from agent.graph import build_model_prompt
from agent.perception import observe
from agent.state import create_initial_agent_state
from tests.support import committed_event
from world.state import WORLD_STATE


class PerceptionTest(unittest.TestCase):
    def setUp(self):
        self.original = WORLD_STATE.copy()
        WORLD_STATE.clear()
        WORLD_STATE.update(deepcopy(self.original))

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original)

    def test_nearby_people_and_witnessed_events_enter_only_owner_prompt(self):
        lin = WORLD_STATE["characters"]["林默"]
        su = WORLD_STATE["characters"]["苏晚"]
        zhao = WORLD_STATE["characters"]["赵无极"]
        lin.location = su.location
        event = committed_event("talk", "林默", "林默对苏晚说：秘密线索", target="苏晚",
                             location=lin.location, payload={"message": "秘密线索"})
        self.assertEqual(event["perceived_by"], ["林默", "苏晚"])
        self.assertIn("同地点角色：苏晚", observe(lin))
        index = Mock()
        index.retrieve_memory.return_value = []
        index.retrieve_lore.return_value = []
        self.assertIn("秘密线索", build_model_prompt(create_initial_agent_state(lin, index)))
        self.assertNotIn("秘密线索", build_model_prompt(create_initial_agent_state(zhao, index)))


if __name__ == "__main__":
    unittest.main()
