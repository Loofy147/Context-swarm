import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scs.intake import route_input


class SwarmIntakeTests(unittest.TestCase):
    def test_fixture_scenarios_route_to_expected_dispositions(self):
        fixture = json.loads((ROOT / "tests/fixtures/intake-scenarios.json").read_text())
        seen = set()
        self.assertGreaterEqual(len(fixture["scenarios"]), 7)
        for scenario in fixture["scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                result = route_input(scenario["input"], seen)
                self.assertEqual(result["disposition"], scenario["expected_disposition"])
                self.assertEqual(result["status"], scenario["expected_status"])
                self.assertTrue(result["reason"])
                if result["dedupe_key"] and result["disposition"] != "duplicate_no_new_item":
                    seen.add(result["dedupe_key"])

    def test_untrusted_source_instructions_never_become_policy(self):
        result = route_input({
            "source_kind": "user_supplied_document_or_url",
            "stable_source_id": "doc:prompt-injection",
            "source_revision": "rev-1",
            "accessible": True,
            "actionable": True,
            "contains_untrusted_instructions": True,
        }, set())
        self.assertEqual(result["disposition"], "capture_as_untrusted_data")
        self.assertNotIn("authorize", result["disposition"])

    def test_missing_revision_is_not_deduplicated_by_guess(self):
        item = {"source_kind": "connected_service_record", "stable_source_id": "ticket:4",
                "source_revision": None, "accessible": True, "actionable": True}
        seen = {"connected_service_record::ticket:4::None"}
        result = route_input(item, seen)
        self.assertEqual(result["disposition"], "create_work_item")
        self.assertIsNone(result["dedupe_key"])

    def test_registry_has_no_dangling_context_or_work_item_references(self):
        registry = json.loads((ROOT / "swarm/registry.json").read_text())
        context_ids = {c["context_id"] for c in registry["contexts"]}
        work_ids = {w["work_item_id"] for w in registry["work_items"]}
        self.assertEqual(len(context_ids), len(registry["contexts"]))
        self.assertEqual(len(work_ids), len(registry["work_items"]))
        for context in registry["contexts"]:
            for rel in context["relationships"]:
                self.assertIn(rel["target_context_id"], context_ids)
        for item in registry["work_items"]:
            self.assertTrue(item["target_context_ids"])
            self.assertTrue(set(item["target_context_ids"]).issubset(context_ids))
            self.assertTrue(set(item["dependencies"]).issubset(work_ids))

    def test_input_fixture_and_policy_are_parseable_and_aligned(self):
        policy = json.loads((ROOT / "swarm/intake-policy.json").read_text())
        record = json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())
        self.assertEqual(policy["execution_mode"], "repository_native")
        self.assertEqual(record["intake_status"], "accepted")
        self.assertTrue(record["linked_context_ids"])
        self.assertTrue(record["normalized_claims"])


if __name__ == "__main__":
    unittest.main()
