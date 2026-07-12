# Audit bundle and replay

Each formal evaluation writes a user-state run directory outside the Git repository.

| File | Role |
|---|---|
| `input.json` | Sanitized structured request needed for replay. |
| `events.jsonl` | Ordered semantic events for relevant facts/rules only. |
| `result.json` | Immutable semantic result plus logical artifact references. |
| `graph.json` | Deterministic nodes, causal/conflict edges, and graph digest. |
| `manifest.json` | Engine/schema/pack identities and semantic digests. |
| `checksums.sha256` | Per-file hashes and bundle digest. |
| `COMPLETE` | Written last; absence means the run is incomplete. |

Replay rejects missing completion markers, changed bytes, rewritten outer checksums with invalid semantic digests, invalid event order, unknown parents, graph/result drift, and missing cached pack material.

Raw narrative, arbitrary provenance objects, private profile content, absolute machine paths, and unrelated rules are not stored. `UNKNOWN`, `DISPUTED`, and `USER_ASSUMED` remain missing-fact, branch/review, and hypothetical states and cannot produce a formal certificate.
