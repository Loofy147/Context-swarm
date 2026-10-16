# Intake records

Store small normalized input envelopes here when an incoming requirement or source must be recorded as part of the durable swarm state. Preserve source locator, revision, access boundary, trust status, disposition, and context/work-item links.

Do not copy secrets or unnecessarily mirror protected source content. Large artifacts should be referenced by stable link and digest instead of committed inline. Replayed source revisions must be recognized as duplicates; new revisions may update evidence without erasing earlier records.
