# Cycle 0006 — fresh GitHub source ingestion

- **Captured at:** 2026-10-16T20:12:59Z
- **Snapshot ID:** `SRC-GH-2026-10-16-0006`
- **Source base commit:** `de6df318372ed9a009053a23d747f229c4ec2d53`
- **Registry snapshot:** version 9, blob `fe9ee25a07388ba1aeb34fe3a009786d475e6f63`
- **Planner baseline:** [CI run 38960866605 — success](https://github.com/Loofy147/Context-swarm/actions/runs/38960866605), 62 tests.
- **Current record/output equality check:** pending CI for this commit; SCS-MATURE-012 remains in review until it passes.

## Captured sources

1. Repository metadata: [source endpoint](https://api.github.com/repos/Loofy147/Context-swarm).
2. Default branch state: [main](https://api.github.com/repos/Loofy147/Context-swarm/branches/main), head `de6df318372ed9a009053a23d747f229c4ec2d53`; unprotected at capture time.
3. Latest commit: [de6df318](https://github.com/Loofy147/Context-swarm/commit/de6df318372ed9a009053a23d747f229c4ec2d53).
4. Issues/PR endpoint: [state=all&per_page=30](https://api.github.com/repos/Loofy147/Context-swarm/issues?state=all%26per_page=30), zero entries. This applies only to that endpoint/query.
5. Successful CI observation: [run 38960554903](https://github.com/Loofy147/Context-swarm/actions/runs/38960554903).

The reduced source objects and limitations are recorded in `swarm/sources/github-snapshot-cycle-0006.json`. The matching registry fixture is frozen at `tests/fixtures/registry-source-cycle-0006.json` so tests do not combine the historical source response with a later registry version.

## Persisted normalized input records

- `IN-GH-9CEB8EBAC289D661` — repository metadata, informational observation.
- `IN-GH-123373305A1649EF` — latest commit, informational observation.
- `IN-GH-D8938724790ABB3A` — empty issues-page observation, scoped to the query.
- `IN-GH-EA41ECF1DB08739E` — successful Actions run, with intake disposition `propose_reversible_update`; its context claim remains in review.

The runner integration test compares each persisted record field-for-field with the planner's input-record proposal and replays the same snapshot expecting four duplicate no-ops and no new state-change proposals. That acceptance gate remains pending until CI on this exact commit finishes.

## Side-effect boundary

The normalizers consume captured API objects; they do not fetch the network. The runner returns `committed=false` and no external actions. No backend, database, API server, or deployment was introduced.
