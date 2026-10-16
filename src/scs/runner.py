"""Orchestrate one captured GitHub snapshot into a bounded SCS cycle plan.

This layer consumes supplied, already-fetched API objects. It has no network,
Git write, persistence, authentication, or external-effect behavior.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from scs.adapters.github import (
    normalize_github_commit,
    normalize_github_issue_page,
    normalize_github_repository,
    normalize_github_source_error,
    normalize_github_workflow_run,
)
from scs.cycle import plan_batch


def plan_github_observation_batch(
    *,
    cycle_id: str,
    base_commit: str,
    repo_full_name: str,
    observed_at: str,
    source_snapshot: Mapping[str, Any],
    registry_snapshot: Mapping[str, Any],
    prior_input_records: Sequence[Mapping[str, Any]] = (),
    context_target_id: str = "ctx-scs-repository-demo",
) -> dict:
    """Normalize repository, commit, issues-page and Actions objects then plan one batch.

    Snapshot keys:
      repository, branch_head_sha, latest_commit, issues, issues_query, workflow_run

    A missing key is treated as an unavailable source and becomes a blocked input.
    An explicit empty issues list is a successful, scoped observation.
    A successful completed workflow run may propose a review-state context update.
    """
    if not isinstance(source_snapshot, Mapping):
        raise ValueError("source_snapshot must be a mapping of captured API objects")

    root = repo_full_name.strip("/")
    if "/" not in root:
        raise ValueError("repo_full_name must be owner/name")

    inputs = []
    query = source_snapshot.get("issues_query", "state=all&per_page=30")

    repository = source_snapshot.get("repository")
    if isinstance(repository, Mapping):
        inputs.append(normalize_github_repository(
            repository,
            repo_full_name=root,
            branch_head_sha=source_snapshot.get("branch_head_sha"),
            observed_at=observed_at,
        ))
    else:
        inputs.append(normalize_github_source_error(
            repo_full_name=root,
            source_kind="commit_or_branch",
            stable_source_id=f"repo:{root}",
            source_locator=f"https://api.github.com/repos/{root}",
            observed_at=observed_at,
            error_summary="Repository metadata was not present in the captured source snapshot.",
        ))

    latest_commit = source_snapshot.get("latest_commit")
    if isinstance(latest_commit, Mapping):
        inputs.append(normalize_github_commit(
            latest_commit, repo_full_name=root, observed_at=observed_at
        ))
    else:
        inputs.append(normalize_github_source_error(
            repo_full_name=root,
            source_kind="commit_or_branch",
            stable_source_id=f"latest-commit:{root}",
            source_locator=f"https://api.github.com/repos/{root}/commits?per_page=1",
            observed_at=observed_at,
            error_summary="Latest commit object was not present in the captured source snapshot.",
        ))

    issues = source_snapshot.get("issues")
    if isinstance(issues, list) and all(isinstance(item, Mapping) for item in issues):
        inputs.extend(normalize_github_issue_page(
            issues, repo_full_name=root, query=str(query), observed_at=observed_at
        ))
    else:
        inputs.append(normalize_github_source_error(
            repo_full_name=root,
            source_kind="issue_or_pull_request",
            stable_source_id=f"issues-page:{root}:{query}",
            source_locator=f"https://api.github.com/repos/{root}/issues?{str(query).lstrip('?')}",
            observed_at=observed_at,
            error_summary="Issues-page response was not available as a list; it is not interpreted as an empty response.",
        ))

    workflow_run = source_snapshot.get("workflow_run")
    workflow_input = None
    if isinstance(workflow_run, Mapping):
        workflow_input = normalize_github_workflow_run(
            workflow_run, repo_full_name=root, observed_at=observed_at
        )
        inputs.append(workflow_input)
    else:
        inputs.append(normalize_github_source_error(
            repo_full_name=root,
            source_kind="test_or_workflow_result",
            stable_source_id=f"workflow-run-observation:{root}",
            source_locator=f"https://api.github.com/repos/{root}/actions/runs?per_page=30",
            observed_at=observed_at,
            error_summary="Workflow-run object was not present in the captured source snapshot.",
        ))

    options_by_input_id: dict[str, dict] = {}
    if workflow_input and workflow_input.get("verification_passed"):
        context = next(
            (ctx for ctx in registry_snapshot.get("contexts", [])
             if ctx.get("context_id") == context_target_id),
            None,
        )
        if context is not None:
            claim = workflow_input["normalized_claims"][0]
            options_by_input_id[workflow_input["input_id"]] = {
                "operation": "update_context",
                "context_update": {
                    "context_id": context_target_id,
                    "expected_version": context["version"],
                    "patch": {
                        "claims_append": [{
                            "claim_id": claim["claim_id"],
                            "text": claim["text"],
                            "status": claim["status"],
                            "evidence_refs": [workflow_input["source_locator"]],
                        }]
                    },
                    "evidence_refs": [workflow_input["source_locator"]],
                    "reason": (
                        f"Propose recording workflow run {workflow_input['workflow_run_id']} "
                        "as verified evidence; acceptance remains a separate review."
                    ),
                },
            }

    return plan_batch(
        cycle_id=cycle_id,
        base_commit=base_commit,
        registry_snapshot=registry_snapshot,
        input_items=inputs,
        prior_input_records=prior_input_records,
        options_by_input_id=options_by_input_id,
    )
