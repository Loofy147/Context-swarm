import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker
from scs.adapters.github import (
    normalize_github_commit,
    normalize_github_issue,
    normalize_github_issue_page,
    normalize_github_repository,
    normalize_github_source_error,
    normalize_github_workflow_run,
)
from scs.cycle import plan_batch


def load_fixture():
    return json.loads((ROOT / "tests/fixtures/github-observations.json").read_text())


def validate_envelope(envelope):
    schema = json.loads((ROOT / "schemas/intake-envelope.schema.json").read_text())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(envelope))
    return [f"{'/'.join(str(e) for e in error.absolute_path)}: {error.message}" for error in errors]


class GitHubAdapterTests(unittest.TestCase):
    BASE = "6ed1c964a55e011ec23e3df54059db20d12b9e44"
    REPO = "Loofy147/Context-swarm"
    OBSERVED = "2026-10-16"

    def test_repository_metadata_adapter_preserves_exact_identity_and_revision(self):
        fixture = load_fixture()
        envelope = normalize_github_repository(
            fixture["repository"], repo_full_name=self.REPO,
            branch_head_sha=fixture["branch_head_sha"], observed_at=self.OBSERVED,
        )
        self.assertEqual(envelope["stable_source_id"], f"repo:{self.REPO}")
        self.assertEqual(envelope["source_kind"], "commit_or_branch")
        self.assertTrue(envelope["source_revision"].startswith("meta:"))
        self.assertIn(fixture["branch_head_sha"], " ".join(c["text"] for c in envelope["normalized_claims"]))
        self.assertEqual(validate_envelope(envelope), [])

    def test_commit_adapter_uses_sha_as_identity_and_revision(self):
        fixture = load_fixture()
        envelope = normalize_github_commit(fixture["latest_commit"], repo_full_name=self.REPO, observed_at=self.OBSERVED)
        self.assertEqual(envelope["stable_source_id"], f"commit:{fixture['latest_commit']['sha']}")
        self.assertEqual(envelope["source_revision"], fixture["latest_commit"]["sha"])
        self.assertIn("Reconcile registry", envelope["normalized_claims"][0]["text"])
        self.assertEqual(validate_envelope(envelope), [])

    def test_open_issue_extracts_only_explicit_acceptance_criteria(self):
        fixture = load_fixture()
        envelope = normalize_github_issue(fixture["synthetic_issue"], repo_full_name=self.REPO, observed_at=self.OBSERVED)
        self.assertTrue(envelope["actionable"])
        self.assertEqual(envelope["priority"]["level"], "high")
        self.assertEqual(envelope["acceptance_criteria"], [
            "Source identity and revision are preserved.",
            "Unavailable sources create blocked records.",
        ])
        self.assertNotIn("This text is fixture data only.", " ".join(c["text"] for c in envelope["normalized_claims"]))
        self.assertEqual(validate_envelope(envelope), [])

    def test_empty_issue_page_is_scoped_observation_not_global_absence_claim(self):
        fixture = load_fixture()
        envelopes = normalize_github_issue_page(
            fixture["issues"], repo_full_name=self.REPO,
            query=fixture["issues_query"], observed_at=self.OBSERVED,
        )
        self.assertEqual(len(envelopes), 1)
        self.assertFalse(envelopes[0]["actionable"])
        text_claims = " ".join(c["text"] for c in envelopes[0]["normalized_claims"])
        self.assertIn("zero entries", text_claims)
        self.assertIn("does not establish", text_claims)
        self.assertEqual(validate_envelope(envelopes[0]), [])

    def test_completed_successful_workflow_is_a_verified_source_observation(self):
        fixture = load_fixture()
        envelope = normalize_github_workflow_run(fixture["workflow_run"], repo_full_name=self.REPO, observed_at=self.OBSERVED)
        self.assertTrue(envelope["verification_passed"])
        self.assertEqual(envelope["source_kind"], "test_or_workflow_result")
        self.assertEqual(envelope["head_sha"], self.BASE)
        self.assertEqual(envelope["normalized_claims"][0]["status"], "verified")
        self.assertEqual(validate_envelope(envelope), [])

    def test_failed_source_is_blocked_with_no_fabricated_claims(self):
        envelope = normalize_github_source_error(
            repo_full_name=self.REPO,
            source_kind="commit_or_branch",
            stable_source_id="repo:Loofy147/Context-swarm",
            source_locator="https://api.github.com/repos/Loofy147/Context-swarm/branches/main",
            observed_at=self.OBSERVED,
            error_summary="Permission denied",
        )
        self.assertFalse(envelope["accessible"])
        self.assertEqual(envelope["normalized_claims"], [])
        self.assertEqual(validate_envelope(envelope), [])

    def test_live_shaped_observations_flow_through_batch_planner(self):
        fixture = load_fixture()
        registry = json.loads((ROOT / "swarm/registry.json").read_text())
        prior = [json.loads((ROOT / "swarm/inputs/IN-SCS-0001-operating-phase.json").read_text())]
        repo_input = normalize_github_repository(
            fixture["repository"], repo_full_name=self.REPO,
            branch_head_sha=fixture["branch_head_sha"], observed_at=self.OBSERVED,
        )
        commit_input = normalize_github_commit(fixture["latest_commit"], repo_full_name=self.REPO, observed_at=self.OBSERVED)
        issue_page_inputs = normalize_github_issue_page(
            fixture["issues"], repo_full_name=self.REPO,
            query=fixture["issues_query"], observed_at=self.OBSERVED,
        )
        workflow_input = normalize_github_workflow_run(
            fixture["workflow_run"], repo_full_name=self.REPO, observed_at=self.OBSERVED,
        )
        context = next(c for c in registry["contexts"] if c["context_id"] == "ctx-scs-repository-demo")
        source_claim = workflow_input["normalized_claims"][0]
        options = {
            workflow_input["input_id"]: {
                "operation": "update_context",
                "context_update": {
                    "context_id": context["context_id"],
                    "expected_version": context["version"],
                    "patch": {"claims_append": [{
                        "claim_id": source_claim["claim_id"],
                        "text": source_claim["text"],
                        "status": source_claim["status"],
                        "evidence_refs": [workflow_input["source_locator"]],
                    }]},
                    "evidence_refs": [workflow_input["source_locator"]],
                    "reason": "Record the verified workflow result as a proposed context claim.",
                },
            }
        }
        batch = plan_batch(
            cycle_id="cycle-github-adapter-test",
            base_commit=self.BASE,
            registry_snapshot=registry,
            input_items=[repo_input, commit_input, *issue_page_inputs, workflow_input],
            prior_input_records=prior,
            options_by_input_id=options,
        )
        self.assertFalse(batch["committed"])
        self.assertEqual(batch["input_count"], 4)
        self.assertEqual(batch["summary"]["input_records_proposed"], 4)
        self.assertEqual(batch["summary"]["state_change_proposals"], 1)
        workflow_plan = next(p for p in batch["plans"] if p["input_ref"]["input_id"] == workflow_input["input_id"])
        self.assertEqual(workflow_plan["plan_status"], "proposed")
        self.assertEqual(workflow_plan["proposals"][0]["proposed_status"], "review")
        self.assertTrue(all(plan["external_actions"] == [] for plan in batch["plans"]))


if __name__ == "__main__":
    unittest.main()
