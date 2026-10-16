# Context records

The repository-native registry is `../registry.json`. Use this directory for durable, domain-specific context dossiers only when the context needs detail beyond the registry summary.

Each dossier should include:
- context ID and version;
- purpose/scope/invariants;
- current claims and decisions with epistemic status;
- evidence references and exact source versions;
- incoming/outgoing relationships;
- unresolved questions, risks, conflicts, and stale dependencies;
- change rationale and the commit that accepted the version.

Do not duplicate the full contents of source repositories or conversation transcripts. Prefer durable source links and minimal evidence excerpts. Update the registry and dossier in the same change when the context's canonical state changes.
