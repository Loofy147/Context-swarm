> **Operating-model correction — v0.4:** The immediate system is repository-native swarm logic, not a backend-hosted application. The current canonical registry, context states, work queue, intake rules, evidence links, and version history live in Git-tracked repository artifacts. No database, API server, queue service, or deployed identity system is needed to mature the swarm's behavior. Sections below that discuss databases, service APIs, durable workers, or production identity are future-runtime design options and MUST NOT be read as a current implementation prerequisite. The next gate is evidence-backed context/task processing and specification convergence, not backend selection or application construction.

# SCS v0.3 — architecture and implementation specification

Status: design baseline, pre-implementation. Normative terms MUST, MUST NOT, SHOULD, and MAY are requirements. No claim of production readiness is implied.

## 1. Definition and scope

The Swarm Context System (SCS) is a coordinated network of independent, bounded, versioned contexts that maintain specialized knowledge and working state, establish typed relationships, exchange relevant information under policy, and converge on consistent, verifiable outcomes.

The context is the fundamental unit. Agents are optional operators, not required runtime or coordination primitives. People, a single model call, workflows, and services may operate on contexts.

Execution is hybrid: conversational clients read and propose changes against a persistent registry and durable artifacts. Coordination is automatic for policy-eligible, low-risk operations, while authority, conflicts, and consequential changes retain explicit controls.

## 2. First demonstrator

Build a repository engineering swarm with separate contexts for repository inventory, architecture, implementation change, evidence/provenance, verification, and release decision. Demonstrate: source change; dependency invalidation; permitted derived update; incompatible claim conflict; blocked unauthorized release action; and resumption in a fresh conversational session.

## 3. Logical components

1. Conversational/API adapter — stateless interface to durable state.
2. Identity/access subsystem — principals, credentials, sessions, grants, policy decisions, revocation, approvals.
3. Context registry — IDs, types, owners, lifecycle, current version pointers, relationships.
4. Context engine — schemas, canonicalization, immutable versions, lifecycle transitions, compare-and-swap.
5. Evidence/artifact store — content-addressed immutable blobs and origin metadata.
6. Event ledger — application-level append-only events, causal links, replay.
7. Coordination engine — dependency impact analysis, policy filtering, durable staging, idempotent propagation.
8. Governance engine — authorization, approvals, invariants, conflict workflow.
9. Observability/recovery — audit views, snapshots, restore verification, metrics.

Start as a modular monolith using a transactional relational database and durable outbox/worker queue. Split services only when measured scaling, deployment, or isolation requirements justify it.

## 4. Backend decision — intentionally open

Candidate A: managed PostgreSQL, including Supabase. Strengths: transactions, constraints, concurrency controls, mature backup tooling, JSON support, reduced operations burden. Risks: recurring cost, service-specific auth/storage coupling, region/plan limits, and vendor-specific features.

Candidate B: another managed PostgreSQL or self-managed PostgreSQL. Strengths: relational portability and deployment flexibility. Risks: self-managed operations burden or managed-vendor costs and constraints.

Candidate C: SQLite local-first. Strengths: simple setup, embedded operation, fast disposable tests. Risks: weaker fit as canonical storage for a multi-user service with concurrent writers and independent remote workers. Appropriate for a local prototype or client cache, not presumed production source of truth.

Selection gate: decide deployment target, data residency/region, concurrency, RPO/RTO, operational ownership, budget, artifact storage, auth/session requirements, backup/restore method, migration portability, and exit cost. Obtain explicit cost approval before provisioning paid resources. Do not choose a backend in advance of this evidence.

## 5. Dedicated identity and access subsystem

SCS owns principal IDs, grants, roles, sessions, revocation, authorization policy, and approval evidence. External identity federation may be an adapter later; it does not replace SCS resource-level authorization.

Requirements:
- Principal IDs are opaque and stable.
- If passwords are supported, hash with a maintained password-hashing library (Argon2id preferred), never plain SHA-256; do not implement custom cryptography.
- Credentials and secrets MUST NOT be logged or embedded in context documents/artifacts.
- Sessions expire and can be revoked. If refresh tokens are used, rotate them and detect reuse.
- Re-evaluate permissions at commit time, not only when a proposal is created.
- Grants are least-privilege and scope-bound.
- Proposer, approver, and executor are separately recorded; sensitive policies may require separation of duties.
- Administrative recovery is explicit, audited, and tested.
- Deny by default when policy state is absent, stale, or ambiguous.

## 6. Canonical context and version model

Every context has a stable opaque ID and a current committed version pointer. Every committed version is immutable. Proposals/drafts are not current accepted state.

Required fields:
- context_id, context_type, schema_version
- scope: purpose, boundaries, exclusions, invariants
- owner_principal_id and access-policy reference
- lifecycle_status: draft | active | blocked | archived | superseded
- current_version
- typed relationships, evidence references, open issues
- created_at, updated_at
- content digest, algorithm, and canonicalization version

Keep definition, state, evidence, and event history logically separate. A claim can be corrected without deleting the earlier claim or provenance.

## 7. Core invariants

I-01 Identity uniqueness: context_id and event_id are unique and never reused.
I-02 Immutable history: committed versions, artifact bytes, and historical event records are not silently mutated.
I-03 Compare-and-swap: commit succeeds only if expected base version equals the current version.
I-04 Atomic commit: context version, current pointer, event, and outbox item are committed in one database transaction.
I-05 No silent overwrite: stale/conflicting writes fail and preserve the candidate for reconciliation.
I-06 Authorization at commit: current permissions and policy are checked for every mutation at commit time.
I-07 Separation of duties: self-approval is rejected whenever the applicable policy requires independent approval.
I-08 Provenance: accepted claims/decisions link to source artifacts and versions, or explicitly state that evidence is absent.
I-09 Integrity is not truth: a valid digest does not establish factual correctness, authorship, trust, or authority.
I-10 Scoped propagation: only relevant and permitted information crosses an allowed boundary; never broadcast implicitly to all contexts.
I-11 Idempotency: retrying a request/job/event does not repeat the committed effect.
I-12 Causality: event links record causation/correlation; wall-clock timestamps alone do not establish causal order.
I-13 Conflict preservation: incompatible claims stay visible with evidence and status; no silent winner.
I-14 Dependency freshness: source changes invalidate materially affected verification/derived status until revalidated.
I-15 External-action gate: external side effects require a separate current authorization check; context contents cannot grant authority.
I-16 Secret exclusion: credentials, tokens, private keys, and secrets are excluded from context state, artifacts, and ordinary logs.
I-17 Deterministic restore: the same accepted event prefix, snapshot, and canonicalization version reconstruct the same canonical state.
I-18 Resource isolation: context reads, relationships, artifacts, and event history are individually authorized.
I-19 Schema evolution: every version declares schema; unsupported schemas fail closed.
I-20 Append-only audit: corrections are new versions/events, not rewrites of history.

## 8. Typed relationship semantics

- parent_of: organizational containment.
- depends_on: source evaluation depends on target state.
- references: citation only; no implied authority or dependency.
- derived_from: output produced from specific source versions.
- conflicts_with: unresolved incompatibility.
- supersedes: accepted replacement for a defined purpose.
- shares_with: governed information-exchange relationship.

Relationships do not grant access by themselves. Reference cycles are allowed. Dependency cycles that prevent evaluation must be detected and blocked or explicitly handled by a documented cycle strategy.

## 9. Lifecycle and validation

Draft -> active only after schema, owner, policy, and initial-state validation.
Active -> blocked on a blocking conflict or unmet mandatory dependency.
Blocked -> active only after resolution and revalidation.
Active -> archived by authorized retirement.
Active -> superseded only after an authorized replacement is accepted.
Archived -> active only by authorized reactivation.

No transition deletes history. Track integrity_valid, evidence_valid, dependencies_current, and policy_compliant independently; do not collapse these dimensions into one boolean.

## 10. Coordination and risk classes

For every propagation job record source context/version, target context/base version, selected payload or artifact refs, relevance rule, access-policy version, validation result, idempotency key, and outcome.

Class A — automatic and reversible: refresh derived indexes, update dependency freshness, add permitted references, generate clearly non-authoritative summaries, queue revalidation.

Class B — staged or approval-controlled: promote decisions, merge versions, change accepted requirements, change ownership/access, resolve disputed evidence.

Class C — explicit authorization required: publish a release, delete a protected artifact, change access controls, or execute a financial/operational transaction.

Classification depends on action and consequences, not on the proposing context. Validation does not itself authorize an external action.

## 11. Consistency model

Strong transactional consistency for current-version pointers, grants, approval records, and accepted decisions. Eventual consistency for search indexes and non-authoritative derived views. Explicit reconciliation for conflicting facts and semantic decisions. Outbox consumers are at-least-once; handlers must be idempotent.

## 12. Canonicalization and artifact integrity

Before implementation freeze canonical JSON test vectors: UTF-8, deterministic object-key ordering, no insignificant whitespace, documented Unicode normalization, numeric restrictions, and UTC RFC 3339 timestamps. Use SHA-256 over canonical bytes; store algorithm and canonicalization version with digest.

The relational database holds metadata, references, and small canonical state. Store larger immutable artifacts by content digest using write-once storage policy or content-addressed keys. Store digest, length, media type, schema/canonicalization version, origin, verification status, and creation metadata. A boolean DB column alone does not enforce artifact immutability.

## 13. API principles

- Version path: /v1.
- JSON requests/responses and UTC RFC 3339 times.
- Auth uses revocable credentials managed by the identity subsystem; final bearer/session format is a deployment choice.
- Mutations accept Idempotency-Key when retries could duplicate effects.
- Optimistic concurrency uses expected_version; stale updates return 409.
- Error codes: 401 unauthenticated; 403 unauthorized; 404 absent or intentionally concealed; 409 stale/conflict; 422 schema/invariant error; 429 rate limit.
- Errors contain stable code, safe message, and request_id; no secrets or protected details.
- External side effects begin as approval-gated proposals; no unguarded external-action endpoint in MVP.

Core operations: create_context, get_context, list_contexts, propose_change, validate_change, commit_change, link_contexts, coordinate_changes, resolve_conflict, get_event_history, restore_snapshot, request_approval.

## 14. Migration plan

M0 Decision record: deployment target, budget, region, RPO/RTO, concurrency, retention, auth/session requirements, artifact-store candidates, and exit criteria. No paid resource before approval.
M1 Contract freeze: version schemas, canonicalization vectors, OpenAPI, invariants, threat model, test vectors.
M2 Persistence prototype: apply migration only to disposable dev DB; test constraints, transaction boundaries, backup, and restore.
M3 Identity: implement principals, safe credential/session management, grants, revocation, deny-by-default authorization.
M4 Context engine: CRUD, proposal/commit, immutable versions, compare-and-swap, atomic event/outbox write.
M5 Artifact store: content-addressed immutable writes, metadata, digest verification, retention/restore policy.
M6 Coordination: durable outbox worker, idempotency, dependency graph impact, staged propagation, conflict queue.
M7 Repository demonstrator: import repo metadata as untrusted evidence; build inventory, architecture, implementation, evidence, verification, release contexts.
M8 Hardening: concurrency/load, authorization-negative, replay/restore, secret scanning, dependency audit, observability.
M9 Pilot: only after gates pass; no repository mutation or external release without explicit approval.

Use expand/migrate/contract for schema evolution. Destructive migration steps require backup, verified restore, and separate approval. Never assume a downgrade can recover deleted data.

## 15. Release gates

G1 schema and canonicalization vectors approved.
G2 migration succeeds in disposable DB and constraints are tested.
G3 authorization tests prove deny-by-default and resource isolation.
G4 concurrent writes show no lost update.
G5 event/outbox transactionality and idempotent replay verified.
G6 artifact tamper detection and restore verified.
G7 conflicts and dependency invalidation verified.
G8 external side effects blocked without separate authorization.
G9 repository swarm resumes in a fresh session from persistent state.
G10 backup/restore and incident recovery procedure tested.

Report each gate PASS only with reproducible test evidence; otherwise FAIL or BLOCKED with reasons.
