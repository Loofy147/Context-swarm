# Swarm Context System (SCS)

**Operating phase:** Repository-native swarm maturation (no application backend required).  
**Specification baseline:** v0.4 operating model.  
**Primary unit:** Context state, not agent.  
**First demonstrator:** Repository engineering swarm.  
**Canonical working store for this phase:** Versioned files and Git history in this repository.  
**Production backend:** Explicitly out of scope until the swarm's data, workflows, specifications, and acceptance evidence mature.

## Definition

The Swarm Context System is a coordinated network of independent, bounded, versioned contexts that maintain specialized knowledge and working state, establish typed relationships, exchange relevant information under rules, and converge on consistent, verifiable outcomes.

The swarm is primarily a state-and-transition system. It consumes data and task events, preserves source and provenance, classifies and links inputs, creates or updates context states, evaluates dependencies and contradictions, proposes changes, validates them, and commits accepted state changes. Agents are not the fundamental unit.

## How work happens now

1. New inputs are captured as source records with origin, revision/time, digest when available, trust status, and access boundary.
2. Inputs are normalized without discarding the original source pointer, classified, deduplicated, and linked to affected contexts.
3. The intake policy either creates a work item, updates an existing one, requests evidence, or marks a conflict. It must not silently discard an input.
4. The swarm processes work against explicit context versions and invariants. Each result is a proposal with evidence and expected base version.
5. Validation checks scope, evidence, dependencies, contradictions, schema, and authorization.
6. An accepted change updates the relevant repository records through a versioned Git commit. High-consequence external actions remain separately gated.
7. Later inputs can stale, challenge, supersede, or improve earlier versions without erasing history.

The protocol is specified in [spec/swarm-operating-model.md](spec/swarm-operating-model.md), with an operator-facing [cycle runbook](swarm/CYCLE.md). The integrated pure planner is [src/scs/cycle.py](src/scs/cycle.py): it proposes input capture and task/context outcomes without committing state or triggering external actions. Source revision impact is handled by [src/scs/impact.py](src/scs/impact.py), which compares stable source revisions and returns schema-valid direct/possible impact and proposed stale-state updates using [schemas/impact-plan.schema.json](schemas/impact-plan.schema.json); it does not commit or execute those proposals. Known source endpoints are cataloged in [swarm/source-catalog.json](swarm/source-catalog.json); the session-bound exposed tool surface is recorded in [swarm/sources/connected-tool-surface.json](swarm/sources/connected-tool-surface.json). Current state is in [swarm/registry.json](swarm/registry.json), intake rules in [swarm/intake-policy.json](swarm/intake-policy.json), capability boundaries in [swarm/capability-matrix.json](swarm/capability-matrix.json), the artifact audit in [swarm/inventory.json](swarm/inventory.json), and file/test dependencies in [swarm/dependency-map.json](swarm/dependency-map.json). Source observations are under [swarm/sources/](swarm/sources/) including [the cycle-0006 GitHub snapshot](swarm/sources/github-snapshot-cycle-0006.json); normalized input records are under [swarm/inputs/](swarm/inputs/), and cycle reports are under [swarm/cycles/](swarm/cycles/).

## Repository map

- `spec/swarm-operating-model.md` — intake, routing, work-item lifecycle, context-state lifecycle, update rules, and promotion gates.
- `swarm/registry.json` — seed registry and initial task queue for the repository-native phase.
- `swarm/intake-policy.json` — deterministic intake and routing rules.
- `swarm/source-catalog.json` — observed sources, revision strategies, routing and refresh rules.
- `swarm/sources/connected-tool-surface.json` — dated snapshot of action definitions visible to the current operator; not proof of resource access.
- `swarm/CYCLE.md` — step-by-step operator runbook for each bounded swarm cycle.
- `swarm/inventory.json` — source-backed repository inventory and recorded alignment findings.
- `swarm/sources/` — source observations, with limits and provenance.
- `swarm/cycles/` — durable reports of actual swarm cycles, inputs consumed, evidence, test results, and follow-up work.
- `schemas/intake-envelope.schema.json`, `schemas/context-state.schema.json`, `schemas/work-item.schema.json`, `schemas/registry.schema.json`, `schemas/input-record.schema.json`, `schemas/intake-policy.schema.json`, `schemas/capability-matrix.schema.json`, `schemas/cycle-plan.schema.json`, `schemas/batch-cycle-plan.schema.json`, `schemas/source-catalog.schema.json`, and `schemas/tool-surface-observation.schema.json` — repository-native state, policy, and planning contracts.
- `schemas/context.schema.json` and `schemas/event.schema.json` — deferred future-runtime contracts.
- `spec/architecture.md` and `spec/schema-alignment.md` — architecture, invariants, and the boundary between current repository-native state and deferred runtime designs.
- `spec/openapi.yaml`, `migrations/`, and `src/scs/reference_model.py` — provisional reference artifacts only; they do not imply an API, database, or service should be built now.
- `spec/backend-decision.md` — explicitly deferred; no backend selection or provisioning in this phase.
- `src/scs/intake.py`, `src/scs/transitions.py`, `src/scs/cycle.py`, `src/scs/adapters/github.py`, and `src/scs/runner.py` — pure logic for intake routing, source normalization, state-transition checks, and snapshot-to-batch plans. These modules do not fetch network data, persist state, or commit changes.
- `tests/`, `requirements-dev.txt`, and `.github/workflows/tests.yml` — schema, intake, transition, and reference-model checks.

## Current authority and persistence

For the repository-native phase, the committed registry, context state files, task records, evidence links, specifications, and Git history are the durable source of truth. Conversation text is an interface/work session, not the canonical store. A successful Git commit records a swarm-state change; it does not mean the future production architecture is finalized.

No database, server, identity service, queue service, or deployed application is required now. Use available connected tools only within their actual permissions. “All accessible sources” means sources exposed by connected integrations or supplied artifacts—not unbounded access to every service or private dataset.

## Status discipline

Distinguish:
- **observed** — read directly from a source;
- **inferred** — reasoned from observed data, with rationale;
- **proposed** — not yet accepted;
- **verified** — an explicit test or independent evidence supports the claim;
- **accepted** — approved context state;
- **blocked/conflicted/stale** — not safe to treat as current accepted truth.

A context's integrity digest is not proof of factual truth. A source's presence is not proof of authorization. A repeated claim is not independent confirmation.

## Test reference artifacts

Requires Python 3.10+ and no third-party dependencies:

```bash
python -m unittest discover -s tests -v
```

Passing reference tests verify only the tested code and file structures. They do not show that a production SCS runtime exists.
