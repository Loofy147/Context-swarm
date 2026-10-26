# Cycle 0007 — source revision impact planning

- **Status:** Accepted
- **Date:** 2026-10-26
- **Work item:** `SCS-MATURE-013`
- **Implementation base:** [e73d521e](https://github.com/Loofy147/Context-swarm/commit/e73d521e8d246691888d656419457d5b0eedd055)
- **Implementation merge:** [f90d0644](https://github.com/Loofy147/Context-swarm/commit/f90d064455bab412e43763fbacd40be60128f0f9)
- **Implementation PR:** [#1 — merged](https://github.com/Loofy147/Context-swarm/pull/1)
- **Candidate CI:** [Run 40398482504 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398482504), 73 tests passed.
- **Post-merge CI:** [Run 40398648552 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398648552), 73 tests passed.
- **Regression found during evidence refresh:** [Run 40399177569 — failed](https://github.com/Loofy147/Context-swarm/actions/runs/40399177569), three impact tests failed because the helper retained an old hard-coded baseline after the dependency map's reviewed base had advanced.
- **Regression fix:** [Commit d1e07518](https://github.com/Loofy147/Context-swarm/commit/d1e0751851c548c4cefdaad5b90484dfa051b0f7) makes the test helper use `dependency_map.reviewed_base_commit` by default and keeps an explicit older baseline in the stale-map test. [Run 40399818363 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40399818363), 73 tests passed.
- **Registry evidence refresh:** [Commit 25a4e7e4](https://github.com/Loofy147/Context-swarm/commit/25a4e7e48e54786143485c243f2ec31ebf9cd2c3); its main CI run [40400352055 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40400352055).

## Scope delivered

1. Added `src/scs/impact.py`: deterministic source-revision comparison using stable source identity, known prior/current revisions, repository-relative artifact paths, and evidence references.
2. Added `schemas/impact-plan.schema.json`: output contract includes baseline metadata, source comparisons, deduplicated direct/possible impacts, stale-state proposals, blockers, `committed: false`, and `external_actions: []`.
3. Added `tests/test_swarm_impact.py`: covers unchanged replay, changed revisions, fan-out, multi-source deduplication, semantic-edge uncertainty, stale-map handling, stale-claim proposals, missing path mapping, malformed/duplicate source observations, dangling context relationships, and JSON Schema validation.
4. Refreshed dependency evidence and documented the output contract in `spec/schema-alignment.md` and `README.md`.

## State and safety semantics

The planner proposes consequences; it does not mutate the supplied registry, write files, persist results, or execute external actions. Proposed stale transitions retain base/result versions and use the existing transition preconditions. Accepted history is preserved. A verified/accepted claim is proposed stale only where its own evidence intersects changed/affected paths. Explicit high-confidence dependencies are direct only when the graph snapshot is fresh against the supplied base; semantic, unknown, or stale-map relationships remain possible impacts.

## Acceptance

- [x] Pure deterministic planner and dedicated schema merged.
- [x] No-change replay, revision change, graph fan-out, multi-source deduplication and ambiguous dependency cases tested.
- [x] Dangling context relationships rejected.
- [x] Candidate and post-merge CI passed 73 tests.
- [x] Baseline regression found, corrected and verified with 73 passing tests.
- [x] SCS-MATURE-013 accepted in registry v14.
- [x] Runtime/backend integration explicitly remains deferred: no automatic source polling, persistence, or automatic application of stale-state proposals.
