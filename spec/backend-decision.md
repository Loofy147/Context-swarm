# Backend decision — deferred by design

**Status:** Deferred. No backend is required for the current repository-native swarm-maturation phase. Do not provision infrastructure as part of the current milestone.

## Current operating model

The committed Git repository is the canonical store for the registry, context states, task records, workflow/intake policy, specifications, evidence pointers, and version history. Tool calls and conversations are operators/interfaces over those records. Changes are proposed, reviewed against rules and evidence, and recorded as commits.

The system should populate and improve its domain data, rules, contexts, test vectors, workflows, and implementation specification before selecting or implementing a production runtime.

## Future backend evaluation — not an active task

Only after a stable implementation contract and measurable operational requirements exist, evaluate:
- managed PostgreSQL (including Supabase);
- another managed or self-managed PostgreSQL option;
- SQLite for local-first/single-user deployments;
- repository/object-artifact storage and other options only if requirements justify them.

Future selection criteria: hosting and availability needs, data residency, concurrency, recovery point/time objectives, budget, operational ownership, artifact retention/immutability, identity/session requirements, portability, and exit cost. Any recurring cost requires explicit owner approval.

This document records a deferred decision, not a recommendation to provision any candidate.
