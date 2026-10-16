import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker
from scs.cycle import CyclePlanningError, plan_batch, plan_cycle


def load_registry():
    snapshot = json.loads((ROOT / "tests/fixtures/registry-cycle-base.json").read_text())
    return snapshot["registry"]


def make_input(**overrides):
    data = {
        "input_id": "IN-TEST-900",
        "observed_at": "2026-10-16",
        "captured_by": "test-harness",
        "access_boundary": "test-fixture-only",
        "trust_status": "unreviewed",
        "classification": "test_task_request",
        "normalized_claims": [],
        "evidence_refs": [],
        "privacy_note": "Synthetic test fixture.",
        "source_kind": "issue_or_pull_request",
        "stable_source_id": "issue:900",
        "source_revision": "rev:1",
        "source_locator": "https://github.com/Loofy147/Context-swarm/issues/900",
        "accessible": True,
        "actionable": True,
        "title": "Update repository intake fixtures",
        "target_context_ids": ["ctx-scs-intake"],
        "acceptance_criteria": ["New intake fixture is replayable in CI."],
        "priority": {"level": "medium", "rationale": "Test bounded task intake."},
    }
    data.update(overrides)
    return data


class SwarmCycleTests(unittest.TestCase):
    BASE = "86244139e81ac4e3f096ec28e3ad972cfa5368c1"

    def plan(self, item, **kwargs):
        return plan_cycle(cycle_id="cycle-test-001", base_commit=self.BASE,
                          registry_snapshot=load_registry(), input_item=item, **kwargs)

    def test_actionable_input_produces_uncommitted_schema_valid_task_proposal(self):
        item = make_input()
        plan = self.plan(item)
        self.assertEqual(plan["plan_status"], "proposed")
        self.assertFalse(plan["committed"])
        self.assertEqual(plan["external_actions"], [])
        proposal = plan["proposals"][0]
        self.assertEqual(proposal["proposal_type"], "create_work_item")
        task = proposal["work_item"]
        self.assertEqual(task["status"], "triaged")
        self.assertEqual(task["version"], 1)
        self.assertIn(item["source_locator"], task["source_refs"])
        schema = json.loads((ROOT / "schemas/work-item.schema.json").read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(task))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

    def test_cycle_plan_output_schema_validates_proposed_and_blocked_plans(self):
        schema = json.loads((ROOT / "schemas/cycle-plan.schema.json").read_text())
        proposed = self.plan(make_input())
        blocked = self.plan(make_input(accessible=False))
        for plan in (proposed, blocked):
            errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(plan))
            self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

    def test_every_nonduplicate_input_has_a_schema_valid_capture_proposal(self):
        item = make_input()
        plan = self.plan(item)
        capture = plan["input_record_proposal"]
        self.assertEqual(capture["proposal_type"], "capture_input")
        self.assertEqual(capture["status"], "proposed_not_committed")
        record = capture["input_record"]
        schema = json.loads((ROOT / "schemas/input-record.schema.json").read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])
        self.assertIn(plan["proposals"][0]["work_item"]["work_item_id"], record["linked_work_item_ids"])

    def test_inaccessible_input_is_captured_as_blocked_without_claiming_source_content(self):
        item = make_input(accessible=False, normalized_claims=[])
        plan = self.plan(item)
        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["input_record_proposal"]["input_record"]["intake_status"], "blocked")
        self.assertEqual(plan["input_record_proposal"]["input_record"]["normalized_claims"], [])
        self.assertEqual(plan["proposals"], [])

    def test_batch_consumes_inputs_and_deduplicates_within_batch(self):
        first = make_input(input_id="IN-BATCH-1", stable_source_id="issue:901",
                           source_locator="https://github.com/Loofy147/Context-swarm/issues/901")
        duplicate = dict(first)
        duplicate["input_id"] = "IN-BATCH-2"
        batch = plan_batch(
            cycle_id="cycle-batch-001",
            base_commit=self.BASE,
            registry_snapshot=load_registry(),
            input_items=[first, duplicate],
        )
        self.assertFalse(batch["committed"])
        self.assertEqual(batch["input_count"], 2)
        self.assertEqual(batch["summary"]["input_records_proposed"], 1)
        self.assertEqual(batch["summary"]["duplicate_noop"], 1)
        self.assertEqual(batch["summary"]["state_change_proposals"], 1)
        self.assertEqual(batch["plans"][1]["plan_status"], "duplicate_noop")
        schema = json.loads((ROOT / "schemas/batch-cycle-plan.schema.json").read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(batch))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

    def test_input_record_id_collision_does_not_overwrite_existing_record(self):
        prior = [{"input_id":"IN-TEST-900","source_kind":"other-source","source_locator":"source:old",
                  "source_revision":"rev:old","stable_source_id":"old:source"}]
        plan = self.plan(make_input(), prior_input_records=prior)
        self.assertEqual(plan["plan_status"], "conflicted")
        self.assertIsNone(plan["input_record_proposal"])
        self.assertTrue(plan["blockers"])

    def test_actionable_input_without_acceptance_criteria_needs_information(self):
        plan = self.plan(make_input(acceptance_criteria=[]))
        self.assertEqual(plan["plan_status"], "needs_information")
        self.assertIn("acceptance_criteria", " ".join(plan["blockers"]))

    def test_prior_input_records_are_used_for_deduplication(self):
        item = make_input()
        item.pop("stable_source_id")
        prior = [{"source_kind": "issue_or_pull_request", "stable_source_id": "issue:900",
                  "source_revision": "rev:1", "source_locator": item["source_locator"]}]
        plan = self.plan(item, prior_input_records=prior)
        self.assertEqual(plan["plan_status"], "duplicate_noop")
        self.assertEqual(plan["proposals"], [])

    def test_duplicate_revision_does_not_propose_second_task(self):
        plan = self.plan(make_input(), seen_revisions={"issue_or_pull_request::issue:900::rev:1"})
        self.assertEqual(plan["plan_status"], "duplicate_noop")
        self.assertEqual(plan["proposals"], [])

    def test_inaccessible_source_is_blocked_not_inferred(self):
        plan = self.plan(make_input(accessible=False))
        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["proposals"], [])
        self.assertEqual(plan["external_actions"], [])

    def test_unauthorized_consequential_action_is_blocked(self):
        plan = self.plan(make_input(consequence_class="C", separate_authorization_present=False))
        self.assertEqual(plan["plan_status"], "blocked")
        self.assertIn("authorization", " ".join(plan["blockers"]).lower())
        self.assertEqual(plan["external_actions"], [])

    def test_conflict_creates_only_a_proposal_and_preserves_conflict_refs(self):
        item = make_input(actionable=False, contains_conflicting_claim=True,
                          conflict_refs=["claim:one", "claim:two"],
                          source_kind="repository_file", stable_source_id="file:architecture",
                          source_revision="blob:abc")
        registry = load_registry()
        ctx = next(c for c in registry["contexts"] if c["context_id"] == "ctx-scs-repository-demo")
        plan = plan_cycle(
            cycle_id="cycle-test-conflict", base_commit=self.BASE,
            registry_snapshot=registry, input_item=item, operation="update_context",
            context_update={
                "context_id": ctx["context_id"], "expected_version": ctx["version"],
                "patch": {"open_questions_append": ["Reconcile contradictory architecture claims."]},
                "evidence_refs": ["test:evidence:1"], "conflict_refs": ["claim:one", "claim:two"],
                "reason": "Material claims conflict and must remain visible.",
            })
        self.assertEqual(plan["plan_status"], "proposed")
        p = plan["proposals"][0]
        self.assertEqual(p["proposed_status"], "conflicted")
        self.assertEqual(p["result_version"], ctx["version"] + 1)
        self.assertEqual(p["conflict_refs"], ["claim:one", "claim:two"])
        self.assertFalse(plan["committed"])

    def test_verified_low_risk_change_remains_a_review_proposal(self):
        item = make_input(actionable=False, verification_passed=True, consequence_class="A",
                          stable_source_id="test:result:2", source_revision="success")
        registry = load_registry()
        ctx = next(c for c in registry["contexts"] if c["context_id"] == "ctx-scs-repository-demo")
        plan = plan_cycle(
            cycle_id="cycle-test-update", base_commit=self.BASE, registry_snapshot=registry,
            input_item=item, operation="update_context",
            context_update={
                "context_id": ctx["context_id"], "expected_version": ctx["version"],
                "patch": {"claims_append": [{"claim_id": "claim:new", "text": "A reference test passed."}]},
                "evidence_refs": ["https://github.com/Loofy147/Context-swarm/actions/runs/38956067934"],
                "reason": "Record a verified test result as a proposal.",
            })
        self.assertEqual(plan["plan_status"], "proposed")
        claim = plan["proposals"][0]["patch"]["claims_append"][0]
        self.assertEqual(claim["status"], "proposed")
        self.assertEqual(plan["proposals"][0]["proposed_status"], "review")

    def test_existing_task_transition_requires_target_and_base_version(self):
        registry = load_registry()
        task = next(t for t in registry["work_items"] if t["work_item_id"] == "SCS-MATURE-008")
        item = make_input(actionable=False, target_work_item_id=task["work_item_id"],
                          stable_source_id="test:work-result", source_revision="rev:1")
        plan = plan_cycle(
            cycle_id="cycle-test-task", base_commit=self.BASE, registry_snapshot=registry,
            input_item=item, operation="advance_task",
            task_transition={"work_item_id": task["work_item_id"], "target_status": "in_progress",
                             "expected_version": task["version"],
                             "reason": "Begin the bounded cycle planner implementation.",
                             "evidence_refs": ["cycle:test:work-start"]})
        self.assertEqual(plan["plan_status"], "proposed")
        proposed = plan["proposals"][0]["work_item"]
        self.assertEqual(proposed["status"], "in_progress")
        self.assertEqual(proposed["version"], task["version"] + 1)

    def test_stale_task_transition_is_blocked(self):
        registry = load_registry()
        task = next(t for t in registry["work_items"] if t["work_item_id"] == "SCS-MATURE-008")
        item = make_input(actionable=False, target_work_item_id=task["work_item_id"])
        plan = plan_cycle(
            cycle_id="cycle-test-stale", base_commit=self.BASE, registry_snapshot=registry,
            input_item=item, operation="advance_task",
            task_transition={"work_item_id": task["work_item_id"], "target_status": "in_progress",
                             "expected_version": task["version"] - 1})
        self.assertEqual(plan["plan_status"], "blocked")
        self.assertTrue(plan["blockers"])

    def test_registry_with_dangling_relationship_fails_closed(self):
        registry = load_registry()
        registry["contexts"][0]["relationships"].append(
            {"type": "references", "target_context_id": "ctx-does-not-exist"})
        with self.assertRaises(CyclePlanningError):
            plan_cycle(cycle_id="cycle-broken-registry", base_commit=self.BASE,
                       registry_snapshot=registry, input_item=make_input())


if __name__ == "__main__":
    unittest.main()
