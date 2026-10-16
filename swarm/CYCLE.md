# Swarm cycle runbook

Use this for each discrete repository-native swarm cycle. This is the current execution method; it does not require a service or background worker.

## Start a cycle

1. Read `swarm/registry.json`, `swarm/intake-policy.json`, and the relevant context dossiers.
2. Select one work item whose dependencies are accepted. Honor explicit user priority and authorization constraints before generic priority.
3. Record a cycle ID and the exact base commit and context versions being read.
4. Inspect the task's source references using only currently available, authorized tools. Record inaccessible sources rather than infer their contents.
5. Create or reuse input records. Normalize while preserving source locators, revisions, trust status, and exact evidence pointers.
6. Run the intake decision logic or apply the same rules explicitly. Duplicate, conflict, untrusted-content, missing-access, and consequential-action checks take precedence over ordinary task routing.
7. Bound the work to the item's scope and acceptance criteria. Do not broaden the task merely because related work is discoverable.
8. Produce a proposed context update, task outcome, supporting evidence, and test changes.

## Validate before accepting

- Check the proposal against the exact base versions read at cycle start.
- Validate JSON syntax and the documented schema contract.
- Check references resolve; no context/task relationship may point to a missing ID.
- Separate observed facts, inferences, proposals, and accepted decisions.
- Check source provenance, dependency freshness, conflicting claims, security boundaries, and consequences.
- Run relevant tests. For changed behavior, add/update fixtures and tests alongside or before accepting the rule.
- If validation fails, preserve the proposal as blocked/conflicted/review; do not label it accepted.

## Commit a cycle

1. Update the relevant context state version and work-item status.
2. Add evidence references, test results, and the change rationale.
3. Update inventory or derived dependency records when their inputs change.
4. Record the cycle outcome under `swarm/cycles/`.
5. Commit the correlated state changes. Prefer one commit for mutually dependent files. If tool limitations force separate commits, preserve explicit parent/base references and do not pretend the series was atomic.
6. Verify the resulting Git commit and CI result. Update the registry with the verified commit/run reference in the next state update if CI completed afterward.

## Required cycle report

Each cycle record states:
- cycle ID and source/base commit;
- inputs consumed and access scope;
- work item(s) selected;
- contexts read and target versions;
- disposition of every input;
- changes made, with path/commit references;
- tests executed and the exact result;
- conflicts, unknowns, inaccessible sources, and deferred consequences;
- follow-up tasks added or closed.

A cycle is not complete just because a response was generated. Durable state, evidence, and explicit disposition must be recorded, or the cycle must explain why no commit was appropriate.

## Retry and concurrent change behavior

If the branch head or expected context version changes during work, stop before overwriting. Reload the current registry, compare the changed records, and rebase/reconcile the proposal. Never force-push to bypass conflicting context state.

## Scope boundary

This runbook coordinates work in the repository and through authorized connected tools. It does not create continuous background execution, universal integration access, production authentication, or transactional writes to external services. Consequential external mutations require a separate permission/approval check.
