"""Pure dependency-impact planning for repository-native swarm context states.

The planner compares two supplied source snapshots, walks a pinned typed dependency
map in reverse dependency direction, and proposes conservative stale updates. It
does not fetch sources, mutate the registry, commit, or perform external actions.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
from typing import Any, Iterable, Mapping


class ImpactPlanningError(ValueError):
    """The source snapshots, registry, or dependency map are malformed."""


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _repo_path(value: Any) -> str | None:
    """Normalize a repository-relative path; external locators return None."""
    if not _is_text(value):
        return None
    value = value.strip().replace("\\", "/")
    if "://" in value or value.startswith("//"):
        return None
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        raise ImpactPlanningError(f"repository path must be relative: {value}")
    normalized = posixpath.normpath(value)
    if normalized in {"", ".", ".."} or normalized.startswith("../") or normalized.startswith("/"):
        raise ImpactPlanningError(f"repository path escapes the repository: {value}")
    return normalized


def _record_paths(record: Mapping[str, Any]) -> list[str]:
    raw = record.get("source_paths", record.get("artifact_paths", record.get("source_path")))
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    elif raw is None:
        values = []
    else:
        raise ImpactPlanningError("source_paths/source_path must be a string or list")
    paths: list[str] = []
    for value in values:
        path = _repo_path(value)
        if path and path not in paths:
            paths.append(path)
    if not paths:
        locator = record.get("source_locator", record.get("locator"))
        if _is_text(locator) and not locator.strip().startswith(
            ("input:", "source:", "file:", "issue:", "commit:")
        ):
            path = _repo_path(locator)
            if path:
                paths.append(path)
    return sorted(paths)


def _source_refs(record: Mapping[str, Any]) -> list[str]:
    refs = record.get("evidence_refs", [])
    if not isinstance(refs, list):
        raise ImpactPlanningError("source evidence_refs must be a list")
    result = [item.strip() for item in refs if _is_text(item)]
    locator = record.get("source_locator", record.get("locator"))
    if _is_text(locator):
        result.append(locator.strip())
    return sorted(set(result))


def _source_index(records: Iterable[Mapping[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, (list, tuple)):
        raise ImpactPlanningError(f"{label} must be a list of source records")
    indexed: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise ImpactPlanningError(f"{label}[{index}] must be an object")
        identity = raw.get("stable_source_id", raw.get("source_id"))
        if not _is_text(identity):
            raise ImpactPlanningError(f"{label}[{index}] requires stable_source_id or source_id")
        identity = identity.strip()
        if identity in indexed:
            raise ImpactPlanningError(f"{label} contains duplicate stable source identity: {identity}")
        revision = raw.get("source_revision", raw.get("revision"))
        if revision is not None and not isinstance(revision, str):
            raise ImpactPlanningError(f"{label}[{index}] source revision must be a string or null")
        routes = raw.get("context_routes", [])
        if not isinstance(routes, list):
            raise ImpactPlanningError(f"{label}[{index}] context_routes must be a list")
        indexed[identity] = {
            "stable_source_id": identity,
            "source_kind": raw.get("source_kind"),
            "source_revision": revision,
            "source_paths": _record_paths(raw),
            "evidence_refs": _source_refs(raw),
            "context_routes": sorted(set(value.strip() for value in routes if _is_text(value))),
        }
    return indexed


def _is_explicit_edge(edge: Mapping[str, Any]) -> bool:
    basis = str(edge.get("basis", "")).lower()
    confidence = str(edge.get("confidence", "")).lower()
    uncertain_markers = ("semantic", "contract", "planned", "hypothes", "relationship", "design")
    direct_markers = ("direct", "explicit", "imports", "loads", "validates",
                      "workflow_command", "json_equality", "schema_ref",
                      "schema_validation", "exact_path")
    return (
        confidence == "high"
        and any(marker in basis for marker in direct_markers)
        and not any(marker in basis for marker in uncertain_markers)
    )


def _edge_index(dependency_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    edges = dependency_map.get("edges")
    if not isinstance(edges, list):
        raise ImpactPlanningError("dependency map must contain an edges array")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(edges):
        if not isinstance(raw, Mapping):
            raise ImpactPlanningError(f"dependency edge {index} must be an object")
        source_raw, target_raw = raw.get("source_path"), raw.get("target_path")
        if not _is_text(source_raw) or not _is_text(target_raw):
            raise ImpactPlanningError(f"dependency edge {index} requires source_path and target_path")
        source_path = _repo_path(source_raw)
        target_path = _repo_path(target_raw)
        if source_path is None or target_path is None:
            continue
        relationship = str(raw.get("relationship", "unknown"))
        basis = str(raw.get("basis", "unknown"))
        normalized.append({
            "source_path": source_path,
            "target_path": target_path,
            "relationship": relationship,
            "basis": basis,
            "explicit": _is_explicit_edge(raw),
            "edge_ref": f"{source_path} <- {target_path} ({relationship}; {basis})",
        })
    return normalized


def _add_impact(
    bucket: dict[tuple[str, str], dict[str, Any]],
    target_type: str,
    target_id: str,
    source_ids: Iterable[str],
    evidence_refs: Iterable[str],
    reason: str,
) -> None:
    key = (target_type, target_id)
    item = bucket.setdefault(key, {
        "target_type": target_type,
        "target_id": target_id,
        "changed_source_ids": [],
        "evidence_refs": [],
        "reasons": [],
    })
    item["changed_source_ids"] = sorted(set(item["changed_source_ids"]) | set(source_ids))
    item["evidence_refs"] = sorted(
        set(item["evidence_refs"]) | {value for value in evidence_refs if _is_text(value)}
    )
    if reason and reason not in item["reasons"]:
        item["reasons"] = sorted(set(item["reasons"]) | {reason})


def _impact_records(bucket: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    return [bucket[key] for key in sorted(bucket)]


def plan_impact(
    *,
    base_commit: str,
    registry_snapshot: Mapping[str, Any],
    dependency_map: Mapping[str, Any],
    previous_sources: Iterable[Mapping[str, Any]],
    current_sources: Iterable[Mapping[str, Any]],
    source_catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, schema-oriented impact proposal without side effects.

    Each dependency-map edge means source_path depends on target_path. A changed
    target therefore propagates backwards to its dependent source_path. Only high
    confidence explicit edges in a map reviewed against base_commit are direct.
    """
    if not _is_text(base_commit):
        raise ImpactPlanningError("base_commit is required")
    if not isinstance(registry_snapshot, Mapping):
        raise ImpactPlanningError("registry_snapshot must be an object")
    if registry_snapshot.get("canonical_store") != "git_tracked_repository_artifacts":
        raise ImpactPlanningError("impact planning requires a repository-native registry snapshot")
    registry_version = registry_snapshot.get("registry_version")
    if not isinstance(registry_version, int) or isinstance(registry_version, bool) or registry_version < 1:
        raise ImpactPlanningError("registry_version must be a positive integer")
    raw_contexts = registry_snapshot.get("contexts")
    if not isinstance(raw_contexts, list):
        raise ImpactPlanningError("registry snapshot must contain contexts")
    contexts: dict[str, Mapping[str, Any]] = {}
    for index, context in enumerate(raw_contexts):
        if not isinstance(context, Mapping) or not _is_text(context.get("context_id")):
            raise ImpactPlanningError(f"context {index} requires context_id")
        context_id = context["context_id"].strip()
        if context_id in contexts:
            raise ImpactPlanningError(f"duplicate context_id: {context_id}")
        contexts[context_id] = context
    for context_id, context in contexts.items():
        relationships = context.get("relationships", [])
        if not isinstance(relationships, list):
            raise ImpactPlanningError(f"context {context_id} relationships must be a list")
        for relationship in relationships:
            if not isinstance(relationship, Mapping):
                raise ImpactPlanningError(f"context {context_id} has a malformed relationship")
            if relationship.get("target_context_id") not in contexts:
                raise ImpactPlanningError(
                    f"context {context_id} has a dangling relationship: {relationship.get('target_context_id')}"
                )

    if not isinstance(dependency_map, Mapping):
        raise ImpactPlanningError("dependency_map must be an object")
    edges = _edge_index(dependency_map)
    previous = _source_index(previous_sources, "previous_sources")
    current = _source_index(current_sources, "current_sources")
    source_catalog = source_catalog if isinstance(source_catalog, Mapping) else {}
    catalog_records = source_catalog.get("sources", [])
    if not isinstance(catalog_records, list):
        raise ImpactPlanningError("source_catalog.sources must be a list")
    catalog: dict[str, Mapping[str, Any]] = {}
    for record in catalog_records:
        if isinstance(record, Mapping):
            source_id = record.get("source_id", record.get("stable_source_id"))
            if _is_text(source_id):
                catalog[source_id.strip()] = record

    map_base = dependency_map.get("reviewed_base_commit")
    map_version = dependency_map.get("map_version")
    map_fresh = isinstance(map_base, str) and map_base == base_commit
    source_changes: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for identity in sorted(set(previous) | set(current)):
        old, new = previous.get(identity), current.get(identity)
        if old is None:
            kind = "added"
        elif new is None:
            kind = "removed"
        elif old["source_revision"] is None or new["source_revision"] is None:
            if old["source_paths"] != new["source_paths"]:
                kind = "path_changed"
            else:
                unresolved.append(identity)
                continue
        elif old["source_revision"] != new["source_revision"]:
            kind = "revision_changed"
        elif old["source_paths"] != new["source_paths"]:
            kind = "path_changed"
        else:
            continue
        paths = sorted(set((old or {}).get("source_paths", [])) | set((new or {}).get("source_paths", [])))
        refs = sorted(set((old or {}).get("evidence_refs", [])) | set((new or {}).get("evidence_refs", [])))
        source_changes.append({
            "stable_source_id": identity,
            "change_kind": kind,
            "previous_revision": (old or {}).get("source_revision"),
            "current_revision": (new or {}).get("source_revision"),
            "source_paths": paths,
            "evidence_refs": refs,
        })

    changed_refs = {ref for row in source_changes for ref in row["evidence_refs"]}
    root_causes: dict[str, set[str]] = {}
    for row in source_changes:
        for path in row["source_paths"]:
            root_causes.setdefault(path, set()).add(row["stable_source_id"])

    direct_impacts: dict[tuple[str, str], dict[str, Any]] = {}
    possible_impacts: dict[tuple[str, str], dict[str, Any]] = {}
    for identity in unresolved:
        refs = set(previous[identity]["evidence_refs"]) | set(current[identity]["evidence_refs"])
        _add_impact(
            possible_impacts, "source", identity, [identity], refs,
            "At least one revision is missing; a no-change result cannot be established.",
        )
    for row in source_changes:
        if not row["source_paths"]:
            _add_impact(
                possible_impacts, "source", row["stable_source_id"],
                [row["stable_source_id"]], row["evidence_refs"],
                "Changed source has no exact repository path; dependencies require review.",
            )

    # Fixed-point reverse traversal with conservative handling of stale/weak edges.
    direct_causes = {path: set(ids) for path, ids in root_causes.items()}
    possible_causes: dict[str, set[str]] = {}
    direct_edges: dict[str, set[str]] = {}
    possible_edges: dict[str, set[str]] = {}
    max_rounds = max(1, len(edges) + 1)
    for _ in range(max_rounds):
        changed = False
        for edge in edges:
            dependency, dependent = edge["target_path"], edge["source_path"]
            if dependency in direct_causes:
                causes = direct_causes[dependency]
                if map_fresh and edge["explicit"]:
                    target = direct_causes.setdefault(dependent, set())
                    before = len(target)
                    target.update(causes)
                    if len(target) != before:
                        changed = True
                    if dependent not in root_causes:
                        bucket = direct_edges.setdefault(dependent, set())
                        if edge["edge_ref"] not in bucket:
                            bucket.add(edge["edge_ref"])
                            changed = True
                else:
                    target = possible_causes.setdefault(dependent, set())
                    before = len(target)
                    target.update(causes)
                    if len(target) != before:
                        changed = True
                    bucket = possible_edges.setdefault(dependent, set())
                    if edge["edge_ref"] not in bucket:
                        bucket.add(edge["edge_ref"])
                        changed = True
            elif dependency in possible_causes:
                target = possible_causes.setdefault(dependent, set())
                before = len(target)
                target.update(possible_causes[dependency])
                if len(target) != before:
                    changed = True
                bucket = possible_edges.setdefault(dependent, set())
                if edge["edge_ref"] not in bucket:
                    bucket.add(edge["edge_ref"])
                    changed = True
        if not changed:
            break

    all_direct_paths = set(direct_causes)
    all_possible_paths = set(possible_causes) - all_direct_paths
    for path, causes in sorted(direct_edges.items()):
        refs = {f"path:{path}"}
        refs.update(ref for row in source_changes if row["stable_source_id"] in causes for ref in row["evidence_refs"])
        _add_impact(
            direct_impacts, "artifact", path, causes, refs,
            "Reached through an explicit high-confidence dependency edge in a map reviewed at the plan base.",
        )
    for path, causes in sorted(possible_causes.items()):
        if path in all_direct_paths:
            continue
        refs = {f"path:{path}"}
        refs.update(ref for row in source_changes if row["stable_source_id"] in causes for ref in row["evidence_refs"])
        reason = (
            "Dependency edge is semantic/weak."
            if map_fresh else
            "Dependency map was not reviewed against the exact plan base."
        )
        _add_impact(possible_impacts, "artifact", path, causes, refs, reason)

    # Context evidence paths may establish direct impact; context relations and
    # catalog routes are only possible impact hints.
    direct_context_causes: dict[str, set[str]] = {}
    possible_context_causes: dict[str, set[str]] = {}
    context_reasons: dict[str, set[str]] = {}
    for context_id, context in contexts.items():
        refs = context.get("evidence_refs", [])
        if not isinstance(refs, list):
            raise ImpactPlanningError(f"context {context_id} evidence_refs must be a list")
        referenced = {_repo_path(ref) for ref in refs if _is_text(ref)}
        referenced.discard(None)
        matched = referenced & all_direct_paths
        if matched:
            causes = set().union(*(direct_causes[path] for path in matched))
            direct_context_causes[context_id] = causes
            context_reasons.setdefault(context_id, set()).add(
                "Context evidence_refs identify a changed or directly affected repository path."
            )
        possible_matches = referenced & all_possible_paths
        if possible_matches:
            causes = set().union(*(possible_causes[path] for path in possible_matches))
            possible_context_causes.setdefault(context_id, set()).update(causes)
            context_reasons.setdefault(context_id, set()).add(
                "Context references a path reached only through uncertain dependency metadata."
            )

    for row in source_changes:
        catalog_entry = catalog.get(row["stable_source_id"], {})
        routes = set(catalog_entry.get("context_routes", [])) if isinstance(catalog_entry, Mapping) else set()
        routes.update((current.get(row["stable_source_id"]) or {}).get("context_routes", []))
        for context_id in routes:
            if context_id in contexts:
                _add_impact(
                    possible_impacts, "context", context_id, [row["stable_source_id"]],
                    row["evidence_refs"],
                    "Source-catalog context routes are discovery hints, not direct dependency evidence.",
                )
    for identity in unresolved:
        catalog_entry = catalog.get(identity, {})
        routes = catalog_entry.get("context_routes", []) if isinstance(catalog_entry, Mapping) else []
        for context_id in routes:
            if context_id in contexts:
                _add_impact(
                    possible_impacts, "context", context_id, [identity],
                    set(previous[identity]["evidence_refs"]) | set(current[identity]["evidence_refs"]),
                    "Source revision is unresolved; catalog routing indicates possible impact only.",
                )

    for _ in range(max(1, len(contexts))):
        changed = False
        for context_id, context in contexts.items():
            for relationship in context.get("relationships", []):
                if relationship.get("type") not in {"depends_on", "derived_from"}:
                    continue
                dependency_id = relationship["target_context_id"]
                causes = direct_context_causes.get(dependency_id) or possible_context_causes.get(dependency_id)
                if not causes:
                    continue
                target = possible_context_causes.setdefault(context_id, set())
                before = len(target)
                target.update(causes)
                if len(target) != before:
                    changed = True
                context_reasons.setdefault(context_id, set()).add(
                    f"Context relation {relationship['type']} -> {dependency_id} is treated as possible impact, not direct."
                )
        if not changed:
            break

    impact_evidence = set(changed_refs) | {f"commit:{base_commit}"}
    impact_evidence.update(f"path:{path}" for path in all_direct_paths)
    for context_id, causes in sorted(direct_context_causes.items()):
        _add_impact(
            direct_impacts, "context", context_id, causes, impact_evidence,
            "; ".join(sorted(context_reasons.get(context_id, {"Direct context evidence dependency changed."}))),
        )
    for context_id, causes in sorted(possible_context_causes.items()):
        if context_id in direct_context_causes:
            continue
        _add_impact(
            possible_impacts, "context", context_id, causes, impact_evidence,
            "; ".join(sorted(context_reasons.get(context_id, {"Possible semantic context dependency."}))),
        )

    stale_proposals: list[dict[str, Any]] = []
    stale_keys: set[tuple[str, str, str | None]] = set()
    direct_changed_refs = set(changed_refs) | {f"path:{path}" for path in all_direct_paths}
    for context_id, causes in sorted(direct_context_causes.items()):
        context = contexts[context_id]
        status, version = context.get("lifecycle_status"), context.get("version")
        if status not in {"active", "accepted"} or not isinstance(version, int) or isinstance(version, bool):
            continue
        claims = context.get("claims", [])
        if not isinstance(claims, list):
            raise ImpactPlanningError(f"context {context_id} claims must be a list")
        if not claims:
            key = ("context", context_id, None)
            if key not in stale_keys:
                stale_keys.add(key)
                stale_proposals.append({
                    "target_type": "context",
                    "context_id": context_id,
                    "claim_id": None,
                    "expected_version": version,
                    "proposed_version": version + 1,
                    "from_status": status,
                    "proposed_status": "stale",
                    "reason": "Direct evidence dependency changed; propose a new stale version without rewriting accepted history.",
                    "evidence_refs": sorted(direct_changed_refs | {f"context:{context_id}:v{version}"}),
                })
            continue
        for claim in claims:
            if not isinstance(claim, Mapping) or claim.get("status") not in {"verified", "accepted"}:
                continue
            claim_id = claim.get("claim_id")
            if not _is_text(claim_id):
                raise ImpactPlanningError(f"context {context_id} has a verified claim without claim_id")
            claim_refs = claim.get("evidence_refs", [])
            if not isinstance(claim_refs, list):
                raise ImpactPlanningError(f"claim {claim_id} evidence_refs must be a list")
            claim_paths = {_repo_path(ref) for ref in claim_refs if _is_text(ref)}
            claim_paths.discard(None)
            tied_to_change = bool(set(claim_refs) & changed_refs) or bool(claim_paths & all_direct_paths)
            if tied_to_change:
                key = ("claim", context_id, claim_id)
                if key not in stale_keys:
                    stale_keys.add(key)
                    stale_proposals.append({
                        "target_type": "claim",
                        "context_id": context_id,
                        "claim_id": claim_id,
                        "expected_version": version,
                        "proposed_version": version + 1,
                        "from_status": claim["status"],
                        "proposed_status": "stale",
                        "reason": "Verified/accepted claim has explicit evidence tied to a changed source or directly affected path.",
                        "evidence_refs": sorted(set(claim_refs) | direct_changed_refs),
                    })
                    _add_impact(
                        direct_impacts, "claim", f"{context_id}/{claim_id}", causes,
                        set(claim_refs) | direct_changed_refs,
                        "Verified/accepted claim evidence is directly affected by a source revision change.",
                    )
            else:
                _add_impact(
                    possible_impacts, "claim", f"{context_id}/{claim_id}", causes,
                    set(claim_refs) | impact_evidence,
                    "Context is impacted, but this claim has no exact evidence tie to the changed source; review before marking stale.",
                )

    # If direct evidence proves a context is directly impacted, its weaker route
    # should remain documented but the same context is not duplicated in possible impact.
    for key in list(possible_impacts):
        if key[0] == "context" and key[1] in direct_context_causes:
            possible_impacts.pop(key, None)

    all_evidence = set(impact_evidence)
    for item in _impact_records(direct_impacts) + _impact_records(possible_impacts):
        all_evidence.update(item["evidence_refs"])
    plan_status = "no_change" if not source_changes and not unresolved else (
        "proposed" if stale_proposals or direct_impacts else "review_required"
    )
    identity_payload = {
        "base_commit": base_commit,
        "base_registry_version": registry_version,
        "source_changes": source_changes,
        "unresolved_source_ids": sorted(unresolved),
        "dependency_map_reviewed_base": map_base,
        "dependency_map_version": map_version,
    }
    plan_id = "SCS-IMPACT-" + hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16].upper()
    return {
        "schema_version": "scs.impact-plan.v1",
        "plan_id": plan_id,
        "base_commit": base_commit,
        "base_registry_version": registry_version,
        "dependency_map": {
            "map_version": map_version if isinstance(map_version, int) and not isinstance(map_version, bool) else None,
            "reviewed_base_commit": map_base if isinstance(map_base, str) else None,
            "matches_base_commit": map_fresh,
        },
        "plan_status": plan_status,
        "source_changes": source_changes,
        "unresolved_source_ids": sorted(unresolved),
        "direct_impacts": _impact_records(direct_impacts),
        "possible_impacts": _impact_records(possible_impacts),
        "stale_proposals": sorted(stale_proposals, key=lambda item: (item["context_id"], item["target_type"], item["claim_id"] or "")),
        "evidence_refs": sorted(ref for ref in all_evidence if _is_text(ref)),
        "blockers": [],
        "external_actions": [],
        "committed": False,
    }
