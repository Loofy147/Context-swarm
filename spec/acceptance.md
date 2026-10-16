# SCS acceptance criteria

Every item must be marked PASS only with reproducible output and linked evidence. An unchecked item is not complete.

## Context and concurrency
- [ ] Stable context IDs persist across service restarts.
- [ ] Committed versions cannot be mutated through normal application interfaces.
- [ ] Stale compare-and-swap write returns conflict and does not overwrite accepted state.
- [ ] Version pointer, event, and outbox item commit atomically.
- [ ] Replaying the same idempotency key does not duplicate effects.

## Authority and isolation
- [ ] Unauthenticated and unauthorized operations fail closed.
- [ ] Reads, relationships, artifacts, and event history each enforce resource scope.
- [ ] Permissions are re-evaluated at commit time.
- [ ] Proposer cannot self-approve when separation of duties applies.
- [ ] External side effects remain blocked without distinct current authorization and required approval.
- [ ] Secret values do not appear in contexts, artifacts, or ordinary logs.

## Evidence, conflicts, and propagation
- [ ] Claims and decisions preserve source references and versions.
- [ ] Incompatible claims remain visible and create a conflict record.
- [ ] Source changes mark affected dependent verification/derived status stale.
- [ ] Propagation crosses only explicitly allowed, relevant relationships.
- [ ] Policy version, source and target versions, and outcome are recorded for every propagation job.

## Integrity and recovery
- [ ] Canonicalization test vectors produce stable SHA-256 digests.
- [ ] Artifact corruption is detected.
- [ ] Event replay reconstructs canonical state for a fixed accepted prefix.
- [ ] Backup can be restored within declared RPO/RTO.
- [ ] Fresh conversation resumes from persistent registry without prior transcript.

## Repository engineering demonstrator
- [ ] Inventory, architecture, implementation, evidence, verification, and release contexts exist.
- [ ] A source update produces a targeted impact analysis.
- [ ] Eligible reversible update propagates automatically.
- [ ] Contradictory evidence is preserved and blocks affected decision.
- [ ] Release operation is blocked until authorization requirements are satisfied.

## Release gates
G1 schema and canonicalization vectors approved.
G2 schema migration succeeds in disposable DB and constraints are tested.
G3 deny-by-default and resource isolation proven.
G4 concurrent writes produce no lost update.
G5 outbox transactionality and idempotent replay proven.
G6 artifact integrity and restore proven.
G7 conflict handling and dependency invalidation proven.
G8 unauthorized external action proven blocked.
G9 new-session recovery proven.
G10 backup and incident recovery tested.
