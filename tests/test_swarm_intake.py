import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scs.intake import route_input
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


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

    def test_consequential_action_gate_precedes_untrusted_content_routing(self):
        result = route_input({
            "source_kind": "user_supplied_document_or_url",
            "stable_source_id": "doc:unsafe-release",
            "source_revision": "rev-1",
            "accessible": True,
            "actionable": True,
            "contains_untrusted_instructions": True,
            "consequence_class": "C",
            "separate_authorization_present": False,
        }, set())
        self.assertEqual(result["disposition"], "hold_for_authorization")
        self.assertEqual(result["status"], "blocked")

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

    def test_repository_state_records_validate_against_json_schemas(self):
        schema_paths = [
            "schemas/context-state.schema.json",
            "schemas/work-item.schema.json",
            "schemas/registry.schema.json",
            "schemas/input-record.schema.json",
            "schemas/intake-policy.schema.json",
            "schemas/capability-matrix.schema.json",
        ]
        schemas = {p: json.loads((ROOT / p).read_text()) for p in schema_paths}
        for path, schema in schemas.items():
            with self.subTest(schema=path):
                Draft202012Validator.check_schema(schema)

        registry = Registry()
        for schema in schemas.values():
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        format_checker = FormatChecker()

        registry_data = json.loads((ROOT / "swarm/registry.json").read_text())
        reg_schema = schemas["schemas/registry.schema.json"]
        errors = list(Draft202012Validator(reg_schema, registry=registry, format_checker=format_checker).iter_errors(registry_data))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        input_data = json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())
        input_schema = schemas["schemas/input-record.schema.json"]
        errors = list(Draft202012Validator(input_schema, format_checker=format_checker).iter_errors(input_data))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        policy = json.loads((ROOT / "swarm/intake-policy.json").read_text())
        policy_schema = schemas["schemas/intake-policy.schema.json"]
        errors = list(Draft202012Validator(policy_schema, format_checker=format_checker).iter_errors(policy))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        matrix = json.loads((ROOT / "swarm/capability-matrix.json").read_text())
        matrix_schema = schemas["schemas/capability-matrix.schema.json"]
        errors = list(Draft202012Validator(matrix_schema, format_checker=format_checker).iter_errors(matrix))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

    def test_capability_matrix_separates_reads_writes_and_privileged_actions(self):
        matrix = json.loads((ROOT / "swarm/capability-matrix.json").read_text())
        self.assertFalse(matrix["universal_access_claim"])
        caps = {item["capability_id"]: item for item in matrix["capabilities"]}
        self.assertEqual(caps["github.repository.read"]["write_operations"], [])
        self.assertEqual(caps["github.repository.privileged"]["approval_gate"], "explicit_per_action")
        self.assertTrue(caps["github.repository.content_write"]["explicit_scope_required"])
        self.assertTrue(caps["connected_service.read"]["limitations"])

    def test_schema_alignment_record_exists_and_separates_current_from_future(self):
        alignment = (ROOT / "spec/schema-alignment.md").read_text().lower()
        self.assertIn("repository-native", alignment)
        self.assertIn("future runtime", alignment)
        self.assertIn("do not apply a migration", alignment)

    def test_repository_dependency_map_points_to_existing_paths(self):
        mapping = json.loads((ROOT / "swarm/dependency-map.json").read_text())
        self.assertTrue(mapping["edges"])
        for edge in mapping["edges"]:
            for key in ("source_path", "target_path"):
                target = edge[key]
                if target.startswith("http://") or target.startswith("https://"):
                    continue
                with self.subTest(edge=edge, field=key):
                    self.assertTrue((ROOT / target).exists(), f"missing dependency target: {target}")

    def test_input_fixture_and_policy_are_parseable_and_aligned(self):
        policy = json.loads((ROOT / "swarm/intake-policy.json").read_text())
        record = json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())
        self.assertEqual(policy["execution_mode"], "repository_native")
        self.assertEqual(record["intake_status"], "accepted")
        self.assertTrue(record["linked_context_ids"])
        self.assertTrue(record["normalized_claims"])


if __name__ == "__main__":
    unittest.main()
