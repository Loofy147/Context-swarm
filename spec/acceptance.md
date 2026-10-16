# SCS acceptance criteria

**Current phase:** repository-native swarm maturation. No backend, database, API server, or deployment is required for this phase.

The runtime criteria below are future implementation gates. They are not blockers to improving repository-native context states now, and they must not be represented as passed until the runtime exists and evidence is recorded.

## Current repository-native acceptance

- [x] Intake rules are explicit and represented in `swarm/intake-policy.json`.
- [x] The repository has a durable context registry and work queue in `swarm/registry.json`.
- [x] User direction is captured as a normalized input record in `swarm/inputs/IN-SCS-0001-operating-phase.json`.
- [x] Replayable cases cover actionable input, exact duplicate, contradictory claims, inaccessible source, untrusted embedded instructions, verified low-risk updates, and a consequential action lacking approval.
- [x] Deterministic reference router returns expected dispositions for those scenarios.
- [x] Registry context relationships and work-item dependency references are checked for dangling references.
- [x] GitHub Actions succeeded for commit `481fe14acada05c55cf08166c895c4440725f359`: [workflow run](https://github.com/Loofy147/Context-swarm/actions/runs/38954032510).
- [x] An evidence-backed repository inventory records file roles, blob identities at its reviewed commit, deferred artifacts, and alignment findings.
- [x] Current GitHub repository metadata was captured with source locators and explicit limitations.

These checks verify the repository-native reference logic and captured state. They do not establish autonomous continuous execution, durable runtime storage, authentication, external-action enforcement by a deployed service, or production readiness.

## Future runtime gates — not yet executed

Every item must be marked PASS only with reproducible output and linked evidence. An unchecked item is not complete.

### Context and concurrency
- [ ] Stable context IDs persist across service restarts.
- [ ] Committed versions cannot be mutated through normal application interfaces.
- [ ] Stale compare-and-swap write returns conflict and does not overwrite accepted state.
- [ ] Version pointer, event, and outbox item commit atomically.
- [ ] Replaying the same idempotency key does not duplicate effects.

### Authority and isolation
- [ ] Unauthenticated and unauthorized operations fail closed.
- [ ] Reads, relationships, artifacts, and event history each enforce resource scope.
- [ ] Permissions are re-evaluated at commit time.
- [ ] Proposer cannot self-approve when separation of duties applies.
- [ ] External side effects remain blocked without distinct current authorization and required approval.
- [ ] Secret values do not appear in contexts, artifacts, or ordinary logs.

### Evidence, conflicts, and propagation
- [ ] Claims and decisions preserve source references and versions.
- [ ] Incompatible claims remain visible and create a conflict record.
- [ ] Source changes mark affected dependent verification/derived status stale.
- [ ] Propagation crosses only explicitly allowed, relevant relationships.
- [ ] Policy version, source and target versions, and outcome are recorded for every propagation job.

### Integrity and recovery
- [ ] Canonicalization test vectors produce stable SHA-256 digests.
- [ ] Artifact corruption is detected.
- [ ] Event replay reconstructs canonical state for a fixed accepted prefix.
- [ ] Backup can be restored within declared RPO/RTO.
- [ ] Fresh conversation resumes from persistent registry without prior transcript.

### Repository engineering demonstrator
- [ ] Inventory, architecture, implementation, evidence, verification, and release contexts exist in the agreed form.
- [ ] A source update produces a targeted impact analysis.
- [ ] Eligible reversible update propagates automatically under a running implementation.
- [ ] Contradictory evidence is preserved and blocks affected decision.
- [ ] Release operation is blocked until authorization requirements are satisfied by the runtime.

### Release gates
G1 schema and canonicalization vectors approved.
G2 schema migration succeeds in disposable DB and constraints are tested.
G3 deny-by-default and resource isolation proven.
G4 concurrent writes produce no lost update.
G5 outbox transactionality and idempotent replay proven.
G6 artifact integrity and restore proven.
G7 conflict handling and dependency invalidation verified.
G8 unauthorized external action proven blocked.
G9 new-session recovery proven.
G10 backup/restore and incident recovery procedure tested.
