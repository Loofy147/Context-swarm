import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scs.intake import build_seen_revision_index, route_input
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

    def test_seen_revision_index_uses_locator_and_digest_fallbacks(self):
        records = [
            {"source_kind": "web_source", "source_locator": "https://example.invalid/spec", "source_revision": "etag-1"},
            {"source_kind": "repository_file", "content_digest": {"algorithm": "sha256", "value": "a" * 64}},
        ]
        seen = build_seen_revision_index(records)
        locator_item = {"source_kind": "web_source", "source_locator": "https://example.invalid/spec",
                        "source_revision": "etag-1", "accessible": True, "actionable": True}
        digest_item = {"source_kind": "repository_file",
                       "content_digest": {"algorithm": "sha256", "value": "a" * 64},
                       "accessible": True, "actionable": True}
        self.assertEqual(route_input(locator_item, seen)["disposition"], "duplicate_no_new_item")
        self.assertEqual(route_input(digest_item, seen)["disposition"], "duplicate_no_new_item")

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
            "schemas/capability-verification.schema.json",
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
        errors = list(Draft202012Validator(reg_schema, registry=registry, format_checker=FormatChecker()).iter_errors(registry_data))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        input_data = json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())
        input_schema = schemas["schemas/input-record.schema.json"]
        errors = list(Draft202012Validator(input_schema, format_checker=FormatChecker()).iter_errors(input_data))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        policy = json.loads((ROOT / "swarm/intake-policy.json").read_text())
        policy_schema = schemas["schemas/intake-policy.schema.json"]
        errors = list(Draft202012Validator(policy_schema, format_checker=FormatChecker()).iter_errors(policy))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        matrix = json.loads((ROOT / "swarm/capability-matrix.json").read_text())
        matrix_schema = schemas["schemas/capability-matrix.schema.json"]
        errors = list(Draft202012Validator(matrix_schema, format_checker=FormatChecker()).iter_errors(matrix))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

    def test_capability_matrix_separates_reads_writes_and_privileged_actions(self):
        matrix = json.loads((ROOT / "swarm/capability-matrix.json").read_text())
        self.assertFalse(matrix["universal_access_claim"])
        caps = {item["capability_id"]: item for item in matrix["capabilities"]}
        self.assertEqual(caps["github.repository.read"]["write_operations"], [])
        self.assertEqual(caps["github.repository.privileged"]["approval_gate"], "explicit_per_action")
        self.assertTrue(caps["github.repository.content_write"]["explicit_scope_required"])
        self.assertTrue(caps["connected_service.read"]["limitations"])

    def test_source_catalog_and_tool_surface_are_structured_and_scoped(self):
        catalog = json.loads((ROOT / "swarm/source-catalog.json").read_text())
        catalog_schema = json.loads((ROOT / "schemas/source-catalog.schema.json").read_text())
        errors = list(Draft202012Validator(catalog_schema, format_checker=FormatChecker()).iter_errors(catalog))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        surface = json.loads((ROOT / "swarm/sources/connected-tool-surface.json").read_text())
        surface_schema = json.loads((ROOT / "schemas/tool-surface-observation.schema.json").read_text())
        errors = list(Draft202012Validator(surface_schema, format_checker=FormatChecker()).iter_errors(surface))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])
        self.assertEqual(sum(group["tool_count"] for group in surface["namespaces"]) + len(surface["non_mcp_tool_names"]), surface["total_tool_definitions"])
        self.assertFalse(surface["resource_access_confirmed"])
        self.assertIn("GitHub", [group["namespace"] for group in surface["namespaces"]])
        self.assertTrue(any(source["source_id"] == "src-other-connected-services" for source in catalog["sources"]))

    def test_resource_scoped_capability_verification_is_schema_valid_and_not_universal(self):
        verification = json.loads((ROOT / "swarm/sources/capability-verification-2026-10-26.json").read_text())
        verification_schema = json.loads((ROOT / "schemas/capability-verification.schema.json").read_text())
        errors = list(Draft202012Validator(verification_schema, format_checker=FormatChecker()).iter_errors(verification))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])
        self.assertFalse(verification["universal_access_claim"])

        surface = json.loads((ROOT / "swarm/sources/connected-tool-surface.json").read_text())
        available_actions = {
            action
            for group in surface["namespaces"]
            for action in group["tool_names"]
        } | set(surface["non_mcp_tool_names"])
        matrix = json.loads((ROOT / "swarm/capability-matrix.json").read_text())
        capability_ids = {item["capability_id"] for item in matrix["capabilities"]}
        resources = {item["resource_id"]: item for item in verification["resources"]}
        github = resources["Loofy147/Context-swarm"]
        self.assertEqual(github["access_status"], "verified_read_write")
        self.assertTrue(github["permission_snapshot"]["pull"])
        self.assertTrue(github["permission_snapshot"]["push"])
        self.assertTrue(any(check["permission_class"] == "read" for check in github["checks"]))
        self.assertTrue(any(check["permission_class"] == "write" for check in github["checks"]))
        for resource in verification["resources"]:
            for check in resource["checks"]:
                with self.subTest(action=check["action_name"], target=check["target"]):
                    self.assertIn(check["action_name"], available_actions)
                    self.assertIn(check["capability_id"], capability_ids)
                    self.assertTrue(check["current_schema_resolved"])
                    self.assertTrue(check["target"])
                    self.assertTrue(check["task_scope"])

        example_kinds = {item["kind"] for item in verification["replayable_examples"]}
        self.assertTrue({"read_only", "blocked", "approval_gated"}.issubset(example_kinds))
        self.assertTrue(verification["unverified_scopes"])
        self.assertFalse(surface["resource_access_confirmed"])

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
