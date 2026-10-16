import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker
from scs.runner import plan_github_observation_batch


def load_fixture():
    return json.loads((ROOT / "tests/fixtures/github-observations.json").read_text())


def load_registry():
    return json.loads((ROOT / "swarm/registry.json").read_text())


def load_prior_inputs():
    return [json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())]


class GitHubSnapshotRunnerTests(unittest.TestCase):
    BASE = "6ed1c964a55e011ec23e3df54059db20d12b9e44"
    REPO = "Loofy147/Context-swarm"

    def run_snapshot(self, snapshot):
        return plan_github_observation_batch(
            cycle_id="cycle-live-shaped-github-0001",
            base_commit=self.BASE,
            repo_full_name=self.REPO,
            observed_at="2026-10-16",
            source_snapshot=snapshot,
            registry_snapshot=load_registry(),
            prior_input_records=load_prior_inputs(),
        )

    def test_snapshot_runs_through_adapters_batch_planner_and_output_schema(self):
        fixture = load_fixture()
        snapshot = {
            "repository": fixture["repository"],
            "branch_head_sha": fixture["branch_head_sha"],
            "latest_commit": fixture["latest_commit"],
            "issues": fixture["issues"],
            "issues_query": fixture["issues_query"],
            "workflow_run": fixture["workflow_run"],
        }
        batch = self.run_snapshot(snapshot)
        self.assertFalse(batch["committed"])
        self.assertEqual(batch["input_count"], 4)
        self.assertEqual(batch["summary"]["input_records_proposed"], 4)
        self.assertEqual(batch["summary"]["state_change_proposals"], 1)
        self.assertEqual(batch["summary"]["proposed"], 1)
        schema = json.loads((ROOT / "schemas/batch-cycle-plan.schema.json").read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(batch))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])

        context_update_plan = next(p for p in batch["plans"] if p["operation"] == "update_context")
        self.assertEqual(context_update_plan["plan_status"], "proposed")
        proposal = context_update_plan["proposals"][0]
        self.assertEqual(proposal["proposed_status"], "review")
        claim = proposal["patch"]["claims_append"][0]
        self.assertEqual(claim["status"], "proposed")
        self.assertTrue(claim["evidence_refs"])
        self.assertTrue(all(p["external_actions"] == [] for p in batch["plans"]))

        empty_issue_plan = next(
            p for p in batch["plans"]
            if p["input_ref"]["source_kind"] == "issue_or_pull_request"
        )
        self.assertIn("zero entries", " ".join(
            c["text"] for c in empty_issue_plan["input_record_proposal"]["input_record"]["normalized_claims"]
        ))

    def test_missing_issue_page_becomes_blocked_record_not_empty_observation(self):
        fixture = load_fixture()
        snapshot = {
            "repository": fixture["repository"],
            "branch_head_sha": fixture["branch_head_sha"],
            "latest_commit": fixture["latest_commit"],
            "workflow_run": fixture["workflow_run"],
            "issues_query": fixture["issues_query"],
        }
        batch = self.run_snapshot(snapshot)
        issue_plan = next(
            p for p in batch["plans"]
            if p["input_ref"]["source_kind"] == "issue_or_pull_request"
        )
        self.assertEqual(issue_plan["plan_status"], "blocked")
        record = issue_plan["input_record_proposal"]["input_record"]
        self.assertEqual(record["intake_status"], "blocked")
        self.assertEqual(record["normalized_claims"], [])
        self.assertIn("not accessible", issue_plan["blockers"][0].lower())

    def test_unavailable_workflow_run_does_not_create_context_update(self):
        fixture = load_fixture()
        snapshot = {
            "repository": fixture["repository"],
            "branch_head_sha": fixture["branch_head_sha"],
            "latest_commit": fixture["latest_commit"],
            "issues": fixture["issues"],
            "issues_query": fixture["issues_query"],
        }
        batch = self.run_snapshot(snapshot)
        workflow_plan = next(
            p for p in batch["plans"]
            if p["input_ref"]["source_kind"] == "test_or_workflow_result"
        )
        self.assertEqual(workflow_plan["plan_status"], "blocked")
        self.assertEqual(workflow_plan["proposals"], [])
        self.assertEqual(workflow_plan["input_record_proposal"]["input_record"]["normalized_claims"], [])

    def test_captured_source_snapshot_runs_idempotently(self):
        snapshot_record = json.loads((ROOT / "swarm/sources/github-snapshot-cycle-0006.json").read_text())
        registry_record = json.loads((ROOT / "tests/fixtures/registry-source-cycle-0006.json").read_text())
        self.assertEqual(snapshot_record["base_commit"], registry_record["source_commit"])
        self.assertEqual(snapshot_record["base_registry_version"], registry_record["registry"]["registry_version"])
        self.assertEqual(snapshot_record["source_snapshot"]["branch_head_sha"], snapshot_record["base_commit"])

        snapshot_schema = json.loads((ROOT / "schemas/github-source-snapshot.schema.json").read_text())
        snapshot_errors = list(Draft202012Validator(snapshot_schema, format_checker=FormatChecker()).iter_errors(snapshot_record))
        self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in snapshot_errors])

        prior_records = [json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())]
        kwargs = {
            "base_commit": snapshot_record["base_commit"],
            "repo_full_name": snapshot_record["repo_full_name"],
            "observed_at": snapshot_record["captured_at"][:10],
            "source_snapshot": snapshot_record["source_snapshot"],
            "registry_snapshot": registry_record["registry"],
            "prior_input_records": prior_records,
        }
        batch = plan_github_observation_batch(cycle_id="SCS-CYCLE-0006-live-snapshot", **kwargs)
        self.assertFalse(batch["committed"])
        self.assertEqual(batch["input_count"], 4)
        self.assertEqual(batch["summary"]["input_records_proposed"], 4)
        self.assertEqual(batch["summary"]["state_change_proposals"], 1)
        self.assertEqual(batch["summary"]["proposed"], 1)

        input_schema = json.loads((ROOT / "schemas/input-record.schema.json").read_text())
        new_records = []
        for plan in batch["plans"]:
            proposal = plan["input_record_proposal"]
            self.assertIsNotNone(proposal)
            record = proposal["input_record"]
            errors = list(Draft202012Validator(input_schema, format_checker=FormatChecker()).iter_errors(record))
            self.assertEqual([], [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors])
            new_records.append(record)

        issue_record = next(r for r in new_records if r["source_kind"] == "issue_or_pull_request")
        self.assertIn("zero entries", " ".join(c["text"] for c in issue_record["normalized_claims"]))
        workflow_plan = next(p for p in batch["plans"] if p["input_ref"]["source_kind"] == "test_or_workflow_result")
        self.assertEqual(workflow_plan["plan_status"], "proposed")
        self.assertEqual(workflow_plan["proposals"][0]["proposed_status"], "review")
        self.assertTrue(all(p["external_actions"] == [] for p in batch["plans"]))

        persisted_paths = sorted((ROOT / "swarm/inputs").glob("IN-GH-*.json"))
        self.assertEqual(len(persisted_paths), 4)
        persisted_records = [json.loads(path.read_text()) for path in persisted_paths]
        persisted_by_id = {record["input_id"]: record for record in persisted_records}
        self.assertEqual(set(persisted_by_id), {record["input_id"] for record in new_records})
        for generated in new_records:
            self.assertEqual(persisted_by_id[generated["input_id"]], generated)

        replay = plan_github_observation_batch(cycle_id="SCS-CYCLE-0006-replay", **{
            **kwargs, "prior_input_records": prior_records + persisted_records
        })
        self.assertEqual(replay["summary"]["input_records_proposed"], 0)
        self.assertEqual(replay["summary"]["duplicate_noop"], 4)
        self.assertEqual(replay["summary"]["state_change_proposals"], 0)


if __name__ == "__main__":
    unittest.main()
