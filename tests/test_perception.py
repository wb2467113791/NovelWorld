import unittest
from copy import deepcopy
from unittest.mock import Mock

from agent.graph import build_model_prompt
from agent.perception import observe
from agent.state import create_initial_agent_state
from tests.support import committed_event
from world.state import WORLD_STATE
from characters.model import PlayerActor
from world.persistence import restore_snapshot, snapshot_world
from world.objects import current_objects
from tools.remote_world import RemoteWorld
import json


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

    def test_report_is_subjective_owner_only_and_inspection_stays_verified(self):
        lin = WORLD_STATE["characters"]["林默"]
        lin.location = "晚风客栈"
        WORLD_STATE["characters"]["玩家"] = PlayerActor("玩家", lin.location)
        before = deepcopy(current_objects())
        event = committed_event("talk", "玩家", "玩家说钥匙在县衙", target="林默", payload={"message": "钥匙在县衙"})
        entry = next(value for value in lin.belief_memory.entries if value.source_event_id == event["id"])
        self.assertEqual((entry.source_actor, entry.confidence, entry.status), ("玩家", 0.5, "active"))
        self.assertEqual(current_objects(), before)
        self.assertFalse(lin.semantic_memory.current_facts())
        self.assertFalse(hasattr(WORLD_STATE["characters"]["玩家"], "belief_memory"))
        self.assertFalse(any(value.source_event_id == event["id"] for value in WORLD_STATE["characters"]["苏晚"].belief_memory.entries))
        committed_event("talk", "苏晚", "苏晚说钥匙在客栈", target="林默", payload={"message": "钥匙在客栈"})
        committed_event("inspect", "林默", "本人查看钥匙", payload={"object_name": "钥匙", "object_id": "key", "observation": "钥匙在客栈"})
        index = Mock(); index.retrieve_memory.return_value = ["历史经历：玩家曾说钥匙在县衙", "已核实调查：钥匙在客栈"]
        index.retrieve_lore.return_value = []
        prompt = build_model_prompt(create_initial_agent_state(lin, index))
        verified = prompt.split("【已验证事实")[1].split("【未验证说法")[0]
        self.assertIn("钥匙在客栈", verified); self.assertNotIn("钥匙在县衙", verified)
        self.assertIn("玩家曾说", prompt); self.assertIn("苏晚曾说", prompt)
        self.assertNotIn("钥匙在县衙", build_model_prompt(create_initial_agent_state(WORLD_STATE["characters"]["赵无极"], index)).split("【未验证说法")[1].split("【检索到")[0])

    def test_beliefs_merge_stay_bounded_and_restore_refresh_worlds_independently(self):
        lin = WORLD_STATE["characters"]["林默"]; lin.location = "晚风客栈"
        for _ in range(8):
            committed_event("talk", "苏晚", "重复说法", target="林默", payload={"message": "同一  说法"})
        reports = [entry for entry in lin.belief_memory.entries if entry.source_type == "report"]
        self.assertEqual(len(reports), 1); self.assertEqual(len(reports[0].evidence_event_ids), 5)
        for number in range(60):
            committed_event("talk", "苏晚", "说法", target="林默", payload={"message": f"说法 {number}"})
        self.assertEqual(len(lin.belief_memory.entries), 50)
        saved = deepcopy(snapshot_world()); expected = lin.belief_memory.to_dict()
        backend = RemoteWorld(WORLD_STATE["world_id"]); backend._call = Mock(return_value=json.dumps(saved))
        backend._refresh_business_state()
        self.assertEqual(WORLD_STATE["characters"]["林默"].belief_memory.to_dict(), expected)
        backend.save_agent_state({"tick_count": 0})
        self.assertEqual(json.loads(backend._call.call_args.args[1]["agentStateJson"])["characters"]["林默"]["belief_memory"], expected)
        other = deepcopy(saved); other["world_id"] = "belief-other"; other["events"] = []
        for person in other["characters"].values(): person.pop("belief_memory", None)
        restore_snapshot(other)
        self.assertFalse(any(entry.source_type == "report" for entry in WORLD_STATE["characters"]["林默"].belief_memory.entries))
        restore_snapshot(saved)
        self.assertEqual(WORLD_STATE["characters"]["林默"].belief_memory.to_dict(), expected)


if __name__ == "__main__":
    unittest.main()
