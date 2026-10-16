# Backend selection decision record

**Status:** Open — no paid infrastructure until owner approval.  
**Storage requirement:** transactional relational state plus immutable, versioned artifacts.  
**Identity requirement:** dedicated SCS identity/access subsystem; external federation may be added as an adapter.

## Candidate comparison

| Criterion | Managed PostgreSQL (including Supabase) | Other managed/self-managed PostgreSQL | SQLite local-first |
|---|---|---|---|
| Multi-writer transactions | Strong fit | Strong fit | Best for embedded/local prototype; limited service concurrency pattern |
| Operations burden | Usually lower with managed service | Managed varies; self-managed higher | Low for single-node use |
| Portability | SQL core portable; hosted extensions/auth/storage may couple | Higher with standard PostgreSQL; self-managed needs operations expertise | Simple file/database portability |
| Identity | SCS still owns resource authorization; integrate rather than conflate vendor auth | Full control, more implementation/operations | Must implement sessions and permissions around it |
| Background coordination | Good with transactional outbox and worker | Good with transactional outbox and worker | Possible in one process; multi-worker service needs care |
| Backup/restore | Provider-specific objectives/charges; test an actual restore | Depends on provider/operator | Straightforward for prototype, but consistency and recovery procedures still matter |
| Cost | Inspect current plan, region, storage, egress, compute | Inspect provider or operations costs | Low infrastructure cost, with scalability/availability trade-offs |
| Best role | Production candidate for a modest concurrent service | Where portability/control matters | Local prototype or desktop/offline cache |

## Required evidence before selection

1. Deployment target and availability expectation.
2. Data residency and region requirements.
3. Estimated concurrent readers/writers and worker count.
4. Recovery point objective (RPO) and recovery time objective (RTO).
5. Monthly cost ceiling and explicit approval for recurring costs.
6. Who owns patching, monitoring, backup, restore, and incident response.
7. Artifact-store location, retention, and immutability controls.
8. Identity/session model and secret management.
9. Export format, migration path, and exit cost.
10. Successful restore drill on a non-production dataset.

## Provisional recommendation

Keep the data model PostgreSQL-compatible and treat managed PostgreSQL as the leading candidate for the first hosted repository swarm, but make no final provider decision until region, budget, RPO/RTO, operational ownership, and plan costs are evidenced. SQLite can support a local prototype and fast tests; it is not selected as the canonical multi-user production store.
