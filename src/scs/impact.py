"""Pure, deterministic impact analysis for source-revision changes.

The planner returns proposals only. It does not read the network, mutate files,
persist state, commit changes, or perform external actions.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
import posixpath
from typing import Any

from scs.transitions import (
    InvalidTransition,
    StaleStateVersion,
    TransitionPreconditionError,
    plan_transition,
)


class ImpactPlanningError(ValueError):
    """The impact request or graph snapshot is malformed or inconsistent."""


_DIRECT_EDGE_BASES = {
    "direct_import",
    "direct_test_import",
    "direct_schema_validation",
    "JSON_Schema_ref",
    "explicit_test_path",
    "explicit_test_read",
    "explicit_workflow_command",
    "registry_shape_consumed_by_planner",
    "schema_contract_test",
    "test_contract",
}
_DIRECT_CONTEXT_RELATIONS = {"depends_on", "derived_from"}
_POSSIBLE_CONTEXT_RELATIONS = {"references", "shares_with", "conflicts_with", "parent_of"}
_STALE_CLAIM_STATUSES = {"accepted", "verified"}
_STALE_CONTEXT_STATUSES = {"accepted", "active"}


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImpactPlanningError(f"{label} must be a non-empty string")
    return value.strip()


def _revision(value: Any, label: str) -> str:
    if isinstance(value, bool) or value is None:
        raise ImpactPlanningError(f"{label} must be a known string or numeric revision")
    if isinstance(value, str):
        if not value.strip():
            raise ImpactPlanningError(f"{label} must be a known string or numeric revision")
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    raise ImpactPlanningError(f"{label} must be a string or numeric revision")


def _repo_path(value: Any, label: str) -> str:
    path = _nonempty_text(value, label).replace("\\", "/")
    if path.startswith("/") or "://" in path:
        raise ImpactPlanningError(f"{label} must be a repository-relative path, not an absolute path or URL")
    normalized = posixpath.normpath(path)
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise ImpactPlanningError(f"{label} must not escape the repository root")
    return normalized


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ImpactPlanningError(f"{label} must be a list of strings")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ImpactPlanningError(f"{label} must contain only non-empty strings")
        result.append(item.strip())
    return sorted(set(result))


def _matching_refs(refs: Sequence[str], paths: set[str]) -> list[str]:
    matched = []
    for ref in refs:
        candidate = ref.strip().rstrip("/")
        if any(candidate == path or candidate.endswith("/" + path) for path in paths):
            matched.append(ref)
    return sorted(set(matched))


def _add_edge(reverse: dict[str, list[dict[str, str]]], dependency: str,
              dependent: str, ref: str) -> None:
    reverse[dependency].append({
        "dependency": dependency,
        "dependent": dependent,
        "ref": ref,
    })


def _walk_graph(
    seeds: Sequence[tuple[str, str]],
    direct_reverse: Mapping[str, Sequence[Mapping[str, str]]],
    possible_reverse: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Walk dependency edges backward from a changed dependency.

    A direct edge only yields a direct impact when the entire path from the
    changed seed is direct. Any uncertain edge makes that route a possible
    impact. A direct route upgrades an earlier possible route deterministically.
    """
    rank = {"possible": 1, "direct": 2}
    best: dict[str, str] = {}
    via: dict[str, set[str]] = defaultdict(set)
    queue: deque[tuple[str, str]] = deque()

    for node, certainty in seeds:
        old = best.get(node)
        if old is None or rank[certainty] > rank[old]:
            best[node] = certainty
            queue.append((node, certainty))

    while queue:
        current, certainty = queue.popleft()
        for edge_class, graph in (("direct", direct_reverse), ("possible", possible_reverse)):
            next_certainty = "direct" if certainty == "direct" and edge_class == "direct" else "possible"
            for edge in graph.get(current, ()):
                dependent = edge["dependent"]
                via[dependent].add(edge["ref"])
                old = best.get(dependent)
                if old is None or rank[next_certainty] > rank[old]:
                    best[dependent] = next_certainty
                    queue.append((dependent, next_certainty))

    return best, via


def _validate_registry(registry: Mapping[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    version = registry.get("registry_version")
    contexts = registry.get("contexts")
    if not isinstance(version, int) or version < 1:
        raise ImpactPlanningError("registry_snapshot.registry_version must be a positive integer")
    if not isinstance(contexts, list):
        raise ImpactPlanningError("registry_snapshot.contexts must be a list")
    seen = set()
    for context in contexts:
        if not isinstance(context, Mapping):
            raise ImpactPlanningError("every context record must be an object")
        context_id = _nonempty_text(context.get("context_id"), "context_id")
        if context_id in seen:
            raise ImpactPlanningError(f"duplicate context_id: {context_id}")
        seen.add(context_id)
        if not isinstance(context.get("relationships", []), list):
            raise ImpactPlanningError(f"context {context_id} relationships must be a list")
        if not isinstance(context.get("evidence_refs", []), list):
            raise ImpactPlanningError(f"context {context_id} evidence_refs must be a list")
    return version, contexts


def _prepare_sources(source_observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source_observations, Sequence) or isinstance(source_observations, (str, bytes)):
        raise ImpactPlanningError("source_observations must be a list of source revision observations")

    prepared = []
    seen_ids = set()
    for index, raw in enumerate(source_observations):
        if not isinstance(raw, Mapping):
            raise ImpactPlanningError(f"source_observations[{index}] must be an object")
        stable_id = _nonempty_text(raw.get("stable_source_id"), "stable_source_id")
        if stable_id in seen_ids:
            raise ImpactPlanningError(f"duplicate stable_source_id in one plan: {stable_id}")
        seen_ids.add(stable_id)
        source_kind = _nonempty_text(raw.get("source_kind"), "source_kind")
        previous = _revision(raw.get("previous_revision"), f"{stable_id}.previous_revision")
        current = _revision(raw.get("current_revision"), f"{stable_id}.current_revision")
        paths_raw = raw.get("artifact_paths", [])
        if not isinstance(paths_raw, Sequence) or isinstance(paths_raw, (str, bytes)):
            raise ImpactPlanningError(f"{stable_id}.artifact_paths must be a list")
        paths = sorted({_repo_path(path, f"{stable_id}.artifact_paths[]") for path in paths_raw})
        evidence = _string_list(raw.get("evidence_refs", []), f"{stable_id}.evidence_refs")
        prepared.append({
            "stable_source_id": stable_id,
            "source_kind": source_kind,
            "previous_revision": previous,
            "current_revision": current,
            "revision_changed": previous != current,
            "artifact_paths": paths,
            "evidence_refs": evidence,
        })
    return sorted(prepared, key=lambda item: item["stable_source_id"])


def _prepare_artifact_graph(
    dependency_map: Mapping[str, Any],
    map_fresh: bool,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], set[str]]:
    edges = dependency_map.get("edges")
    if not isinstance(edges, list):
        raise ImpactPlanningError("dependency_map.edges must be a list")

    direct_reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    possible_reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    known_paths: set[str] = set()

    for index, edge in enumerate(edges):
        if not isinstance(edge, Mapping):
            raise ImpactPlanningError(f"dependency edge {index} must be an object")
        source_path, target_path = edge.get("source_path"), edge.get("target_path")
        if not isinstance(source_path, str) or not isinstance(target_path, str):
            continue
        if "://" in source_path or "://" in target_path:
            continue
        source_path = _repo_path(source_path, f"dependency edge {index}.source_path")
        target_path = _repo_path(target_path, f"dependency edge {index}.target_path")
        relationship = _nonempty_text(edge.get("relationship"), f"dependency edge {index}.relationship")
        basis = str(edge.get("basis", "unknown"))
        confidence = str(edge.get("confidence", "low"))
        ref = f"{source_path} --{relationship}--> {target_path} [basis={basis}; confidence={confidence}]"
        known_paths.update((source_path, target_path))
        explicitly_grounded = (
            map_fresh and confidence == "high" and basis in _DIRECT_EDGE_BASES
        )
        if explicitly_grounded:
            _add_edge(direct_reverse, target_path, source_path, ref)
        else:
            _add_edge(possible_reverse, target_path, source_path, ref)

    for graph in (direct_reverse, possible_reverse):
        for dependency in graph:
            graph[dependency].sort(key=lambda edge: (edge["dependent"], edge["ref"]))
    return direct_reverse, possible_reverse, known_paths


def _context_graph(contexts: Sequence[Mapping[str, Any]]) -> tuple[
    dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], set[str]
]:
    direct_reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    possible_reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    context_ids = {str(context["context_id"]) for context in contexts}

    for context in contexts:
        source_id = str(context["context_id"])
        relationships = context.get("relationships", [])
        for relationship in relationships:
            if not isinstance(relationship, Mapping):
                raise ImpactPlanningError(f"context {source_id} has a malformed relationship")
            target_id = relationship.get("target_context_id")
            relation_type = relationship.get("type")
            if target_id not in context_ids:
                continue
            if relation_type not in _DIRECT_CONTEXT_RELATIONS | _POSSIBLE_CONTEXT_RELATIONS:
                continue
            ref = f"{source_id} --{relation_type}--> {target_id}"
            bucket = direct_reverse if relation_type in _DIRECT_CONTEXT_RELATIONS else possible_reverse
            _add_edge(bucket, str(target_id), source_id, ref)

    for graph in (direct_reverse, possible_reverse):
        for dependency in graph:
            graph[dependency].sort(key=lambda edge: (edge["dependent"], edge["ref"]))
    return direct_reverse, possible_reverse, context_ids


def plan_context_impact(
    *,
    cycle_id: str,
    base_commit: str,
    registry_snapshot: Mapping[str, Any],
    dependency_map: Mapping[str, Any],
    source_observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a deterministic, uncommitted impact plan for source revision changes.

    Each source observation uses a stable_source_id, source_kind,
    previous_revision, current_revision, artifact_paths, and evidence_refs.
    Explicit high-confidence dependency edges are direct only when the map's
    reviewed_base_commit equals base_commit. Stale/semantic/unknown edges remain
    visible as possible impacts. The planner does not mutate its inputs.
    """
    cycle_id = _nonempty_text(cycle_id, "cycle_id")
    base_commit = _nonempty_text(base_commit, "base_commit")
    if len(base_commit) < 7:
        raise ImpactPlanningError("base_commit must contain at least seven characters")
    if not isinstance(registry_snapshot, Mapping):
        raise ImpactPlanningError("registry_snapshot must be an object")
    if not isinstance(dependency_map, Mapping):
        raise ImpactPlanningError("dependency_map must be an object")

    registry_version, contexts = _validate_registry(registry_snapshot)
    map_version = dependency_map.get("map_version")
    if not isinstance(map_version, int) or map_version < 1:
        raise ImpactPlanningError("dependency_map.map_version must be a positive integer")

    reviewed_base = dependency_map.get("reviewed_base_commit")
    reviewed_base = reviewed_base.strip() if isinstance(reviewed_base, str) else ""
    map_fresh = reviewed_base == base_commit
    observations = _prepare_sources(source_observations)
    changed = [item for item in observations if item["revision_changed"]]
    blockers: list[str] = []

    if changed and not map_fresh:
        blockers.append(
            "Dependency map is not reconciled to the exact base_commit; artifact edges are downgraded to possible impacts."
        )

    direct_reverse, possible_reverse, known_paths = _prepare_artifact_graph(dependency_map, map_fresh)
    context_direct_reverse, context_possible_reverse, context_ids = _context_graph(contexts)

    direct_artifacts: dict[str, dict[str, set[str]]] = {}
    possible_artifacts: dict[str, dict[str, set[str]]] = {}
    direct_contexts: dict[str, dict[str, set[str]]] = {}
    possible_contexts: dict[str, dict[str, set[str]]] = {}
    stale_claims: dict[tuple[str, str], dict[str, Any]] = {}

    def add_impact(
        bucket: dict[str, dict[str, set[str]]],
        target_id: str,
        source_id: str,
        evidence_refs: Sequence[str],
        edge_refs: Sequence[str],
    ) -> None:
        item = bucket.setdefault(target_id, {
            "source_ids": set(), "evidence_refs": set(), "edge_refs": set()
        })
        item["source_ids"].add(source_id)
        item["evidence_refs"].update(evidence_refs)
        item["edge_refs"].update(edge_refs)

    context_index = {str(context["context_id"]): context for context in contexts}
    all_context_refs: dict[str, list[str]] = {}
    for context in contexts:
        refs = _string_list(context.get("evidence_refs", []), f"{context['context_id']}.evidence_refs")
        for claim in context.get("claims", []) or []:
            if not isinstance(claim, Mapping):
                raise ImpactPlanningError(f"context {context['context_id']} has a malformed claim")
            refs.extend(_string_list(claim.get("evidence_refs", []), f"{context['context_id']}.claims.evidence_refs"))
        all_context_refs[str(context["context_id"])] = sorted(set(refs))

    artifact_reference_paths = set(known_paths)
    for refs in all_context_refs.values():
        for ref in refs:
            if "://" not in ref and not ref.startswith("source_revision:"):
                artifact_reference_paths.add(ref)

    for source in changed:
        source_id = source["stable_source_id"]
        source_paths = set(source["artifact_paths"])
        evidence = source["evidence_refs"]
        if not source_paths:
            blockers.append(f"Changed source {source_id} has no artifact_paths mapping.")
            continue
        if not evidence:
            blockers.append(f"Changed source {source_id} has no evidence_refs.")
        for path in source_paths:
            referenced = path in known_paths or any(
                path in refs or any(ref.endswith("/" + path) for ref in refs)
                for refs in all_context_refs.values()
            )
            if not referenced:
                blockers.append(
                    f"No explicit or possible dependency/reference edge maps changed path {path}."
                )

        path_seeds = [(path, "direct") for path in sorted(source_paths)]
        artifact_best, artifact_via = _walk_graph(path_seeds, direct_reverse, possible_reverse)
        direct_path_set = set(source_paths)
        possible_path_set: set[str] = set()

        for path, certainty in artifact_best.items():
            if path in source_paths:
                continue
            if certainty == "direct":
                direct_path_set.add(path)
                add_impact(
                    direct_artifacts, path, source_id, evidence,
                    sorted(artifact_via.get(path, set())),
                )
            else:
                possible_path_set.add(path)
                add_impact(
                    possible_artifacts, path, source_id, evidence,
                    sorted(artifact_via.get(path, set())),
                )

        context_seeds: list[tuple[str, str]] = []
        seed_evidence: dict[str, set[str]] = defaultdict(set)
        for context_id, refs in all_context_refs.items():
            direct_refs = _matching_refs(refs, direct_path_set)
            possible_refs = _matching_refs(refs, possible_path_set)
            if direct_refs:
                context_seeds.append((context_id, "direct"))
                seed_evidence[context_id].update(direct_refs)
            elif possible_refs:
                context_seeds.append((context_id, "possible"))
                seed_evidence[context_id].update(possible_refs)

        context_best, context_via = _walk_graph(
            context_seeds, context_direct_reverse, context_possible_reverse
        )

        for context_id, certainty in context_best.items():
            context = context_index[context_id]
            context_refs = seed_evidence.get(context_id, set())
            # An indirectly affected context retains its own evidence refs for review.
            context_refs.update(_string_list(context.get("evidence_refs", []), f"{context_id}.evidence_refs"))
            if certainty == "direct":
                add_impact(
                    direct_contexts, context_id, source_id, sorted(set(evidence) | context_refs),
                    sorted(context_via.get(context_id, set())),
                )
            else:
                add_impact(
                    possible_contexts, context_id, source_id, sorted(set(evidence) | context_refs),
                    sorted(context_via.get(context_id, set())),
                )

            if certainty != "direct":
                continue

            current_status = context.get("lifecycle_status")
            version = context.get("version")
            if current_status in _STALE_CONTEXT_STATUSES:
                if not isinstance(version, int) or version < 1:
                    blockers.append(f"Context {context_id} has no valid positive version; stale proposal omitted.")
                else:
                    stale_evidence = sorted(set(evidence) | context_refs)
                    try:
                        transition = plan_transition(
                            "context", str(current_status), "stale",
                            current_version=version, expected_version=version,
                            evidence_refs=stale_evidence,
                            reason=f"Source revision changed for {source_id}; review current derived state.",
                        )
                    except (InvalidTransition, StaleStateVersion, TransitionPreconditionError) as exc:
                        blockers.append(f"Context {context_id} could not propose stale transition: {exc}")
                    else:
                        add_impact  # Keep the pure planner visibly side-effect free.
                        proposal_key = context_id
                        proposal_store = stale_claims.setdefault(
                            ("__context__", proposal_key),
                            {
                                "context_id": context_id,
                                "from_status": str(current_status),
                                "base_version": version,
                                "expected_version": version,
                                "result_version": transition["result_version"],
                                "source_ids": set(),
                                "evidence_refs": set(),
                                "edge_refs": set(),
                                "reason": f"Source revision changed for {source_id}; review current derived state.",
                            },
                        )
                        proposal_store["source_ids"].add(source_id)
                        proposal_store["evidence_refs"].update(stale_evidence)
                        proposal_store["edge_refs"].update(context_via.get(context_id, set()))

            for claim in context.get("claims", []) or []:
                claim_id = claim.get("claim_id")
                claim_status = claim.get("status")
                claim_refs = _string_list(claim.get("evidence_refs", []), f"{context_id}.{claim_id}.evidence_refs")
                matching_claim_refs = _matching_refs(claim_refs, direct_path_set)
                if claim_status not in _STALE_CLAIM_STATUSES or not matching_claim_refs:
                    continue
                claim_key = (context_id, str(claim_id))
                proposal = stale_claims.setdefault(
                    claim_key,
                    {
                        "context_id": context_id,
                        "claim_id": str(claim_id),
                        "from_status": str(claim_status),
                        "context_version": context.get("version"),
                        "source_ids": set(),
                        "evidence_refs": set(),
                        "reason": f"Claim evidence intersects changed source {source_id}; preserve history and propose stale review.",
                    },
                )
                proposal["source_ids"].add(source_id)
                proposal["evidence_refs"].update(set(evidence) | set(matching_claim_refs))

    # Emit a blocker instead of an unsupported "no impact" conclusion when a
    # changed source has no resolvable artifact/context impact.
    if changed and not direct_artifacts and not possible_artifacts and not direct_contexts and not possible_contexts:
        blockers.append("Changed revisions produced no resolvable impact; dependency/evidence coverage needs review.")

    direct_impacts = []
    for target_type, bucket in (("artifact", direct_artifacts), ("context", direct_contexts)):
        for target_id, details in bucket.items():
            direct_impacts.append({
                "target_type": target_type,
                "target_id": target_id,
                "source_ids": sorted(details["source_ids"]),
                "evidence_refs": sorted(details["evidence_refs"]),
                "edge_refs": sorted(details["edge_refs"]),
                "reason": (
                    "Affected through exact changed-path evidence or explicitly grounded dependency edges."
                    if target_type == "artifact"
                    else "Affected through context evidence or an explicit depends_on/derived_from relationship."
                ),
            })
    direct_keys = {(item["target_type"], item["target_id"]) for item in direct_impacts}

    possible_impacts = []
    for target_type, bucket in (("artifact", possible_artifacts), ("context", possible_contexts)):
        for target_id, details in bucket.items():
            if (target_type, target_id) in direct_keys:
                continue
            possible_impacts.append({
                "target_type": target_type,
                "target_id": target_id,
                "source_ids": sorted(details["source_ids"]),
                "evidence_refs": sorted(details["evidence_refs"]),
                "edge_refs": sorted(details["edge_refs"]),
                "reason": (
                    "Dependency edge is semantic, uncertain, or not proven against the exact base snapshot."
                    if target_type == "artifact"
                    else "Possible context relation or evidence link; impact needs review before state changes."
                ),
            })

    stale_proposals = []
    stale_claim_proposals = []
    for key, proposal in stale_claims.items():
        if key[0] == "__context__":
            stale_proposals.append({
                "context_id": proposal["context_id"],
                "from_status": proposal["from_status"],
                "to_status": "stale",
                "base_version": proposal["base_version"],
                "expected_version": proposal["expected_version"],
                "result_version": proposal["result_version"],
                "source_ids": sorted(proposal["source_ids"]),
                "evidence_refs": sorted(proposal["evidence_refs"]),
                "edge_refs": sorted(proposal["edge_refs"]),
                "reason": proposal["reason"],
            })
        else:
            stale_claim_proposals.append({
                "context_id": proposal["context_id"],
                "claim_id": proposal["claim_id"],
                "from_status": proposal["from_status"],
                "to_status": "stale",
                "context_version": proposal["context_version"],
                "source_ids": sorted(proposal["source_ids"]),
                "evidence_refs": sorted(proposal["evidence_refs"]),
                "reason": proposal["reason"],
            })

    direct_impacts.sort(key=lambda item: (item["target_type"], item["target_id"]))
    possible_impacts.sort(key=lambda item: (item["target_type"], item["target_id"]))
    stale_proposals.sort(key=lambda item: item["context_id"])
    stale_claim_proposals.sort(key=lambda item: (item["context_id"], item["claim_id"]))
    blockers = sorted(set(blockers))

    if not changed:
        status = "no_change"
    elif blockers:
        status = "blocked"
    else:
        status = "proposed"

    return {
        "schema_version": "scs.impact-plan.v1",
        "cycle_id": cycle_id,
        "base_commit": base_commit,
        "base_registry_version": registry_version,
        "base_dependency_map_version": map_version,
        "dependency_map_reviewed_base_commit": reviewed_base,
        "dependency_map_fresh": map_fresh,
        "plan_status": status,
        "source_comparisons": observations,
        "direct_impacts": direct_impacts,
        "possible_impacts": possible_impacts,
        "stale_proposals": stale_proposals,
        "stale_claim_proposals": stale_claim_proposals,
        "blockers": blockers,
        "external_actions": [],
        "committed": False,
    }
