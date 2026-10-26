# Cycle 0007 — source revision impact planning

- **Status:** Reopened for baseline regression repair
- **Date:** 2026-10-26
- **Work item:** `SCS-MATURE-013`
- **Merged implementation:** [f90d0644](https://github.com/Loofy147/Context-swarm/commit/f90d064455bab412e43763fbacd40be60128f0f9)
- **Implementation PR:** [#1 — merged](https://github.com/Loofy147/Context-swarm/pull/1)
- **Candidate CI before merge:** [Run 40398482504 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398482504), 73 tests.
- **Post-merge main CI before evidence refresh:** [Run 40398648552 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398648552), 73 tests.
- **Regression evidence:** [Run 40399177569 — failure](https://github.com/Loofy147/Context-swarm/actions/runs/40399177569), three impact tests failed after dependency-map v12 moved its reviewed base to f90d064 while the test helper stayed fixed at e73d521.

## Delivered implementation

1. `src/scs/impact.py` compares stable source IDs and previous/current revisions and returns deterministic, side-effect-free impact proposals.
2. `schemas/impact-plan.schema.json` defines baseline metadata, source comparisons, deduplicated direct/possible impacts, stale proposals, blockers, `committed: false`, and `external_actions: []`.
3. `tests/test_swarm_impact.py` covers replay, revisions, fan-out, deduplication, uncertain edges, stale-map behavior, claim proposals, missing mapping, malformed identity/revision, dangling context relationships and schema validation.
4. A final evidence refresh exposed three test failures caused by a hard-coded test baseline, not by the intended conservative planner behavior.

## Regression and remediation

- [x] Diagnosis traced to test baseline mismatch.
- [x] Test helper now defaults to `dependency_map.reviewed_base_commit`.
- [x] Stale-map test supplies the older base explicitly.
- [x] Dependency-map v13 reviews exact repair baseline `f684b10baef778824ae1c2f7f9f520075128a2aa`.
- [ ] Follow-up candidate CI must pass before re-acceptance.
- [ ] Merge fix PR and refresh evidence against the merged tree.

## Safety and scope

The planner emits proposals only, preserves accepted history, and never performs persistence or external actions. Semantic, unknown, or stale-map edges remain possible impacts. Source revision values, mapped paths, and evidence are supplied by the caller; automatic backend/persistence integration remains deferred.
