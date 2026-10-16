# Cycle 0005 — pure GitHub source adapters and snapshot runner

- **Base commit:** `29d61ddce497bc8c1c814fa9a938a1e2b7b2e71b`
- **Implementation:** `src/scs/adapters/github.py`, `src/scs/runner.py`, `schemas/intake-envelope.schema.json`.
- **CI evidence:** [run 38960068848 — success](https://github.com/Loofy147/Context-swarm/actions/runs/38960068848), 61 tests.
- **Mode:** repository-native, pure, and side-effect-free.

## Added behavior

- Pure normalizers for repository metadata, commit objects, issues/PRs, issue-page results, workflow runs and unavailable sources.
- A common normalized intake envelope carrying stable source identity, revision, source locator, observed date, capture actor, access boundary, trust status, normalized claims and evidence references.
- A snapshot runner that composes these normalizers with `plan_batch`.
- An observed empty issues page becomes a scoped observation, not a global claim that there are no tasks.
- Missing responses become blocked input proposals with zero invented claims.
- A completed successful workflow may propose a review-state context claim with its exact run URL and head SHA; it is not accepted automatically.
- An issue body remains untrusted data; only bullets beneath an explicit Acceptance Criteria/Definition of Done heading become proposed criteria.

## Evidence boundary

The 61-test run validates adapters and planner behavior against captured real-shaped API fixtures. The fixture's synthetic issue is labelled test-only. The pure adapter does not fetch sources and the runner does not commit state.

## Next

`SCS-MATURE-012`: capture a fresh scoped GitHub snapshot through authorized tools, run it through the pure runner, validate proposed input records, replay the source revisions to test deduplication, then commit the accepted records and cycle report. Do not auto-accept context updates or trigger external actions.
