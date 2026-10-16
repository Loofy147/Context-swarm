"""Pure GitHub-object normalizers for the repository-native swarm.

No function in this module makes network calls, interprets source text as policy,
or executes an operation described by an issue/comment/body. Callers fetch the
exact scoped source through an authorized connector, then pass the returned data
to these normalizers.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_CAPTURED_BY = "scs.github-adapter.v1"
DEFAULT_CONTEXT = "ctx-scs-repository-demo"
OBSERVATION_CONTEXT = "ctx-scs-repository-observation"


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _input_id(source_kind: str, stable_source_id: str, source_revision: str | None) -> str:
    return "IN-GH-" + _digest([source_kind, stable_source_id, source_revision])[:16].upper()


def _claim(source_locator: str, identity: str, text: str, status: str = "observed") -> dict:
    return {
        "claim_id": "CL-GH-" + _digest([identity, text])[:12].upper(),
        "text": text,
        "status": status,
        "source_support": source_locator,
    }


def _date(observed_at: str) -> str:
    if not isinstance(observed_at, str) or len(observed_at) < 10:
        raise ValueError("observed_at must include an ISO date")
    value = observed_at[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("observed_at must start with YYYY-MM-DD")
    return value


def _canonical_repo(repo_full_name: str) -> str:
    if not isinstance(repo_full_name, str) or "/" not in repo_full_name:
        raise ValueError("repo_full_name must be owner/name")
    return repo_full_name.strip()


def _envelope(
    *,
    source_kind: str,
    stable_source_id: str,
    source_revision: str | None,
    source_locator: str,
    observed_at: str,
    repo_full_name: str,
    classification: str,
    actionable: bool = False,
    title: str | None = None,
    target_context_ids: Sequence[str] | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    priority: Mapping[str, Any] | None = None,
    normalized_claims: Sequence[Mapping[str, Any]] | None = None,
    evidence_refs: Sequence[str] | None = None,
    trust_status: str = "source_verified",
    accessible: bool = True,
    verification_passed: bool = False,
    consequence_class: str = "A",
    extra: Mapping[str, Any] | None = None,
) -> dict:
    result = {
        "input_id": _input_id(source_kind, stable_source_id, source_revision),
        "source_kind": source_kind,
        "stable_source_id": stable_source_id,
        "source_revision": source_revision,
        "source_locator": source_locator,
        "observed_at": _date(observed_at),
        "captured_by": DEFAULT_CAPTURED_BY,
        "access_boundary": f"Scoped GitHub API observation for {repo_full_name}; read-only source data.",
        "trust_status": trust_status,
        "classification": classification,
        "accessible": accessible,
        "actionable": actionable,
        "target_context_ids": list(target_context_ids or [DEFAULT_CONTEXT]),
        "acceptance_criteria": list(acceptance_criteria or []),
        "priority": dict(priority or {
            "level": "medium",
            "rationale": "Observation only; this is not a hidden priority score.",
        }),
        "normalized_claims": [dict(c) for c in (normalized_claims or [])],
        "evidence_refs": list(dict.fromkeys([source_locator, *(evidence_refs or [])])),
        "privacy_note": "Only minimal metadata and source evidence pointers are normalized; raw response bodies are not copied wholesale.",
        "consequence_class": consequence_class,
        "separate_authorization_present": False,
        "contains_untrusted_instructions": False,
        "contains_conflicting_claim": False,
        "conflict_refs": [],
        "verification_passed": verification_passed,
    }
    if title is not None:
        result["title"] = title
    if extra:
        result.update(extra)
    return result


def normalize_github_repository(
    repository: Mapping[str, Any],
    *,
    repo_full_name: str,
    branch_head_sha: str | None,
    observed_at: str,
) -> dict:
    """Normalize selected repository metadata; do not infer access beyond this repo."""
    repo_full_name = _canonical_repo(repo_full_name)
    returned_name = repository.get("full_name")
    if returned_name != repo_full_name:
        raise ValueError(f"repository identity mismatch: expected {repo_full_name}, got {returned_name!r}")
    locator = repository.get("html_url") or f"https://api.github.com/repos/{repo_full_name}"
    revision_payload = {
        "branch_head_sha": branch_head_sha,
        "updated_at": repository.get("updated_at"),
        "default_branch": repository.get("default_branch"),
        "private": repository.get("private"),
        "archived": repository.get("archived"),
    }
    revision = "meta:" + _digest(revision_payload)
    facts = []
    if repository.get("full_name"):
        facts.append(_claim(locator, repo_full_name, f"GitHub returned repository identity {repo_full_name}."))
    if isinstance(repository.get("private"), bool):
        visibility = "private" if repository["private"] else "public"
        facts.append(_claim(locator, repo_full_name, f"Repository metadata reports {visibility} visibility."))
    if isinstance(repository.get("archived"), bool):
        facts.append(_claim(locator, repo_full_name, f"Repository archived flag is {str(repository['archived']).lower()}."))
    if repository.get("default_branch"):
        facts.append(_claim(locator, repo_full_name, f"Default branch reported by repository metadata is {repository['default_branch']}."))
    if branch_head_sha:
        facts.append(_claim(locator, repo_full_name, f"Observed default-branch head SHA is {branch_head_sha}."))
    return _envelope(
        source_kind="commit_or_branch",
        stable_source_id=f"repo:{repo_full_name}",
        source_revision=revision,
        source_locator=locator,
        observed_at=observed_at,
        repo_full_name=repo_full_name,
        classification="repository_metadata_observation",
        actionable=False,
        target_context_ids=[OBSERVATION_CONTEXT, DEFAULT_CONTEXT],
        normalized_claims=facts,
        extra={"repository_full_name": repo_full_name},
    )


def normalize_github_commit(
    commit: Mapping[str, Any],
    *,
    repo_full_name: str,
    observed_at: str,
) -> dict:
    """Normalize a single GitHub commit object into a source observation."""
    repo_full_name = _canonical_repo(repo_full_name)
    sha = commit.get("sha")
    if not isinstance(sha, str) or len(sha) < 7:
        raise ValueError("commit object requires sha")
    locator = commit.get("html_url") or f"https://github.com/{repo_full_name}/commit/{sha}"
    raw_commit = commit.get("commit") if isinstance(commit.get("commit"), Mapping) else {}
    message = raw_commit.get("message") if isinstance(raw_commit.get("message"), str) else ""
    subject = message.splitlines()[0].strip() if message else "(no commit subject supplied)"
    author = raw_commit.get("author") if isinstance(raw_commit.get("author"), Mapping) else {}
    authored_at = author.get("date") if isinstance(author.get("date"), str) else None
    claim_text = f"Observed commit {sha[:12]} with subject: {subject}"
    if authored_at:
        claim_text += f"; author timestamp: {authored_at}"
    return _envelope(
        source_kind="commit_or_branch",
        stable_source_id=f"commit:{sha}",
        source_revision=sha,
        source_locator=locator,
        observed_at=observed_at,
        repo_full_name=repo_full_name,
        classification="commit_observation",
        actionable=False,
        target_context_ids=[DEFAULT_CONTEXT, OBSERVATION_CONTEXT],
        normalized_claims=[_claim(locator, sha, claim_text)],
        extra={"commit_sha": sha},
    )


def _priority_from_labels(labels: Any) -> dict:
    names = []
    if isinstance(labels, Sequence) and not isinstance(labels, (str, bytes)):
        for label in labels:
            if isinstance(label, Mapping) and isinstance(label.get("name"), str):
                names.append(label["name"].strip().lower())
            elif isinstance(label, str):
                names.append(label.strip().lower())
    for level in ("critical", "high", "medium", "low"):
        candidates = {f"priority:{level}", f"priority-{level}", f"p{ {'critical':0,'high':1,'medium':2,'low':3}[level] }"}
        if any(name in candidates for name in names):
            return {"level": level, "rationale": f"Priority derived from explicit source label matching {level}."}
    return {"level": "medium", "rationale": "No recognized priority label; treat as provisional triage priority pending review."}


def _acceptance_criteria_from_body(body: Any) -> list[str]:
    """Extract only bullets under an explicit acceptance-criteria heading."""
    if not isinstance(body, str):
        return []
    lines = body.splitlines()
    in_section = False
    criteria = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{1,6}\s*(acceptance criteria|definition of done|done when)\b", stripped, re.IGNORECASE):
            in_section = True
            continue
        if in_section and re.match(r"^#{1,6}\s+", stripped):
            break
        if in_section and re.match(r"^[-*+]\s+", stripped):
            criteria.append(re.sub(r"^[-*+]\s+", "", stripped).strip())
    return [item for item in criteria if item]


def normalize_github_issue(
    issue: Mapping[str, Any],
    *,
    repo_full_name: str,
    observed_at: str,
) -> dict:
    """Normalize an issue/PR while treating title/body as source data, not policy."""
    repo_full_name = _canonical_repo(repo_full_name)
    number = issue.get("number")
    title = issue.get("title")
    if not isinstance(number, int) or not isinstance(title, str) or not title.strip():
        raise ValueError("issue object requires integer number and non-empty title")
    is_pr = isinstance(issue.get("pull_request"), Mapping)
    stable_source_id = f"{'pull-request' if is_pr else 'issue'}:{number}"
    locator = issue.get("html_url") or f"https://github.com/{repo_full_name}/{'pull' if is_pr else 'issues'}/{number}"
    state = issue.get("state") if issue.get("state") in {"open", "closed"} else "unknown"
    merged = bool(issue.get("merged_at"))
    updated_at = issue.get("updated_at") if isinstance(issue.get("updated_at"), str) else None
    revision_payload = {"updated_at": updated_at, "state": state, "title": title, "merged": merged}
    revision = "issue:" + _digest(revision_payload)
    actionable = state == "open" and not merged
    criteria = _acceptance_criteria_from_body(issue.get("body"))
    claims = [_claim(locator, stable_source_id, f"GitHub {'pull request' if is_pr else 'issue'} #{number} title is: {title}")]
    if state in {"open", "closed"}:
        claims.append(_claim(locator, stable_source_id, f"GitHub item state is {state}."))
    return _envelope(
        source_kind="issue_or_pull_request",
        stable_source_id=stable_source_id,
        source_revision=revision,
        source_locator=locator,
        observed_at=observed_at,
        repo_full_name=repo_full_name,
        classification="open_work_item_candidate" if actionable else "issue_or_pull_request_observation",
        actionable=actionable,
        title=title.strip(),
        target_context_ids=[DEFAULT_CONTEXT],
        acceptance_criteria=criteria,
        priority=_priority_from_labels(issue.get("labels")),
        normalized_claims=claims,
        extra={"target_work_item_id": None, "issue_number": number, "is_pull_request": is_pr},
    )


def normalize_github_issue_page(
    issues: Sequence[Mapping[str, Any]],
    *,
    repo_full_name: str,
    query: str,
    observed_at: str,
) -> list[dict]:
    """Normalize a scoped issues-page response. Empty means only that query was empty."""
    repo_full_name = _canonical_repo(repo_full_name)
    if issues:
        return [normalize_github_issue(issue, repo_full_name=repo_full_name, observed_at=observed_at) for issue in issues]
    locator = f"https://api.github.com/repos/{repo_full_name}/issues?{query.lstrip('?')}"
    stable_id = f"issues-page:{repo_full_name}:{query.lstrip('?')}"
    revision = f"empty-page:{_date(observed_at)}"
    claim_text = f"The GitHub issues endpoint returned zero entries for query {query.lstrip('?')} in this observation; this does not establish that tasks are absent from other sources."
    return [_envelope(
        source_kind="issue_or_pull_request",
        stable_source_id=stable_id,
        source_revision=revision,
        source_locator=locator,
        observed_at=observed_at,
        repo_full_name=repo_full_name,
        classification="empty_issue_page_observation",
        actionable=False,
        target_context_ids=[OBSERVATION_CONTEXT, DEFAULT_CONTEXT],
        normalized_claims=[_claim(locator, stable_id, claim_text)],
    )]


def normalize_github_workflow_run(
    run: Mapping[str, Any],
    *,
    repo_full_name: str,
    observed_at: str,
) -> dict:
    """Normalize Actions metadata. Only a completed success is marked verified."""
    repo_full_name = _canonical_repo(repo_full_name)
    run_id = run.get("id")
    if not isinstance(run_id, int):
        raise ValueError("workflow run object requires integer id")
    head_sha = run.get("head_sha") if isinstance(run.get("head_sha"), str) else "unknown"
    status = run.get("status") if isinstance(run.get("status"), str) else "unknown"
    conclusion = run.get("conclusion") if isinstance(run.get("conclusion"), str) else "unknown"
    locator = run.get("html_url") or run.get("url") or f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}"
    updated_at = run.get("updated_at") if isinstance(run.get("updated_at"), str) else None
    revision = f"run:{updated_at or _date(observed_at)}:{status}:{conclusion}:{head_sha}"
    verified = status == "completed" and conclusion == "success"
    claim_text = f"GitHub Actions run {run_id} for commit {head_sha} has status {status} and conclusion {conclusion}."
    claim_status = "verified" if verified else "observed"
    return _envelope(
        source_kind="test_or_workflow_result",
        stable_source_id=f"workflow-run:{run_id}",
        source_revision=revision,
        source_locator=locator,
        observed_at=observed_at,
        repo_full_name=repo_full_name,
        classification="ci_verification_observation",
        actionable=False,
        target_context_ids=[DEFAULT_CONTEXT, OBSERVATION_CONTEXT],
        normalized_claims=[_claim(locator, str(run_id), claim_text, claim_status)],
        verification_passed=verified,
        consequence_class="A",
        extra={"workflow_run_id": run_id, "head_sha": head_sha, "status": status, "conclusion": conclusion},
    )


def normalize_github_source_error(
    *,
    repo_full_name: str,
    source_kind: str,
    stable_source_id: str,
    source_locator: str,
    observed_at: str,
    error_summary: str,
) -> dict:
    """Represent an unavailable source as a blocked input without fabricated claims."""
    repo_full_name = _canonical_repo(repo_full_name)
    return _envelope(
        source_kind=source_kind,
        stable_source_id=stable_source_id,
        source_revision=None,
        source_locator=source_locator,
        observed_at=observed_at,
        repo_full_name=repo_full_name,
        classification="source_unavailable",
        actionable=False,
        target_context_ids=[OBSERVATION_CONTEXT],
        normalized_claims=[],
        evidence_refs=[source_locator],
        trust_status="unreviewed",
        accessible=False,
        extra={"source_error_summary": error_summary},
    )
