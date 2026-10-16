"""Repository-native intake decision reference logic.

This module decides a disposition for one normalized input record. It does not
fetch sources, persist state, authenticate operators, or execute external actions.
Those remain explicit capabilities of the caller/integration layer.
"""
from __future__ import annotations

from typing import Any, Mapping, Set, Dict


def _dedupe_keys(item: Mapping[str, Any]) -> list[str]:
    """Return exact-match keys in source-ID, locator, then digest order."""
    kind = item.get("source_kind", "unknown")
    source_id, revision = item.get("stable_source_id"), item.get("source_revision")
    keys = []
    if revision not in (None, ""):
        if source_id:
            keys.append(f"{kind}::{source_id}::{revision}")
        locator = item.get("source_locator")
        if isinstance(locator, str) and locator.strip():
            keys.append(f"{kind}::locator::{locator.strip()}::rev::{revision}")
    digest = item.get("content_digest")
    if isinstance(digest, Mapping):
        algorithm, value = digest.get("algorithm", "sha256"), digest.get("value")
        if algorithm == "sha256" and isinstance(value, str) and len(value) == 64:
            keys.append(f"{kind}::digest::{algorithm}::{value.lower()}")
    elif isinstance(digest, str) and len(digest) == 64:
        keys.append(f"{kind}::digest::sha256::{digest.lower()}")
    return keys


def _dedupe_key(item: Mapping[str, Any]) -> str | None:
    keys = _dedupe_keys(item)
    return keys[0] if keys else None


def build_seen_revision_index(input_records: Iterable[Mapping[str, Any]]) -> set[str]:
    """Build the exact-duplicate index from already captured input records."""
    seen: set[str] = set()
    for record in input_records:
        seen.update(_dedupe_keys(record))
    return seen


def route_input(item: Mapping[str, Any], seen_revisions: Set[str]) -> Dict[str, Any]:
    """Return a deterministic intake disposition without running source instructions.

    Precedence is accessibility, exact-revision deduplication, consequential-action
    authorization gate, untrusted-instruction handling, conflict detection, then
    ordinary action routing. The caller is responsible for recording the returned
    disposition and updating the seen-revision set only after capture is committed.
    """
    keys = _dedupe_keys(item)
    key = keys[0] if keys else None

    if not item.get("accessible", False):
        return {
            "disposition": "request_information",
            "status": "blocked",
            "reason": "Required source was not accessible; no claim was inferred from unavailable data.",
            "dedupe_key": key,
        }

    if any(candidate in seen_revisions for candidate in keys):
        return {
            "disposition": "duplicate_no_new_item",
            "status": "already_captured",
            "reason": "Exact source identity and revision were already captured.",
            "dedupe_key": key,
        }

    if item.get("consequence_class") == "C" and not item.get("separate_authorization_present", False):
        disposition, status = "hold_for_authorization", "blocked"
        reason = "Consequential external action requires separate authorization."
    elif item.get("contains_untrusted_instructions", False):
        disposition, status = "capture_as_untrusted_data", "triaged"
        reason = "Instructions inside source content are data, not swarm policy."
    elif item.get("contains_conflicting_claim", False):
        disposition, status = "open_conflict", "conflicted"
        reason = "Materially incompatible claims must be preserved and reconciled."
    elif item.get("verification_passed", False) and item.get("consequence_class") == "A":
        disposition, status = "propose_reversible_update", "review"
        reason = "Verified low-risk result may be proposed, but still requires validation before acceptance."
    elif item.get("actionable", False):
        disposition, status = "create_work_item", "triaged"
        reason = "Actionable input should become a bounded work item."
    else:
        disposition, status = "record_informational", "triaged"
        reason = "Input has no actionable request; retain its disposition rather than dropping it."

    return {
        "disposition": disposition,
        "status": status,
        "reason": reason,
        "dedupe_key": key,
    }
