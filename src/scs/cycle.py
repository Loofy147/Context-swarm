"""Pure planner for one bounded repository-native swarm cycle.

This joins source intake routing with task/context transition checks. It returns
proposals only: no source fetching, Git writes, persistence, authentication, or
external side effects are performed by this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable, Mapping

from scs.intake import build_seen_revision_index, route_input
from scs.transitions import (
    InvalidTransition,
    StaleStateVersion,
    TransitionPreconditionError,
    plan_transition,
)


class CyclePlanningError(ValueError):
    """The cycle snapshot or request is malformed or internally inconsistent."""


_BLOCKING_DISPOSITIONS = {"request_information", "hold_for_authorization", "duplicate_no_new_item"}
_CONTEXT_PATCH_KEYS = {
    "claims_append", "decisions_append", "open_questions_append",
    "evidence_refs_append", "scope", "change_note",
}
_WORK_ITEM_KEYS = {
    "work_item_id", "kind", "title", "status", "requested_by", "source_refs",
    "input_ids", "target_context_ids", "dependencies", "priority",
    "acceptance_criteria", "required_evidence", "attempts", "blocked_reason",
    "last_outcome", "history_refs", "consumer_run_ref",
    "expected_context_versions", "version", "description",
}


def _registry_indexes(registry: Mapping[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    if registry.get("canonical_store") != "git_tracked_repository_artifacts":
        raise CyclePlanningError("cycle requires a repository-native registry snapshot")
    if not isinstance(registry.get("registry_version"), int):
        raise CyclePlanningError("registry_version must be an integer")
    contexts = registry.get("contexts")
    work_items = registry.get("work_items")
    if not isinstance(contexts, list) or not isinstance(work_items, list):
        raise CyclePlanningError("registry must contain contexts and work_items arrays")
    context_index: dict[str, dict] = {}
    task_index: dict[str, dict] = {}
    for context in contexts:
        context_id = context.get("context_id")
        if not isinstance(context_id, str) or not context_id:
            raise CyclePlanningError("every context must have a context_id")
        if context_id in context_index:
            raise CyclePlanningError(f"duplicate context_id: {context_id}")
        context_index[context_id] = context
    for task in work_items:
        task_id = task.get("work_item_id")
        if not isinstance(task_id, str) or not task_id:
            raise CyclePlanningError("every work item must have a work_item_id")
        if task_id in task_index:
            raise CyclePlanningError(f"duplicate work_item_id: {task_id}")
        task_index[task_id] = task
    # Fail closed on broken graph references.
    for context in contexts:
        for relationship in context.get("relationships", []):
            if relationship.get("target_context_id") not in context_index:
                raise CyclePlanningError(f"context {context['context_id']} has a dangling relationship")
    for task in work_items:
        missing_contexts = set(task.get("target_context_ids", [])) - set(context_index)
        if missing_contexts:
            raise CyclePlanningError(f"work item {task['work_item_id']} targets unknown contexts: {sorted(missing_contexts)}")
        missing_tasks = set(task.get("dependencies", [])) - set(task_index)
        if missing_tasks:
            raise CyclePlanningError(f"work item {task['work_item_id']} has unknown dependencies: {sorted(missing_tasks)}")
    return context_index, task_index


def _source_ref(item: Mapping[str, Any]) -> str | None:
    locator = item.get("source_locator")
    if isinstance(locator, str) and locator.strip():
        return locator.strip()
    source_kind, source_id, revision = item.get("source_kind"), item.get("stable_source_id"), item.get("source_revision")
    if source_kind and source_id and revision not in (None, ""):
        return f"{source_kind}:{source_id}@{revision}"
    input_id = item.get("input_id")
    return f"input:{input_id}" if input_id else None


def _stable_task_id(item: Mapping[str, Any]) -> str | None:
    identity = item.get("input_id") or _source_ref(item)
    if not identity:
        return None
    canonical = json.dumps(
        {"identity": identity, "source_kind": item.get("source_kind"),
         "source_revision": item.get("source_revision")},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "SCS-TASK-" + hashlib.sha256(canonical).hexdigest()[:16].upper()


def _make_work_item_proposal(
    item: Mapping[str, Any],
    registry: Mapping[str, Any],
    context_index: Mapping[str, dict],
    task_index: Mapping[str, dict],
    draft: Mapping[str, Any] | None,
) -> dict:
    raw = dict(draft if draft is not None else item.get("work_item_draft", {}))
    candidate = {k: copy.deepcopy(v) for k, v in raw.items() if k in _WORK_ITEM_KEYS}
    blockers: list[str] = []
    title = candidate.get("title") or item.get("title")
    targets = candidate.get("target_context_ids", item.get("target_context_ids", []))
    criteria = candidate.get("acceptance_criteria", item.get("acceptance_criteria", []))
    priority = candidate.get("priority", item.get("priority"))
    if not isinstance(title, str) or not title.strip():
        blockers.append("A task title is required; the swarm must not invent the requested outcome.")
    if not isinstance(targets, list) or not targets:
        blockers.append("At least one target_context_id is required to route the task.")
    if not isinstance(criteria, list) or not criteria or not all(isinstance(x, str) and x.strip() for x in criteria):
        blockers.append("Explicit acceptance_criteria are required before a task can be ready.")
    if not isinstance(priority, dict) or priority.get("level") not in {"critical", "high", "medium", "low"} or not isinstance(priority.get("rationale"), str) or not priority.get("rationale", "").strip():
        blockers.append("Priority level and rationale are required; no hidden priority score will be inferred.")
    source_ref = _source_ref(item)
    if not source_ref:
        blockers.append("A stable source locator or input identity is required for provenance.")
    if blockers:
        return {"proposal": None, "blockers": blockers}

    work_id = candidate.get("work_item_id") or _stable_task_id(item)
    if not work_id:
        return {"proposal": None, "blockers": ["Could not derive a stable work-item identity."]}
    if work_id in task_index:
        return {"proposal": None, "blockers": [f"work_item_id already exists: {work_id}"]}
    missing_contexts = set(targets) - set(context_index)
    if missing_contexts:
        return {"proposal": None, "blockers": [f"Unknown target contexts: {sorted(missing_contexts)}"]}

    dependencies = candidate.get("dependencies", [])
    if not isinstance(dependencies, list):
        return {"proposal": None, "blockers": ["dependencies must be a list of work_item_ids."]}
    if work_id in dependencies:
        return {"proposal": None, "blockers": ["A work item cannot depend on itself."]}
    missing_dependencies = set(dependencies) - set(task_index)
    if missing_dependencies:
        return {"proposal": None, "blockers": [f"Unknown task dependencies: {sorted(missing_dependencies)}"]}

    refs = list(candidate.get("source_refs", []))
    if source_ref not in refs:
        refs.append(source_ref)
    input_id = item.get("input_id")
    input_ids = list(candidate.get("input_ids", []))
    if input_id and input_id not in input_ids:
        input_ids.append(input_id)
    work_item = candidate
    work_item.update({
        "work_item_id": work_id,
        "kind": candidate.get("kind") or item.get("work_kind") or "task",
        "title": title.strip(),
        "status": "triaged",  # Intake cannot auto-start or auto-accept a task.
        "source_refs": refs,
        "input_ids": input_ids,
        "target_context_ids": targets,
        "dependencies": dependencies,
        "priority": priority,
        "acceptance_criteria": criteria,
        "attempts": 0,
        "blocked_reason": None,
        "version": 1,
    })
    work_item.setdefault("requested_by", item.get("captured_by") or item.get("requested_by") or "intake")
    work_item.setdefault("required_evidence", [])
    return {"proposal": {
        "proposal_type": "create_work_item",
        "status": "proposed_not_committed",
        "base_registry_version": registry["registry_version"],
        "work_item": work_item,
    }, "blockers": []}


def _plan_task_transition(
    task_transition: Mapping[str, Any],
    input_item: Mapping[str, Any],
    task_index: Mapping[str, dict],
    cycle_id: str,
) -> dict:
    work_id = task_transition.get("work_item_id")
    task = task_index.get(work_id)
    if task is None:
        return {"proposal": None, "blockers": [f"Unknown work_item_id: {work_id}"]}
    if input_item.get("target_work_item_id") != work_id:
        return {"proposal": None, "blockers": ["input_item.target_work_item_id must match the explicit task-transition target."]}
    expected = task_transition.get("expected_version")
    if not isinstance(expected, int):
        return {"proposal": None, "blockers": ["expected_version is required for task transitions."]}
    evidence = list(task_transition.get("evidence_refs", []))
    try:
        transition = plan_transition(
            "task", task.get("status"), task_transition.get("target_status"),
            current_version=task.get("version"), expected_version=expected,
            evidence_refs=evidence, conflict_refs=task_transition.get("conflict_refs", []),
            reason=task_transition.get("reason"),
            acceptance_verified=task_transition.get("acceptance_verified", False),
            acceptance_criteria_present=bool(task.get("acceptance_criteria")),
            source_refs_present=bool(task.get("source_refs")),
            resolution_ref=task_transition.get("resolution_ref"),
            replacement_ref=task_transition.get("replacement_ref"),
        )
    except (InvalidTransition, StaleStateVersion, TransitionPreconditionError) as exc:
        return {"proposal": None, "blockers": [str(exc)]}

    next_task = copy.deepcopy(task)
    next_task["status"] = transition["to_status"]
    next_task["version"] = transition["result_version"]
    next_task["last_outcome"] = task_transition.get("reason") or f"Proposed transition {transition['from_status']} -> {transition['to_status']}"
    history = list(next_task.get("history_refs", []))
    for ref in [f"cycle:{cycle_id}", *evidence]:
        if ref not in history:
            history.append(ref)
    next_task["history_refs"] = history
    return {"proposal": {
        "proposal_type": "transition_work_item",
        "status": "proposed_not_committed",
        "transition": transition,
        "work_item": next_task,
    }, "blockers": []}


def _plan_context_update(
    context_update: Mapping[str, Any],
    input_item: Mapping[str, Any],
    context_index: Mapping[str, dict],
    registry_version: int,
    cycle_id: str,
    target_status: str,
) -> dict:
    context_id = context_update.get("context_id")
    context = context_index.get(context_id)
    if context is None:
        return {"proposal": None, "blockers": [f"Unknown context_id: {context_id}"]}
    expected = context_update.get("expected_version")
    if not isinstance(expected, int):
        return {"proposal": None, "blockers": ["expected_version is required for context updates."]}
    patch = context_update.get("patch")
    if not isinstance(patch, dict) or not patch:
        return {"proposal": None, "blockers": ["A non-empty patch is required for context updates."]}
    forbidden = set(patch) - _CONTEXT_PATCH_KEYS
    if forbidden:
        return {"proposal": None, "blockers": [f"Protected or unsupported patch keys: {sorted(forbidden)}"]}
    reason = context_update.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return {"proposal": None, "blockers": ["A rationale is required for a context update."]}
    conflict_refs = list(context_update.get("conflict_refs", input_item.get("conflict_refs", [])))
    if target_status == "conflicted" and not conflict_refs:
        return {"proposal": None, "blockers": ["conflict_refs are required to open a conflict."]}

    source_ref = _source_ref(input_item)
    evidence = list(context_update.get("evidence_refs", []))
    evidence.extend(input_item.get("evidence_refs", []))
    if source_ref and source_ref not in evidence:
        evidence.append(source_ref)
    evidence = list(dict.fromkeys(x for x in evidence if isinstance(x, str) and x.strip()))
    if not evidence:
        return {"proposal": None, "blockers": ["At least one evidence reference is required."]}

    safe_patch = copy.deepcopy(patch)
    if "claims_append" in safe_patch:
        if not isinstance(safe_patch["claims_append"], list):
            return {"proposal": None, "blockers": ["claims_append must be a list."]}
        for claim in safe_patch["claims_append"]:
            if not isinstance(claim, dict) or not claim.get("claim_id") or not claim.get("text"):
                return {"proposal": None, "blockers": ["Each appended claim needs claim_id and text."]}
            claim["status"] = "proposed"
            claim_refs = list(claim.get("evidence_refs", []))
            for ref in evidence:
                if ref not in claim_refs:
                    claim_refs.append(ref)
            claim["evidence_refs"] = claim_refs
    if "decisions_append" in safe_patch:
        if not isinstance(safe_patch["decisions_append"], list):
            return {"proposal": None, "blockers": ["decisions_append must be a list."]}
        for decision in safe_patch["decisions_append"]:
            if not isinstance(decision, dict) or not decision.get("decision_id") or not decision.get("statement"):
                return {"proposal": None, "blockers": ["Each appended decision needs decision_id and statement."]}
            decision["status"] = "proposed"
            decision_refs = list(decision.get("evidence_refs", []))
            for ref in evidence:
                if ref not in decision_refs:
                    decision_refs.append(ref)
            decision["evidence_refs"] = decision_refs

    try:
        transition = plan_transition(
            "context", context.get("lifecycle_status"), target_status,
            current_version=context.get("version"), expected_version=expected,
            evidence_refs=evidence, conflict_refs=conflict_refs, reason=reason,
        )
    except (InvalidTransition, StaleStateVersion, TransitionPreconditionError) as exc:
        return {"proposal": None, "blockers": [str(exc)]}

    safe_patch.setdefault("evidence_refs_append", [])
    if not isinstance(safe_patch["evidence_refs_append"], list):
        return {"proposal": None, "blockers": ["evidence_refs_append must be a list."]}
    for ref in evidence:
        if ref not in safe_patch["evidence_refs_append"]:
            safe_patch["evidence_refs_append"].append(ref)
    return {"proposal": {
        "proposal_type": "update_context",
        "status": "proposed_not_committed",
        "base_registry_version": registry_version,
        "context_id": context_id,
        "base_version": context["version"],
        "result_version": transition["result_version"],
        "from_status": context["lifecycle_status"],
        "proposed_status": target_status,
        "patch": safe_patch,
        "evidence_refs": evidence,
        "conflict_refs": conflict_refs,
        "reason": reason,
        "transition_validation": transition,
        "cycle_id": cycle_id,
    }, "blockers": []}


def plan_cycle(
    *,
    cycle_id: str,
    base_commit: str,
    registry_snapshot: Mapping[str, Any],
    input_item: Mapping[str, Any],
    seen_revisions: Iterable[str] = (),
    prior_input_records: Iterable[Mapping[str, Any]] = (),
    operation: str = "intake",
    proposed_work_item: Mapping[str, Any] | None = None,
    task_transition: Mapping[str, Any] | None = None,
    context_update: Mapping[str, Any] | None = None,
) -> dict:
    """Plan one cycle without committing it.

    - intake: route input and optionally propose a new work item or context update.
    - advance_task: propose a transition for one existing task.
    - update_context: propose a verified reversible update or conflict state.
    """
    if not isinstance(cycle_id, str) or not cycle_id.strip():
        raise CyclePlanningError("cycle_id is required")
    if not isinstance(base_commit, str) or len(base_commit) < 7:
        raise CyclePlanningError("base_commit must identify the repository snapshot")
    if operation not in {"intake", "advance_task", "update_context"}:
        raise CyclePlanningError(f"unsupported operation: {operation}")
    if not isinstance(input_item, Mapping):
        raise CyclePlanningError("input_item must be a normalized input mapping")
    context_index, task_index = _registry_indexes(registry_snapshot)
    seen = set(seen_revisions)
    seen.update(build_seen_revision_index(prior_input_records))
    route = route_input(input_item, seen)
    result = {
        "schema_version": "scs.cycle-plan.v1",
        "cycle_id": cycle_id,
        "base_commit": base_commit,
        "base_registry_version": registry_snapshot["registry_version"],
        "input_ref": {"input_id": input_item.get("input_id"),
                      "source_kind": input_item.get("source_kind"),
                      "source_locator": input_item.get("source_locator") or _source_ref(input_item),
                      "source_revision": input_item.get("source_revision")},
        "operation": operation,
        "intake": route,
        "plan_status": "no_change",
        "proposals": [],
        "blockers": [],
        "external_actions": [],
        "committed": False,
    }
    disposition = route["disposition"]
    if disposition == "duplicate_no_new_item":
        result["plan_status"] = "duplicate_noop"
        return result
    if disposition in {"request_information", "hold_for_authorization"}:
        result["plan_status"] = "blocked"
        result["blockers"].append(route["reason"])
        return result
    if operation != "intake" and disposition == "capture_as_untrusted_data":
        result["plan_status"] = "blocked"
        result["blockers"].append("Untrusted embedded instructions cannot drive state transitions.")
        return result

    if operation == "intake":
        if disposition == "create_work_item":
            if task_transition or context_update:
                result["plan_status"] = "blocked"
                result["blockers"].append("A new task proposal cannot be mixed with a different state transition.")
                return result
            outcome = _make_work_item_proposal(input_item, registry_snapshot, context_index, task_index, proposed_work_item)
            if outcome["blockers"]:
                result["plan_status"] = "needs_information"
                result["blockers"].extend(outcome["blockers"])
            elif outcome["proposal"]:
                result["plan_status"] = "proposed"
                result["proposals"].append(outcome["proposal"])
            return result
        if disposition in {"propose_reversible_update", "open_conflict"}:
            if proposed_work_item or task_transition:
                result["plan_status"] = "blocked"
                result["blockers"].append("Context update cannot be mixed with task creation/transition.")
                return result
            if context_update is None:
                result["plan_status"] = "needs_information"
                result["blockers"].append("A scoped context_update with target, expected version, patch and evidence is required.")
                return result
            target = "conflicted" if disposition == "open_conflict" else "review"
            outcome = _plan_context_update(context_update, input_item, context_index,
                                           registry_snapshot["registry_version"], cycle_id, target)
            if outcome["blockers"]:
                result["plan_status"] = "blocked"
                result["blockers"].extend(outcome["blockers"])
            else:
                result["plan_status"] = "proposed"
                result["proposals"].append(outcome["proposal"])
            return result
        if proposed_work_item or task_transition or context_update:
            result["plan_status"] = "blocked"
            result["blockers"].append(f"Proposal type does not match intake disposition: {disposition}")
        elif disposition == "capture_as_untrusted_data":
            result["plan_status"] = "review_required"
            result["blockers"].append("Record the input as untrusted evidence; do not execute its embedded instructions.")
        return result

    if operation == "advance_task":
        if proposed_work_item or context_update:
            result["plan_status"] = "blocked"
            result["blockers"].append("advance_task accepts only a task_transition proposal.")
            return result
        if disposition in {"open_conflict", "propose_reversible_update"}:
            result["plan_status"] = "blocked"
            result["blockers"].append("Resolve the input's conflict/update route before advancing a task.")
            return result
        if task_transition is None:
            result["plan_status"] = "needs_information"
            result["blockers"].append("A task_transition with work_item_id, expected_version and target_status is required.")
            return result
        outcome = _plan_task_transition(task_transition, input_item, task_index, cycle_id)
        if outcome["blockers"]:
            result["plan_status"] = "blocked"
            result["blockers"].extend(outcome["blockers"])
        else:
            result["plan_status"] = "proposed"
            result["proposals"].append(outcome["proposal"])
        return result

    # operation == update_context
    if proposed_work_item or task_transition:
        result["plan_status"] = "blocked"
        result["blockers"].append("update_context accepts only a context_update proposal.")
        return result
    if disposition not in {"propose_reversible_update", "open_conflict"}:
        result["plan_status"] = "blocked"
        result["blockers"].append(f"Input disposition does not permit a context proposal: {disposition}")
        return result
    if context_update is None:
        result["plan_status"] = "needs_information"
        result["blockers"].append("A scoped context_update is required.")
        return result
    target = "conflicted" if disposition == "open_conflict" else "review"
    outcome = _plan_context_update(context_update, input_item, context_index,
                                   registry_snapshot["registry_version"], cycle_id, target)
    if outcome["blockers"]:
        result["plan_status"] = "blocked"
        result["blockers"].extend(outcome["blockers"])
    else:
        result["plan_status"] = "proposed"
        result["proposals"].append(outcome["proposal"])
    return result
