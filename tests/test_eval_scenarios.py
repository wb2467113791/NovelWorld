"""固定评测场景的最小有效性检查。"""

import unittest
import json

from eval.scenarios import SCENARIOS
from world.state import WORLD_STATE


class ScenarioCatalogTest(unittest.TestCase):
    def test_scenarios_have_valid_fixed_starting_points(self):
        self.assertEqual(len(SCENARIOS), 9)
        self.assertEqual(len({scenario.id for scenario in SCENARIOS}), 9)

        characters = WORLD_STATE["characters"]
        locations = WORLD_STATE["locations"]
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.id):
                self.assertIn(scenario.actor, characters)
                self.assertTrue(scenario.expected_behavior)
                for name, location in scenario.location_overrides:
                    self.assertIn(name, characters)
                    self.assertIn(location, locations)
                for name, fact in scenario.fact_additions:
                    self.assertIn(name, characters)
                    self.assertTrue(fact)
                for name, memory in scenario.memory_additions:
                    self.assertIn(name, characters)
                    self.assertTrue(memory)
                for name, arguments, location in scenario.prior_actions:
                    self.assertTrue(name)
                    self.assertIsInstance(json.loads(arguments), dict)
                    self.assertIn(location, locations)

    def test_forbidden_secrets_are_not_in_actors_starting_knowledge(self):
        leakage_scenarios = [
            scenario for scenario in SCENARIOS
            if scenario.focus == "knowledge_leakage"
        ]
        self.assertEqual(len(leakage_scenarios), 2)
        for scenario in leakage_scenarios:
            actor = WORLD_STATE["characters"][scenario.actor]
            actor_facts = actor.known_facts + actor.secrets
            actor_facts += [
                fact for name, fact in scenario.fact_additions
                if name == scenario.actor
            ]
            for forbidden in scenario.forbidden_facts:
                with self.subTest(scenario=scenario.id, forbidden=forbidden):
                    self.assertNotIn(forbidden, actor_facts)


if __name__ == "__main__":
    unittest.main()
