"""Pure composition of bounded intake and context revision-impact proposals."""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any
from scs.cycle import plan_batch
from scs.impact import plan_context_impact


class ContextCyclePlanningError(ValueError):
    """The component plans do not share one valid baseline."""


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unranked": 4}


def _priority_summary(batch: Mapping[str, Any]) -> dict[str, Any]:
    counts = {level: 0 for level in ("critical", "high", "medium", "low", "unranked")}
    rows = []
    for item_plan in batch.get("plans", []):
        input_id = item_plan.get("input_ref", {}).get("input_id") or "unknown"
        for proposal in item_plan.get("proposals", []):
            if proposal.get("proposal_type") != "create_work_item":
                continue
            task = proposal.get("work_item", {})
            priority = task.get("priority", {}) if isinstance(task, Mapping) else {}
            level = priority.get("level") if isinstance(priority, Mapping) else None
            level = level if level in {"critical", "high", "medium", "low"} else "unranked"
            counts[level] += 1
            rows.append({
                "input_id": input_id,
                "work_item_id": task.get("work_item_id", "unknown"),
                "title": task.get("title", "Untitled proposal"),
                "priority_level": level,
                "priority_rationale": priority.get("rationale", "") if isinstance(priority, Mapping) else "",
            })
    rows.sort(key=lambda item: (_PRIORITY_ORDER[item["priority_level"]], item["work_item_id"], item["input_id"]))
    return {"proposed_work_items": rows, "counts_by_level": counts}


def _context_conflicts(batch: Mapping[str, Any], impact: Mapping[str, Any]) -> list[dict[str, Any]]:
    updates: dict[str, set[str]] = {}
    for item_plan in batch.get("plans", []):
        input_id = item_plan.get("input_ref", {}).get("input_id") or "unknown"
        for proposal in item_plan.get("proposals", []):
            if proposal.get("proposal_type") == "update_context" and isinstance(proposal.get("context_id"), str):
                updates.setdefault(proposal["context_id"], set()).add(input_id)

    impacted: dict[str, dict[str, set[str]]] = {}
    for kind, field in (("direct", "direct_impacts"), ("possible", "possible_impacts")):
        for item in impact.get(field, []):
            if item.get("target_type") == "context" and isinstance(item.get("target_id"), str):
                impacted.setdefault(item["target_id"], {}).setdefault(kind, set()).update(
                    x for x in item.get("source_ids", []) if isinstance(x, str))
    for field, kind in (("stale_proposals", "stale_context"), ("stale_claim_proposals", "stale_claim")):
        for item in impact.get(field, []):
            if isinstance(item.get("context_id"), str):
                impacted.setdefault(item["context_id"], {}).setdefault(kind, set()).update(
                    x for x in item.get("source_ids", []) if isinstance(x, str))

    conflicts = []
    for context_id in sorted(set(updates) & set(impacted)):
        evidence = set()
        for field in ("direct_impacts", "possible_impacts", "stale_proposals", "stale_claim_proposals"):
            for item in impact.get(field, []):
                if item.get("target_id") == context_id or item.get("context_id") == context_id:
                    evidence.update(x for x in item.get("evidence_refs", []) if isinstance(x, str) and x.strip())
        claim_ids = sorted({x.get("claim_id") for x in impact.get("stale_claim_proposals", [])
                            if x.get("context_id") == context_id and isinstance(x.get("claim_id"), str)})
        conflicts.append({
            "context_id": context_id,
            "input_ids": sorted(updates[context_id]),
            "impact_kinds": sorted(impacted[context_id]),
            "stale_claim_ids": claim_ids,
            "changed_source_ids": sorted(set().union(*impacted[context_id].values())),
            "evidence_refs": sorted(evidence),
            "resolution": "review_required_before_commit",
            "reason": "An intake context update overlaps source impact or staleness for the same context; reconcile both proposals before any commit.",
        })
    return conflicts


def compose_context_cycle_plan(
    *, cycle_id: str, base_commit: str, registry_snapshot: Mapping[str, Any],
    dependency_map: Mapping[str, Any], batch_plan: Mapping[str, Any],
    source_observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compose a batch (including adapter-generated batches) with impact analysis."""
    if not isinstance(cycle_id, str) or not cycle_id.strip():
        raise ContextCyclePlanningError("cycle_id is required")
    if not isinstance(base_commit, str) or len(base_commit.strip()) < 7:
        raise ContextCyclePlanningError("base_commit must identify a repository snapshot")
    if not isinstance(registry_snapshot, Mapping):
        raise ContextCyclePlanningError("registry_snapshot must be an object")
    version = registry_snapshot.get("registry_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ContextCyclePlanningError("registry_version must be a positive integer")
    if not isinstance(batch_plan, Mapping):
        raise ContextCyclePlanningError("batch_plan must be an object")
    if batch_plan.get("cycle_id") != cycle_id:
        raise ContextCyclePlanningError("batch plan cycle_id does not match")
    if batch_plan.get("base_commit") != base_commit:
        raise ContextCyclePlanningError("batch plan base_commit does not match")
    if batch_plan.get("base_registry_version") != version:
        raise ContextCyclePlanningError("batch plan registry version does not match")
    if batch_plan.get("committed") is not False or batch_plan.get("external_actions") != []:
        raise ContextCyclePlanningError("batch plan must be uncommitted with no external actions")
    if not isinstance(source_observations, Sequence) or isinstance(source_observations, (str, bytes)):
        raise ContextCyclePlanningError("source_observations must be a sequence")

    impact = plan_context_impact(
        cycle_id=cycle_id, base_commit=base_commit, registry_snapshot=registry_snapshot,
        dependency_map=dependency_map, source_observations=source_observations)
    conflicts = _context_conflicts(batch_plan, impact)
    priorities = _priority_summary(batch_plan)
    batch_summary = batch_plan.get("summary", {})
    statuses = [x.get("plan_status") for x in batch_plan.get("plans", [])]
    blockers = []
    for item_plan in batch_plan.get("plans", []):
        input_id = item_plan.get("input_ref", {}).get("input_id") or "unknown"
        blockers.extend(f"{input_id}: {message}" for message in item_plan.get("blockers", [])
                        if isinstance(message, str) and message.strip())
    blockers.extend(x for x in impact.get("blockers", []) if isinstance(x, str) and x.strip())
    blockers = list(dict.fromkeys(blockers))
    changed = sum(1 for x in impact.get("source_comparisons", []) if x.get("revision_changed") is True)
    direct = len(impact.get("direct_impacts", []))
    possible = len(impact.get("possible_impacts", []))
    stale_contexts = len(impact.get("stale_proposals", []))
    stale_claims = len(impact.get("stale_claim_proposals", []))

    if impact.get("plan_status") == "blocked":
        status = "blocked"
    elif conflicts or any(s in {"blocked", "conflicted", "needs_information", "review_required"} for s in statuses):
        status = "review_required"
    elif (batch_summary.get("input_records_proposed", 0) or batch_summary.get("state_change_proposals", 0)
          or changed or direct or possible or stale_contexts or stale_claims):
        status = "proposed"
    else:
        status = "no_change"

    return {
        "schema_version": "scs.context-cycle-plan.v1",
        "cycle_id": cycle_id,
        "base_commit": base_commit,
        "base_registry_version": version,
        "plan_status": status,
        "batch_plan": dict(batch_plan),
        "impact_plan": impact,
        "priority_summary": priorities,
        "context_conflicts": conflicts,
        "summary": {
            "input_count": batch_plan.get("input_count", 0),
            "input_records_proposed": batch_summary.get("input_records_proposed", 0),
            "input_duplicate_noops": batch_summary.get("duplicate_noop", 0),
            "state_change_proposals": batch_summary.get("state_change_proposals", 0),
            "changed_sources": changed, "direct_impact_count": direct, "possible_impact_count": possible,
            "stale_context_proposals": stale_contexts, "stale_claim_proposals": stale_claims,
            "priority_proposals": len(priorities["proposed_work_items"]), "context_conflicts": len(conflicts),
        },
        "blockers": blockers,
        "external_actions": [],
        "committed": False,
    }


def plan_context_cycle(
    *, cycle_id: str, base_commit: str, registry_snapshot: Mapping[str, Any],
    dependency_map: Mapping[str, Any], input_items: Sequence[Mapping[str, Any]],
    source_observations: Sequence[Mapping[str, Any]],
    prior_input_records: Sequence[Mapping[str, Any]] = (),
    options_by_input_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan one bounded batch and compose it with source-revision impact proposals."""
    batch = plan_batch(
        cycle_id=cycle_id, base_commit=base_commit, registry_snapshot=registry_snapshot,
        input_items=input_items, prior_input_records=prior_input_records,
        options_by_input_id=options_by_input_id)
    return compose_context_cycle_plan(
        cycle_id=cycle_id, base_commit=base_commit, registry_snapshot=registry_snapshot,
        dependency_map=dependency_map, batch_plan=batch, source_observations=source_observations)
