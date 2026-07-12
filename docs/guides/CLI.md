# CLI reference

The CLI is the default JC interface. With `--json`, stdout carries the machine result and diagnostics use stderr.

| Command | Function |
|---|---|
| `jc doctor` | Check packaged resources and selected audit state. |
| `jc packs list` / `verify` | Inspect manifests; verify hashes, inventory, and admission. |
| `jc rules lookup` / `audit` | Search a corpus or emit governance blockers without promotion. |
| `jc evaluate` | Evaluate an explicit `CaseRequest` and write an audit bundle. |
| `jc replay` | Verify and semantically replay a completed bundle. |
| `jc render` | Render a completed bundle without evaluation. |
| `jc training export` | Export governed rule-corpus splits. |
| `jc analyze strategy` / `similar-cases` | Create advisory artifacts from a completed bundle. |

```powershell
jc evaluate --input case-request.json --json
jc replay <run-id> --json
jc render <run-id> --format markdown --audience agent --json
```

| Exit code | Meaning |
|---:|---|
| 0 | Command completed. |
| 2 | CLI usage or input error. |
| 3 | Admission or official-pack gate blocked. |
| 4 | Engine or audit-write error. |
| 5 | Replay or integrity mismatch. |
| 6 | Optional pack/component missing. |

Non-bundled rule roots require both `--development` and `--config-root`; environment variables cannot silently replace packaged rules. See `jc <command> --help` for exact arguments.
