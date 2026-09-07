# CLI reference

This page covers every `jc` subcommand, the exit codes, the host environment variables, and the second console script `jc-formal`. The CLI is the default JC interface; with `--json`, stdout carries the machine result and diagnostics use stderr.

| Command | Function |
|---|---|
| `jc capabilities` | Report the configured runtime identity, tools, limits, pack, trust, and storage capabilities. |
| `jc evaluate` | Evaluate an explicit `CaseInputBundleV4` and write an audit bundle. |
| `jc verify` | Verify a completed run selected by an artifact handle. |
| `jc replay` | Verify and semantically replay a completed run selected by an artifact handle. |
| `jc read-artifact` | Read a bounded artifact range through a signed handle. |
| `jc render` | Render a completed bundle without evaluation. |

```powershell
jc capabilities --json
jc evaluate --input case-input-bundle.json --json
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
installed module whose `create_client()` returns the configured `JCClient`.
`JC_PRODUCTION_CONFIG` selects the production configuration. Evaluation, verification,
replay, artifact reads, and rendering fail closed when the configured host is absent.
See `jc <command> --help` for exact arguments.

## jc-formal

`jc-formal` is the profile-fixed formal entry point. It loads one active profile from a
deployment registry, evaluates the bundle through the formal bridge, and writes one
verified canonical delivery to stdout:

```powershell
jc-formal --registry <deployment/profile-registry.json> --input <case-input-bundle.json>
```

`--registry` defaults to `JC_PROFILE_REGISTRY`, then to `deployment/profile-registry.json`.
Errors print a stable code on stderr and exit 1.

## Related documents

- [Chinese guide](README_CN.md)
- [Input and semantic boundary](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)
- [Audit-bundle contract](../contracts/AUDIT_BUNDLE.md)
- [Documentation index](../INDEX.md)
