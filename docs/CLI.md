# JC CLI contract

The CLI is the primary interface for humans, Codex, automation, and downstream legal agents. JSON mode writes one success object to stdout and one stable error object to stderr.

## Commands

| Command | Purpose |
|---|---|
| `jc doctor` | Diagnose packaged resources, audit state, Python support, and optional adapter availability. |
| `jc packs list` | List declared pack metadata without claiming verification. |
| `jc packs verify` | Verify manifests, hashes, inventory, dates, and rule admission. |
| `jc rules lookup` | Bounded lookup in a corpus; lookup does not promote rules. |
| `jc rules audit` | Produce governance findings and promotion blockers. |
| `jc evaluate` | Evaluate one explicit `CaseRequest` and write a complete audit bundle. |
| `jc replay` | Verify and semantically replay a complete bundle. |
| `jc render` | Render a verified run with the packaged neutral renderer; never evaluates facts. |
| `jc training export` | Export governed corpus splits without private case facts. |
| `jc analyze strategy` | Produce review-required strategy advisory from a verified run. |
| `jc analyze similar-cases` | Compare a verified run with an explicit versioned case index. |

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Command completed successfully. |
| 2 | Invalid input or CLI usage. |
| 3 | Admission or official-pack gate blocked. |
| 4 | Engine or audit-write error. |
| 5 | Replay or integrity mismatch. |
| 6 | Optional pack/component missing. |

Non-bundled rule roots require both `--development` and `--config-root`. Environment variables alone cannot silently replace packaged rules. `jc render` is fixed to the packaged neutral profile; personal style overrides are not part of the public kernel.
