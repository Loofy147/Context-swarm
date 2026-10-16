# Cycle 0003 — integrated bounded-cycle planner

- **Cycle ID:** SCS-CYCLE-0003
- **Base commit:** `625797168fa27efe90e1d1b39828aca7a2636aea`
- **Purpose:** Connect input routing and state-transition preconditions into one reviewable plan without introducing a backend.
- **Status at this revision:** First CI run failed 1 of 43 tests; the failure was a mismatched fixture targeting a task already in progress. The fixture has been corrected to use a ready task and the exact registry snapshot; the follow-up CI result is pending. [Failed run with logs](https://github.com/Loofy147/Context-swarm/actions/runs/38956865056).

## Planned contract

A cycle reads an exact registry snapshot and base commit, consumes one normalized input, validates context/task references, applies intake routing, and returns one bounded proposal or explicit blockers. It never writes state, commits Git, authenticates an operator, or performs external actions.

Supported operations:
- `intake`: propose a new triaged task or a context update.
- `advance_task`: propose a version-checked transition for an existing task.
- `update_context`: propose an evidence-backed update or conflict state.

## Safety behavior

- Exact duplicate source revisions return no-op.
- Inaccessible inputs and consequential actions without separate authorization block before proposals.
- New tasks require explicit title, target context, acceptance criteria, priority rationale and source provenance; they start in `triaged`, never `accepted`.
- Context updates require expected version, evidence, rationale, and an allowed patch set.
- Claims and decisions introduced by proposals are labelled `proposed`, not accepted.
- Invalid registry links, stale versions, illegal transitions and protected patch fields fail closed.
- The output contains `committed=false` and an empty `external_actions` array by design.

## Verification plan

- Run `tests/test_swarm_cycle.py` in the repository's existing CI workflow.
- Validate any generated proposed task against `schemas/work-item.schema.json`.
- Test actionable input, missing acceptance criteria, duplicate revision, inaccessible source, missing authorization, conflict, low-risk update, explicit existing-task transition, stale task version, and dangling registry reference.
- Record the exact commit and CI run before closing `SCS-MATURE-009`.
