# Swarm cycle runbook

Use this for each discrete repository-native swarm cycle. This is the current execution method; it does not require a service or background worker.

## Start a cycle

1. Read `swarm/registry.json`, `swarm/intake-policy.json`, and the relevant context dossiers.
2. Select one work item whose dependencies are accepted. Honor explicit user priority and authorization constraints before generic priority.
3. Record a cycle ID and the exact base commit and context versions being read.
4. Inspect the task's source references using only currently available, authorized tools. Record inaccessible sources rather than infer their contents.
5. Create or reuse input records. Normalize while preserving source locators, revisions, trust status, and exact evidence pointers.
6. Run the intake decision logic or apply the same rules explicitly. Duplicate, conflict, untrusted-content, missing-access, and consequential-action checks take precedence over ordinary task routing.
7. Bound the work to the item's scope and acceptance criteria. Do not broaden the task merely because related work is discoverable.
8. Produce a proposed context update, task outcome, supporting evidence, and test changes.

## Validate before accepting

- Check the proposal against the exact base versions read at cycle start.
- Validate JSON syntax and the documented schema contract.
- Check references resolve; no context/task relationship may point to a missing ID.
- Separate observed facts, inferences, proposals, and accepted decisions.
- Check source provenance, dependency freshness, conflicting claims, security boundaries, and consequences.
- Run relevant tests. For changed behavior, add/update fixtures and tests alongside or before accepting the rule.
- If validation fails, preserve the proposal as blocked/conflicted/review; do not label it accepted.

## Commit a cycle

1. Update the relevant context state version and work-item status.
2. Add evidence references, test results, and the change rationale.
3. Update inventory or derived dependency records when their inputs change.
4. Record the cycle outcome under `swarm/cycles/`.
5. Commit the correlated state changes. Prefer one commit for mutually dependent files. If tool limitations force separate commits, preserve explicit parent/base references and do not pretend the series was atomic.
6. Verify the resulting Git commit and CI result. Update the registry with the verified commit/run reference in the next state update if CI completed afterward.

## Required cycle report

Each cycle record states:
- cycle ID and source/base commit;
- inputs consumed and access scope;
- work item(s) selected;
- contexts read and target versions;
- disposition of every input;
- changes made, with path/commit references;
- tests executed and the exact result;
- conflicts, unknowns, inaccessible sources, and deferred consequences;
- follow-up tasks added or closed.

A cycle is not complete just because a response was generated. Durable state, evidence, and explicit disposition must be recorded, or the cycle must explain why no commit was appropriate.

## Batch related changes

When Git data tools are available, group related state/schema/test updates into one logical commit:
1. Read the exact branch head and matching tree SHA.
2. Create blobs for changed and new files.
3. Create one tree based on the observed tree, overlaying only scoped paths.
4. Create a commit whose parent is the observed branch head.
5. Update the branch only if its current head still equals the expected SHA.
6. Verify the resulting head and CI result for that grouped commit.

If the branch moved, stop and reconcile. Never force-push around a conflict. Use per-file contents operations only when batching is unavailable or changes are independent. CI can cancel obsolete runs, but the final resulting state must pass.

## Retry and concurrent change behavior

If the branch head or expected context version changes during work, stop before overwriting. Reload the current registry, compare the changed records, and rebase/reconcile the proposal. Never force-push to bypass conflicting context state.

## Scope boundary

This runbook coordinates work in the repository and through authorized connected tools. It does not create continuous background execution, universal integration access, production authentication, or transactional writes to external services. Consequential external mutations require a separate permission/approval check.


## Input capture proposals and batch planning

The planner now returns an `input_record_proposal` for every non-duplicate input with adequate provenance, including inputs whose source is inaccessible or whose requested action is blocked. The proposed record preserves the locator/access boundary and records zero claims when source content was not available. A duplicate returns a no-op and does not propose a second record.

For multiple sources in one bounded cycle, use `plan_batch` with the same explicit base commit and registry snapshot. The batch limit is 100 items. It builds its duplicate index from existing captured records and from input records proposed earlier in the same batch. Batch plans remain uncommitted; the caller must validate and commit accepted proposals. Multiple context updates targeting the same context are not silently merged: later conflicting proposals are blocked for explicit merge/rebase.

Each record must preserve source identity/revision, observed date, capture actor, trust status, access boundary, disposition, and affected context/task links. Missing provenance produces a `needs_information` result rather than a fabricated input record. The tool/source catalog guides discovery but never grants access.


## GitHub source normalizers and snapshot runner

For an explicit GitHub observation, the authorized source layer fetches the exact repository/commit/issues/Actions objects and records the response time, source locator and revision. Pass the captured objects to `plan_github_observation_batch` in `src/scs/runner.py` with the exact base commit, registry snapshot and previously captured input records.

The pure normalizers do not fetch network data. They preserve source ID/revision and only extract fields needed for routing/provenance. Issue bodies are untrusted data; only bullets under an explicit Acceptance Criteria/Definition of Done heading are extracted. An empty issues response remains a scoped observation; a missing response becomes a blocked record with no fabricated claims. A completed successful workflow may create a proposed claim for review, not accepted truth.

Validate the candidate envelopes and returned batch plan. Commit accepted input records, the correlated registry changes and cycle report in one coherent commit where possible. Replay the same source snapshot to ensure exact revisions produce duplicate no-ops. No external side effects are executed by the adapters/runner.


## Fresh snapshot capture — cycle 0006

The captured source is `swarm/sources/github-snapshot-cycle-0006.json`; its matching registry is frozen at `tests/fixtures/registry-source-cycle-0006.json`. Four normalized inputs are stored under `swarm/inputs/IN-GH-*.json`: repository metadata, latest commit, a scoped empty issues page, and a successful Actions run.

The integration test regenerates the batch with `plan_github_observation_batch`, compares the proposed input records field-for-field with the persisted JSON files, then replays the same source revisions. Cycle 0006 remains in review until these checks pass on the exact repository commit. The successful workflow observation creates only a proposed context update; do not accept it automatically.


## Integrated context-cycle planning (SCS-MATURE-014)

Use `scs.context_cycle.plan_context_cycle` when normalized inputs and source-revision observations should be reviewed in one bounded cycle. Use `compose_context_cycle_plan` when a batch already exists, including one returned by `plan_github_observation_batch`.

The coordinator requires the same cycle ID, base commit, and registry version across both plans. It preserves the child plans, sorts proposed work items by their explicitly supplied priority only, and flags an intake context update that overlaps direct/possible impact or stale-state proposals for review before commit. A stale dependency-map baseline blocks direct impact claims. The combined output is always uncommitted with no external actions; it neither applies stale updates nor rewrites accepted history.
