# SCS schema alignment record

**Status:** Current repository-native contracts are identified. Future runtime envelopes remain separate pending more representative use cases.

## Canonical contract set now

| Record | Canonical file | Used for |
|---|---|---|
| Repository registry | `swarm/registry.json` validated by `schemas/registry.schema.json` | Current context summaries, task queue, relationships, source references, and current state pointers |
| Context state | `schemas/context-state.schema.json` | Individual context-state record stored in the repository registry |
| Work item | `schemas/work-item.schema.json` | Versioned task state, dependencies, acceptance criteria, evidence, and work history |
| Captured input | `schemas/input-record.schema.json` | Normalized source/requirement record with origin, trust, access boundary, claims, disposition, and links |
| Intake policy | `swarm/intake-policy.json` validated by `schemas/intake-policy.schema.json` | Allowed source kinds, intake order, duplicate strategy, routing dispositions, and safety gates |
| Evidence snapshot | `swarm/sources/*.json` | Source-backed repository observations with date, source locator, claims, and limitations |
| Cycle record | `swarm/cycles/*.md` | Human-auditable account of a bounded processing cycle |
| Context impact plan | `schemas/impact-plan.schema.json` | Deterministic proposed impacts, dependency confidence, stale-state proposals, evidence, blockers, and no-side-effect guarantees |

These are the contracts used in the repository-native maturation phase. CI validates the schemas and the canonical registry, intake policy, and captured input against them.

## Shared concepts with future runtime envelope

The repository-native context state and the future envelope both use context identity, type, scope/purpose, lifecycle, version, relationships, evidence references, and open issues. Those concepts are the likely stable core.

## Differences that should not be erased prematurely

| Concern | Repository-native state | Future runtime envelope |
|---|---|---|
| Version pointer | `version` on each context record | `current_version` plus immutable version rows |
| Record owner | Git contributor and repository ownership/audit are currently the practical provenance | Explicit `owner_principal_id` and resource grants |
| Content integrity | Git blob/commit identity is available for tracked files; data files do not all carry a separate content digest | Explicit canonical digest and canonicalization version |
| Event history | Git commit history plus cycle records and source observations | Structured application event log with causation/correlation |
| Proposals | Work-item status and a proposed change in the cycle's working output; not a separate persistent API resource | Explicit proposal entity and compare-and-swap commit contract |
| Authorization | Repository and connected-tool capabilities, plus explicit procedural review; branch protection is currently not configured | Dedicated SCS principal/session/grant/policy subsystem with commit-time enforcement |
| Persistence | Git-tracked files and repository history | Transactional database plus immutable artifact storage |

The future `schemas/context.schema.json` and `schemas/event.schema.json`, `spec/openapi.yaml`, and `migrations/001_initial_postgres.sql` are reference-only and deferred. Do not apply a migration, deploy an API, or provision a backend as part of this phase.

## Current limitations and decisions

1. The context records in `swarm/registry.json` are summaries, not a full replacement for detailed context dossiers.
2. The current state store does not enforce per-context ACLs. GitHub and connected integrations enforce their own permissions; SCS policy remains a workflow contract until a runtime implements it.
3. The repository's `main` branch is unprotected. A procedural approval described in a file does not equal a server-enforced permission control.
4. Git history records accepted repository changes but does not independently record every read or every rejected input. Input/cycle records must preserve those dispositions when they matter.
5. Content digests and Git object IDs establish integrity of bytes/history, not truth, authorship identity beyond the host's claims, or authorization.


## Context impact planning (SCS-MATURE-013)

The pure planner in `src/scs/impact.py` compares a stable source identity's previous and current revision, then walks the repository dependency map backward from changed artifacts. It treats only high-confidence edges with an explicit basis as direct, and only when the map's reviewed base commit exactly matches the plan's base commit. Semantic, uncertain, or stale-map edges are retained as possible impacts and cannot independently drive stale-state proposals.

Context relationships are evaluated separately from file edges. Directly affected active/accepted contexts receive versioned proposals to move to stale using the existing transition reference logic. Verified/accepted claims are proposed stale only when their own evidence references intersect changed/affected paths. The plan is deterministic, schema-validated in tests, uncommitted, and has no external actions; it never rewrites accepted history.


## Decision

Keep repository-native and future-runtime schemas separate while the state machine, intake fixtures, and real repository examples mature. Use test failures and concrete field gaps to justify consolidation. A future adapter may map the stable common concepts without forcing a single storage representation.

Revisit this record when a schema migration or new use case exposes a real contract conflict—not just because two schemas describe related concepts.
