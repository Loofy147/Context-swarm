# Cycle 0007 — source revision impact planning

- **Status:** Accepted
- **Date:** 2026-10-26
- **Work item:** `SCS-MATURE-013`
- **Base commit:** [e73d521e](https://github.com/Loofy147/Context-swarm/commit/e73d521e8d246691888d656419457d5b0eedd055)
- **Merged main commit:** [f90d0644](https://github.com/Loofy147/Context-swarm/commit/f90d064455bab412e43763fbacd40be60128f0f9)
- **Pull request:** [#1 — Implement deterministic source revision impact planning](https://github.com/Loofy147/Context-swarm/pull/1) — merged
- **Candidate CI:** [Run 40398482504 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398482504), 73 tests passed.
- **Post-merge main CI:** [Run 40398648552 — success](https://github.com/Loofy147/Context-swarm/actions/runs/40398648552), 73 tests passed.

## Scope delivered

1. Added `src/scs/impact.py`, a deterministic, pure comparison of stable source IDs and previous/current revisions with repository-relative artifact references and evidence.
2. Added `schemas/impact-plan.schema.json`. A plan includes base commit and registry/map versions, source comparison results, deduplicated direct and possible impacts, stale-state proposals, blockers, and explicit `committed: false` / `external_actions: []`.
3. Added `tests/test_swarm_impact.py`, including no-change replay, changed revision, fan-out, multi-source deduplication, semantic dependency uncertainty, stale map metadata, stale claim proposals, missing source-path mapping, duplicate/malformed source observations, dangling context relationships, and JSON Schema validation.
4. Refreshed `swarm/dependency-map.json` to v12 against the exact merged tree. High-confidence edges with explicit code/test/schema/workflow bases are direct only when the input base matches the map baseline. Semantic, documentation-only, unknown, or stale-map edges remain possible impact.
5. Updated schema alignment, README, repository inventory and registry evidence.

## State and safety semantics

The planner proposes consequences and does not mutate the supplied registry, write files, persist outputs or execute external actions. It preserves accepted history and emits versioned context-stale proposals through the existing transition reference logic. A verified/accepted claim is proposed stale only if its own evidence intersects changed/affected paths. Uncertain relationships are not asserted as direct dependencies. The source observation caller must provide stable identity, prior/current revisions, mapped artifact paths and evidence; automatic persistence/backend integration remains deferred in the repository-native phase.

## Acceptance evidence

- [x] Implementation and dedicated output schema merged.
- [x] Dependency graph and context IDs validated; dangling context relationship rejected.
- [x] No-change replay, changed revision, graph fan-out, multi-source deduplication and ambiguous dependency cases tested.
- [x] Candidate CI passed 73 tests (run 40398482504).
- [x] Post-merge main CI passed 73 tests (run 40398648552).
- [x] PR #1 merged as commit f90d064455bab412e43763fbacd40be60128f0f9.
- [x] Registry SCS-MATURE-013 accepted and evidence inventory/dependency map refreshed.

## Remaining boundary

This is repository-native reference logic, not a deployed runtime. It does not fetch source systems itself, automatically run on new commits, persist its plans, or apply proposed stale transitions. Those require a separately scoped caller/runtime and its own authorization, persistence, and verification design.
