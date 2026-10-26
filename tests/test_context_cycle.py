import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker
from scs.context_cycle import (
    ContextCyclePlanningError,
    compose_context_cycle_plan,
    plan_context_cycle,
)
from scs.runner import plan_github_observation_batch


def read_json(path):
    return json.loads((ROOT / path).read_text())


def make_input(**overrides):
    item = {
        "input_id": "IN-CC-001",
        "observed_at": "2026-10-26",
        "captured_by": "context-cycle-test",
        "access_boundary": "repository_fixture_only",
        "trust_status": "unreviewed",
        "classification": "test_task_request",
        "normalized_claims": [],
        "evidence_refs": [],
        "privacy_note": "Synthetic input for deterministic planner tests.",
        "source_kind": "issue_or_pull_request",
        "stable_source_id": "issue:context-cycle-001",
        "source_revision": "rev:1",
        "source_locator": "https://github.com/Loofy147/Context-swarm/issues/9001",
        "accessible": True,
        "actionable": True,
        "title": "Exercise integrated context cycle",
        "target_context_ids": ["ctx-scs-intake"],
        "acceptance_criteria": ["The composed plan validates and remains uncommitted."],
        "priority": {"level": "medium", "rationale": "Test declared priority only."},
    }
    item.update(overrides)
    return item


def changed_source():
    base = read_json("swarm/dependency-map.json")["reviewed_base_commit"]
    return {
        "stable_source_id": "repo-file:src/scs/intake.py",
        "source_kind": "repository_file",
        "previous_revision": "blob:before",
        "current_revision": "blob:after",
        "artifact_paths": ["src/scs/intake.py"],
        "evidence_refs": [f"https://github.com/Loofy147/Context-swarm/commit/{base}"],
    }


class ContextCycleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.registry = read_json("swarm/registry.json")
        self.dependency_map = read_json("swarm/dependency-map.json")
        self.base = self.dependency_map["reviewed_base_commit"]
        self.schema = read_json("schemas/context-cycle-plan.schema.json")

    def assert_schema_valid(self, plan):
        errors = list(Draft202012Validator(self.schema, format_checker=FormatChecker()).iter_errors(plan))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])
        self.assertFalse(plan["committed"])
        self.assertEqual([], plan["external_actions"])
        self.assertFalse(plan["batch_plan"]["committed"])
        self.assertFalse(plan["impact_plan"]["committed"])
        self.assertEqual([], plan["batch_plan"]["external_actions"])
        self.assertEqual([], plan["impact_plan"]["external_actions"])

        schemas = [
            ("schemas/batch-cycle-plan.schema.json", plan["batch_plan"]),
            ("schemas/impact-plan.schema.json", plan["impact_plan"]),
        ]
        for path, child in schemas:
            schema = read_json(path)
            child_errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(child))
            self.assertEqual([], [f"{path}: {'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
                                  for e in child_errors])

    def test_composes_captured_github_batch_with_unchanged_revision_observation(self):
        fixture = read_json("tests/fixtures/github-observations.json")
        snapshot = {
            "repository": fixture["repository"],
            "branch_head_sha": fixture["branch_head_sha"],
            "latest_commit": fixture["latest_commit"],
            "issues": fixture["issues"],
            "issues_query": fixture["issues_query"],
            "workflow_run": fixture["workflow_run"],
        }
        batch = plan_github_observation_batch(
            cycle_id="context-cycle-captured-input-0001",
            base_commit=self.base,
            repo_full_name="Loofy147/Context-swarm",
            observed_at="2026-10-26",
            source_snapshot=snapshot,
            registry_snapshot=self.registry,
        )
        observation = changed_source()
        observation["previous_revision"] = observation["current_revision"] = "same-revision"
        before = copy.deepcopy(self.registry)
        result = compose_context_cycle_plan(
            cycle_id=batch["cycle_id"], base_commit=batch["base_commit"],
            registry_snapshot=self.registry, dependency_map=self.dependency_map,
            batch_plan=batch, source_observations=[observation],
        )
        self.assert_schema_valid(result)
        self.assertEqual(before, self.registry)
        self.assertEqual(result["summary"]["input_count"], 4)
        self.assertEqual(result["summary"]["input_records_proposed"], 4)
        self.assertEqual(result["impact_plan"]["plan_status"], "no_change")
        self.assertEqual(result["summary"]["priority_proposals"],
                         len(result["priority_summary"]["proposed_work_items"]))
        counts = result["priority_summary"]["counts_by_level"]
        self.assertEqual(sum(counts.values()), result["summary"]["priority_proposals"])

    def test_changed_source_overlapping_context_update_requires_reconciliation(self):
        context = next(c for c in self.registry["contexts"] if c["context_id"] == "ctx-scs-intake")
        item = make_input(input_id="IN-CC-UPDATE", actionable=False,
                          verification_passed=True, consequence_class="A",
                          stable_source_id="input:update-context", source_revision="rev:update",
                          source_locator="input:update-context")
        options = {
            item["input_id"]: {
                "operation": "update_context",
                "context_update": {
                    "context_id": context["context_id"],
                    "expected_version": context["version"],
                    "patch": {"claims_append": [{
                        "claim_id": "claim:cycle-integration", "text": "Input routing is current."
                    }]},
                    "evidence_refs": ["test:evidence:context-cycle"],
                    "reason": "Exercise overlap between an intake update and source invalidation.",
                },
            }
        }
        before = copy.deepcopy(self.registry)
        result = plan_context_cycle(
            cycle_id="context-cycle-conflict-0001", base_commit=self.base,
            registry_snapshot=self.registry, dependency_map=self.dependency_map,
            input_items=[item], options_by_input_id=options,
            source_observations=[changed_source()],
        )
        self.assert_schema_valid(result)
        self.assertEqual(before, self.registry)
        self.assertEqual(result["plan_status"], "review_required")
        conflict = next(c for c in result["context_conflicts"] if c["context_id"] == "ctx-scs-intake")
        self.assertIn("direct", conflict["impact_kinds"])
        self.assertIn("stale_context", conflict["impact_kinds"])
        self.assertEqual(conflict["resolution"], "review_required_before_commit")
        self.assertTrue(result["impact_plan"]["stale_proposals"])

    def test_duplicate_input_revision_is_noop_and_priority_is_not_duplicated(self):
        first = make_input(
            input_id="IN-CC-DUP-1", stable_source_id="issue:duplicate",
            source_locator="https://github.com/Loofy147/Context-swarm/issues/9002",
            priority={"level": "high", "rationale": "Explicitly declared high priority."},
        )
        duplicate = dict(first)
        duplicate["input_id"] = "IN-CC-DUP-2"
        result = plan_context_cycle(
            cycle_id="context-cycle-duplicate-0001", base_commit=self.base,
            registry_snapshot=self.registry, dependency_map=self.dependency_map,
            input_items=[first, duplicate], source_observations=[],
        )
        self.assert_schema_valid(result)
        self.assertEqual(result["summary"]["input_duplicate_noops"], 1)
        self.assertEqual(result["summary"]["input_records_proposed"], 1)
        self.assertEqual(result["summary"]["priority_proposals"], 1)
        self.assertEqual(result["priority_summary"]["proposed_work_items"][0]["priority_level"], "high")

    def test_stale_dependency_map_blocks_direct_impact_and_retains_possible_impact(self):
        stale_map = copy.deepcopy(self.dependency_map)
        stale_map["reviewed_base_commit"] = "older-baseline"
        result = plan_context_cycle(
            cycle_id="context-cycle-stale-map-0001", base_commit=self.base,
            registry_snapshot=self.registry, dependency_map=stale_map,
            input_items=[make_input()], source_observations=[changed_source()],
        )
        self.assert_schema_valid(result)
        self.assertEqual(result["plan_status"], "blocked")
        self.assertEqual(result["impact_plan"]["plan_status"], "blocked")
        self.assertFalse(any(item["target_type"] == "artifact"
                             for item in result["impact_plan"]["direct_impacts"]))
        self.assertTrue(result["impact_plan"]["possible_impacts"])
        self.assertTrue(result["blockers"])

    def test_batch_baseline_mismatch_fails_closed(self):
        from scs.cycle import plan_batch
        batch = plan_batch(
            cycle_id="context-cycle-mismatch-0001", base_commit=self.base,
            registry_snapshot=self.registry, input_items=[make_input()],
        )
        with self.assertRaises(ContextCyclePlanningError):
            compose_context_cycle_plan(
                cycle_id=batch["cycle_id"], base_commit="differentbase",
                registry_snapshot=self.registry, dependency_map=self.dependency_map,
                batch_plan=batch, source_observations=[],
            )


if __name__ == "__main__":
    unittest.main()
