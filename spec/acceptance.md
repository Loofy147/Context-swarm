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
- [x] A recent commit-history observation preserves commit URLs, dates, inferred topic categories and page limitations.
- [x] JSON Schema validation checks the current registry, work items, captured input, intake policy and capability matrix.
- [x] Pure context/task transition planning rejects stale versions and invalid transitions and enforces evidence/dependency preconditions before proposing acceptance.
- [x] Current versus future-runtime schema differences are documented in `spec/schema-alignment.md`.
- [x] A capability matrix explicitly separates scoped reads, task-scoped writes and consequential per-action authorization; it does not grant access.
- [x] Nine related repository artifacts were grouped in commit `8f0a4c597a9eef7ba24dd50bcde8fd68a2e6737f`; [the resulting CI run succeeded](https://github.com/Loofy147/Context-swarm/actions/runs/38956067934).

- [x] Integrated bounded-cycle planning combines intake routing, registry reference validation, context/task transition preconditions, and an uncommitted proposal contract; [50 tests passed](https://github.com/Loofy147/Context-swarm/actions/runs/38958604867).
- [x] Each non-duplicate input can produce a schema-valid durable input-record proposal, alongside any task/context proposal.
- [x] Batch processing supports up to 100 inputs and deduplicates exact source revisions against prior records and earlier items in the same batch; [cycle tests passed](https://github.com/Loofy147/Context-swarm/actions/runs/38958604867).
- [x] A source catalog describes repository endpoints and revision strategy; a dated tool-surface snapshot lists 1,098 visible tool definitions while explicitly not claiming resource access.
- [x] The source catalog and tool-surface schemas passed the [CI run 38959142167](https://github.com/Loofy147/Context-swarm/actions/runs/38959142167).
- [x] Pure GitHub adapters normalize repository metadata, commits, issue/PR pages, workflow runs and unavailable-source outcomes into schema-valid intake envelopes.
- [x] A snapshot runner composes these normalizers with the batch planner; the successful path yields a review proposal, while unavailable sources are blocked with no invented claims. [61 tests passed](https://github.com/Loofy147/Context-swarm/actions/runs/38960068848).

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
