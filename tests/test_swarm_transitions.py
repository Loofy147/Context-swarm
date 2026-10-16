import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scs.transitions import (
    InvalidTransition,
    StaleStateVersion,
    TransitionPreconditionError,
    plan_transition,
)


class SwarmTransitionTests(unittest.TestCase):
    def test_transition_is_a_proposal_and_increments_version(self):
        plan = plan_transition(
            "task", "captured", "triaged",
            current_version=1, expected_version=1,
        )
        self.assertEqual(plan["plan_status"], "proposed_not_committed")
        self.assertEqual(plan["base_version"], 1)
        self.assertEqual(plan["result_version"], 2)

    def test_stale_version_is_rejected(self):
        with self.assertRaises(StaleStateVersion):
            plan_transition(
                "task", "captured", "triaged",
                current_version=2, expected_version=1,
            )

    def test_illegal_task_transition_is_rejected(self):
        with self.assertRaises(InvalidTransition):
            plan_transition(
                "task", "ready", "accepted",
                current_version=1, expected_version=1,
                acceptance_verified=True, evidence_refs=["test:1"],
            )

    def test_task_cannot_be_accepted_without_verified_evidence(self):
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "task", "review", "accepted",
                current_version=1, expected_version=1,
                evidence_refs=["test:1"], acceptance_verified=False,
            )
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "task", "review", "accepted",
                current_version=1, expected_version=1,
                acceptance_verified=True, evidence_refs=[],
            )

    def test_task_acceptance_passes_with_verified_criteria_and_evidence(self):
        plan = plan_transition(
            "task", "review", "accepted",
            current_version=3, expected_version=3,
            evidence_refs=["ci:run-7"], acceptance_verified=True,
        )
        self.assertEqual(plan["result_version"], 4)
        self.assertEqual(plan["to_status"], "accepted")

    def test_blocked_state_requires_reason(self):
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "context", "active", "blocked",
                current_version=1, expected_version=1,
            )

    def test_conflict_requires_conflict_reference(self):
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "context", "active", "conflicted",
                current_version=1, expected_version=1,
            )
        plan = plan_transition(
            "context", "active", "conflicted",
            current_version=1, expected_version=1,
            conflict_refs=["claim:A", "claim:B"], reason="Claims are incompatible",
        )
        self.assertEqual(plan["to_status"], "conflicted")

    def test_context_acceptance_requires_evidence_dependencies_and_policy(self):
        common = dict(
            entity_kind="context", current_status="review", target_status="accepted"
        )
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "context", "review", "accepted",
                current_version=2, expected_version=2,
                evidence_refs=["test:pass"], acceptance_verified=True,
                dependencies_current=False, policy_compliant=True,
            )
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "context", "review", "accepted",
                current_version=2, expected_version=2,
                evidence_refs=["test:pass"], acceptance_verified=True,
                dependencies_current=True, policy_compliant=None,
            )
        plan = plan_transition(
            "context", "review", "accepted",
            current_version=2, expected_version=2,
            evidence_refs=["test:pass"], acceptance_verified=True,
            dependencies_current=True, policy_compliant=True,
        )
        self.assertEqual(plan["result_version"], 3)

    def test_stale_context_cannot_reactivate_without_current_dependencies(self):
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "context", "stale", "active",
                current_version=4, expected_version=4,
                dependencies_current=False, evidence_refs=["dep-check:failed"],
            )
        plan = plan_transition(
            "context", "stale", "active",
            current_version=4, expected_version=4,
            dependencies_current=True, resolution_ref="dep-check:pass",
        )
        self.assertEqual(plan["to_status"], "active")

    def test_superseded_state_requires_replacement_reference(self):
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "context", "accepted", "superseded",
                current_version=2, expected_version=2,
            )
        plan = plan_transition(
            "context", "accepted", "superseded",
            current_version=2, expected_version=2,
            replacement_ref="ctx:replacement:v1",
        )
        self.assertEqual(plan["result_version"], 3)

    def test_ready_task_requires_source_and_acceptance_criteria(self):
        with self.assertRaises(TransitionPreconditionError):
            plan_transition(
                "task", "triaged", "ready",
                current_version=1, expected_version=1,
                acceptance_criteria_present=True, source_refs_present=False,
            )


if __name__ == "__main__":
    unittest.main()
