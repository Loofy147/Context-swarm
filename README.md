# Swarm Context System (SCS)

**Specification baseline:** v0.3  
**Status:** Pre-implementation; this repository is being initialized from the reviewed design package.  
**Primary unit:** Context, not agent.  
**First demonstrator:** Repository engineering swarm.  
**Backend:** Deliberately undecided pending an operational comparison.  
**Identity:** Dedicated identity and access subsystem.  
**Artifact storage:** Transactional database plus immutable, versioned artifacts.

## Definition

The Swarm Context System is a coordinated network of independent, bounded, versioned contexts that maintain specialized knowledge and working state, establish typed relationships, exchange relevant information under policy, and converge on consistent, verifiable outcomes.

Conversational clients are interfaces to persistent state, not the source of truth. Agents are optional operators; they are not a fundamental unit of the system.

## Repository map

- `spec/architecture.md` — normative architecture, invariants, trust boundaries, consistency, and migration/release gates.
- `spec/openapi.yaml` — initial HTTP API contract.
- `schemas/context.schema.json` — context envelope schema.
- `schemas/event.schema.json` — event envelope schema.
- `migrations/001_initial_postgres.sql` — PostgreSQL reference migration; not applied or production-certified.
- `src/scs/reference_model.py` — dependency-free reference semantics for versioning and authorization gates.
- `tests/` — executable reference-model and contract-artifact tests.

## Current status

This repository starts from the SCS v0.3 pre-implementation specification. Files here are design artifacts and reference code, not evidence of a deployed service. The included reference tests, where present, must be run in CI and their exact results recorded. A database migration, HTTP server, identity subsystem, durable artifact store, and coordination worker are not considered implemented until built and tested.

## Backend decision gate

Compare managed PostgreSQL (including Supabase), another managed/self-managed PostgreSQL option, and SQLite local-first against: deployment target, data residency, concurrency, RPO/RTO, monthly budget, operational ownership, backup/restore, identity/session requirements, artifact-store integration, portability, and exit cost. Do not provision a paid service until the owner approves the cost and region.

## Security boundary

- Context data is not authorization.
- Content integrity is not proof of factual truth or source authenticity.
- Consequential external actions require a separate, current authorization check.
- Do not store passwords, tokens, private keys, or secrets in context content, artifacts, or ordinary logs.
- Committed versions and events must not be silently rewritten; corrections are new events/versions.

## Running reference tests

Requires Python 3.10+ and no third-party dependencies:

```bash
python -m unittest discover -s tests -v
```

Passing reference tests do not imply that the full system is implemented, deployed, or integration-tested.
