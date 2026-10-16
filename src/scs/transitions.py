"""Pure reference rules for versioned context/work-item transitions.

This module proposes a transition; it does not persist state, fetch sources,
authenticate a principal, or perform external side effects.
"""
from __future__ import annotations

from typing import Iterable


class InvalidTransition(ValueError):
    """The state machine does not permit the requested transition."""


class TransitionPreconditionError(ValueError):
    """The transition is allowed in principle but required evidence is missing."""


class StaleStateVersion(ValueError):
    """The proposal was built against a stale state version."""


TASK_TRANSITIONS = {
    "captured": {"triaged", "rejected"},
    "triaged": {"ready", "needs_information", "blocked", "conflicted", "rejected"},
    "ready": {"in_progress", "blocked", "rejected"},
    "in_progress": {"needs_information", "blocked", "conflicted", "review"},
    "needs_information": {"triaged", "blocked", "rejected"},
    "blocked": {"ready", "conflicted", "rejected"},
    "conflicted": {"triaged", "blocked", "review"},
    "review": {"accepted", "ready", "blocked", "conflicted"},
    "accepted": {"superseded"},
    "superseded": set(),
    "rejected": set(),
}

CONTEXT_TRANSITIONS = {
    "draft": {"active", "blocked", "deferred", "archived"},
    "active": {"review", "blocked", "conflicted", "stale", "archived", "superseded"},
    "blocked": {"active", "conflicted", "archived"},
    "conflicted": {"review", "blocked", "archived"},
    "review": {"accepted", "active", "blocked", "conflicted"},
    "accepted": {"stale", "superseded", "archived"},
    "stale": {"active", "review", "blocked", "conflicted"},
    "superseded": set(),
    "archived": set(),
    "deferred": {"draft", "active", "archived"},
}

_REASON_REQUIRED = {"blocked", "needs_information", "rejected", "archived", "deferred"}


def _nonempty(values: Iterable[str] | None) -> list[str]:
    return [v for v in (values or []) if isinstance(v, str) and v.strip()]


def plan_transition(
    entity_kind: str,
    current_status: str,
    target_status: str,
    *,
    current_version: int,
    expected_version: int,
    evidence_refs: Iterable[str] | None = None,
    conflict_refs: Iterable[str] | None = None,
    reason: str | None = None,
    acceptance_verified: bool = False,
    acceptance_criteria_present: bool = False,
    source_refs_present: bool = False,
    dependencies_current: bool | None = None,
    policy_compliant: bool | None = None,
    resolution_ref: str | None = None,
    replacement_ref: str | None = None,
) -> dict:
    """Validate a transition and return a proposal with a monotonic next version.

    The caller must still verify current authorization, persist the new state,
    and record the change/evidence. A returned plan is not an accepted commit.
    """
    if entity_kind == "task":
        transition_table = TASK_TRANSITIONS
    elif entity_kind == "context":
        transition_table = CONTEXT_TRANSITIONS
    else:
        raise InvalidTransition(f"unknown entity kind: {entity_kind}")

    if current_version < 1 or expected_version < 1:
        raise StaleStateVersion("versions must be positive integers")
    if expected_version != current_version:
        raise StaleStateVersion(
            f"expected version {expected_version}, current version is {current_version}"
        )
    allowed = transition_table.get(current_status)
    if allowed is None or target_status not in allowed:
        raise InvalidTransition(f"{entity_kind}: {current_status} -> {target_status} is not allowed")

    evidence = _nonempty(evidence_refs)
    conflicts = _nonempty(conflict_refs)

    if target_status in _REASON_REQUIRED and not (reason and reason.strip()):
        raise TransitionPreconditionError(f"reason is required for status {target_status}")
    if target_status == "conflicted" and not conflicts:
        raise TransitionPreconditionError("conflicted state requires conflict_refs")
    if target_status == "superseded" and not (replacement_ref and replacement_ref.strip()):
        raise TransitionPreconditionError("superseded state requires replacement_ref")

    if entity_kind == "task" and target_status == "ready":
        if not acceptance_criteria_present or not source_refs_present:
            raise TransitionPreconditionError(
                "ready task requires acceptance criteria and source references"
            )

    if target_status == "accepted":
        if not acceptance_verified:
            raise TransitionPreconditionError("acceptance criteria have not been verified")
        if not evidence:
            raise TransitionPreconditionError("accepted state requires evidence_refs")
        if entity_kind == "context":
            if dependencies_current is not True:
                raise TransitionPreconditionError("context dependencies must be current")
            if policy_compliant is not True:
                raise TransitionPreconditionError("context policy compliance must be verified")

    if entity_kind == "context" and target_status == "active" and current_status == "stale":
        if dependencies_current is not True:
            raise TransitionPreconditionError("stale context cannot reactivate before dependencies are current")
        if not (resolution_ref or evidence):
            raise TransitionPreconditionError("stale context reactivation requires resolution/evidence")

    if current_status in {"blocked", "conflicted", "stale", "needs_information"} and target_status in {"active", "ready", "review", "triaged"}:
        if not (resolution_ref or evidence):
            raise TransitionPreconditionError("resolving a blocked/stale/conflicted state requires a resolution reference or evidence")

    return {
        "plan_status": "proposed_not_committed",
        "entity_kind": entity_kind,
        "from_status": current_status,
        "to_status": target_status,
        "base_version": current_version,
        "expected_version": expected_version,
        "result_version": current_version + 1,
        "evidence_refs": evidence,
        "conflict_refs": conflicts,
        "reason": reason,
        "resolution_ref": resolution_ref,
        "replacement_ref": replacement_ref,
    }
