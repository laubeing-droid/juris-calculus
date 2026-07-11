# JC v3 audit storage and replay

[我已知道的][高等] A formal `jc evaluate` run writes one completed bundle under `runs/<filesystem-safe-run-id>/` and caches its verified rule pack once under `packs/<pack-content-digest>/`.

[我已知道的][高等] The logical run ID remains `run::<digest>` inside JSON. The directory form uses `run--<digest>` because Windows forbids colons in file names; this encoding does not enter semantic digests.

## Default state root

- [我已知道的][高等] Windows: `%LOCALAPPDATA%\juris-calculus`.
- [我已知道的][高等] POSIX: `$XDG_STATE_HOME/juris-calculus`, or `~/.local/state/juris-calculus` when the variable is absent.
- [我已知道的][高等] `--audit-out PATH` replaces the state root for that command. It is not a single-run directory.
- [我已知道的][高等] A state root inside any Git worktree is rejected.

## Finalization and integrity

[我已知道的][高等] `COMPLETE` is written last. A directory without it is interrupted evidence, not a valid run. `checksums.sha256` covers `input.json`, `events.jsonl`, `result.json`, `graph.json`, and `manifest.json`; it does not include itself. Its ordered bundle digest is repeated in `COMPLETE`.

[我已知道的][高等] Replay first checks file hashes and semantic digests, then loads the exact cached pack without network access, reruns the application service, and compares the event sequence, semantic result, and graph. Missing cache material is distinct from mismatch.

## Privacy boundary

[我已知道的][高等] The stored input excludes fact descriptions, raw text, legacy source text, and arbitrary provenance dictionaries. Structured fact IDs, values, trust states, source IDs, alternatives, and admission metadata remain because replay requires them. Absolute machine paths in retained structured fields are rejected.

[我已知道的][高等] POSIX permissions are narrowed when supported. Windows ACL strength is reported as unverified rather than claimed. File hashes detect later changes but are not digital signatures and do not prove who created a bundle.

## Retention

[我已知道的][高等] JC v3 does not automatically delete runs or pack caches. The user or downstream system owns the retention period. Delete a completed run directory only after any required professional-retention or litigation-hold decision; pack caches may be removed, but replay then returns `REPLAY_MATERIAL_MISSING` until the exact pack is restored locally.

[我已知道的][高等] Rendered lawyer-facing files are not appended to completed bundles. They belong under a separate `renders/` tree and bind back to the immutable result digest.
