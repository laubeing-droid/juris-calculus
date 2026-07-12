# Audit bundle and replay

Every completed `jc evaluate` run creates one immutable evidence bundle outside the Git worktree.

| File | Purpose |
|---|---|
| `input.json` | Sanitized structured request required for replay. |
| `events.jsonl` | Ordered events for facts, rules, conflicts, checks, and result. |
| `result.json` | Canonical semantic result and logical references. |
| `graph.json` | Deterministic graph derived from the same events/result. |
| `manifest.json` | Engine, schema, pack, source, and digest identities. |
| `checksums.sha256` | Per-file hashes and ordered bundle digest. |
| `COMPLETE` | Written last; without it, the run is invalid. |

## Storage

The default state root is `%LOCALAPPDATA%\juris-calculus` on Windows, and `$XDG_STATE_HOME/juris-calculus` or `~/.local/state/juris-calculus` on POSIX. Use `--audit-out PATH` to select a state root. A Git worktree is rejected as a state root.

The logical run ID remains `run::<digest>`. Windows directories use a filesystem-safe form; that encoding is not part of semantic digests.

## Replay

```powershell
jc replay <run-id> --json
```

Replay checks completion, file hashes, event order, parent references, semantic digests, graph/result consistency, and the exact cached pack. It then reruns the application and compares semantic events, result, and graph. Missing cached pack material returns a distinct blocked result; it is not treated as a mismatch.

## Data boundary

The bundle excludes raw narratives, arbitrary provenance objects, private profiles, absolute machine paths, and irrelevant rules. It keeps only structured fields required to audit and replay. Hashes detect later modification; they are not digital signatures and do not establish authorship.

JC does not automatically delete bundles or pack caches. Retention and litigation-hold decisions belong to the user or downstream system. Rendered files live under a separate `renders/` tree and bind to the immutable result digest.
