# Cycle 0007 — source revision impact planning

- **Status:** Accepted
- **Date:** 2026-10-26
- **Work item:** `SCS-MATURE-013`
- **Implementation base:** [e73d521e](https://github.com/Loofy147/Context-swarm/commit/e73d521e8d246691888d656419457d5b0eedd055)
- **Implementation merge:** [f90d0644](https://github.com/Loofy147/Context-swarm/commit/f90d064455bab412e43763fbacd40be60128f0f9)
- **Implementation PR:** [#1 — merged](https://github.com/Loofy147/Context-swarm/pull/1)
- **Candidate CI:** [Run 40398482504 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398482504), 73 tests.
- **Post-merge CI:** [Run 40398648552 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398648552), 73 tests.
- **Baseline regression:** [Run 40399177569 — failed](https://github.com/Loofy147/Context-swarm/actions/runs/40399177569), three impact tests failed after evidence refresh changed the graph's reviewed base while tests still used the old fixed base.
- **First repair:** commit [d1e07518](https://github.com/Loofy147/Context-swarm/commit/d1e0751851c548c4cefdaad5b90484dfa051b0f7) aligned the fixed test base with map v12; [run 40399818363](https://github.com/Loofy147/Context-swarm/actions/runs/40399818363) passed 73 tests.
- **Robust repair:** commit [ef73b8a1](https://github.com/Loofy147/Context-swarm/commit/ef73b8a1712697525d20f934083fa55a619186d6) made the test helper default to `dependency_map.reviewed_base_commit` and made the stale-map test pass an older base explicitly. [Run 40400844325 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40400844325), 73 tests.
- **Metadata verification:** dependency-map and inventory refreshes also passed CI: [run 40400918044](https://github.com/Loofy147/Context-swarm/actions/runs/40400918044) and [run 40400955054](https://github.com/Loofy147/Context-swarm/actions/runs/40400955054).

## Scope delivered

1. Added `src/scs/impact.py`: deterministic source-revision comparison using stable source identity, known prior/current revisions, repository-relative artifact paths and evidence references.
2. Added `schemas/impact-plan.schema.json`: output contract includes baseline metadata, source comparisons, deduplicated direct/possible impacts, stale-state proposals, blockers, `committed: false` and `external_actions: []`.
3. Added `tests/test_swarm_impact.py`: tests unchanged replay, changed revisions, dependency fan-out, multi-source deduplication, semantic-edge uncertainty, stale-map handling, stale-claim proposals, missing mapping, malformed/duplicate source observations, dangling context relationships and JSON Schema validation.
4. Documented the contract in `spec/schema-alignment.md` and `README.md`; reconciled dependency-map v13 and inventory v10 to source/test baseline `ef73b8a1712697525d20f934083fa55a619186d6`.

## State and safety semantics

The planner proposes consequences; it does not mutate the supplied registry, write files, persist results or execute external actions. Proposed stale transitions retain base/result versions and use existing transition preconditions. Accepted history is preserved. A verified/accepted claim is proposed stale only where its own evidence intersects changed/affected paths. Explicit high-confidence dependencies are direct only when the graph snapshot is fresh against the supplied base; semantic, unknown or stale-map relationships remain possible impacts.

## Acceptance

- [x] Pure deterministic planner and dedicated schema merged.
- [x] No-change replay, revision change, graph fan-out, multi-source deduplication and ambiguous dependency cases tested.
- [x] Dangling context relationships rejected.
- [x] Candidate and post-merge CI passed 73 tests.
- [x] Baseline regression diagnosed, repaired and verified with map-driven test baseline.
- [x] SCS-MATURE-013 accepted in registry v15.
- [x] Runtime/backend integration remains deferred: no automatic source polling, persistence or automatic application of stale-state proposals.
