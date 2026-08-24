# CLI reference

The CLI is the default JC interface. With `--json`, stdout carries the machine result and diagnostics use stderr.

| Command | Function |
|---|---|
| `jc capabilities` | Report the configured runtime identity, tools, limits, pack, trust, and storage capabilities. |
| `jc evaluate` | Evaluate an explicit `CaseRequest` and write an audit bundle. |
| `jc verify` | Verify a completed run selected by an artifact handle. |
| `jc replay` | Verify and semantically replay a completed run selected by an artifact handle. |
| `jc read-artifact` | Read a bounded artifact range through a signed handle. |
| `jc render` | Render a completed bundle without evaluation. |

```powershell
jc capabilities --json
jc evaluate --input case-request.json --json
jc verify --input artifact-handle.json --json
jc replay --input artifact-handle.json --json
jc render --input artifact-handle.json --format markdown --audience agent --json
```

| Exit code | Meaning |
|---:|---|
| 0 | Command completed. |
| 2 | CLI usage or input error. |
| 3 | Admission or official-pack gate blocked. |
| 4 | Engine or audit-write error. |
| 5 | Replay or integrity mismatch. |
| 6 | Optional pack/component missing. |

`JC_RUNTIME_MANIFEST` configures published capabilities. `JC_RUNTIME_FACTORY` names an
installed module whose `create_client()` returns the configured `JCClient`. Evaluation,
verification, replay, artifact reads, and rendering fail closed when that host factory is
absent. See `jc <command> --help` for exact arguments.
