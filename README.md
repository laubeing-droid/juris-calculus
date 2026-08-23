# juris-calculus

JC 4.0.0rc1 is a public, auditable V4 legal-reasoning kernel. It accepts an explicit structured request, admits only verified facts and signed rules, runs one deterministic application service, and emits canonical results with replayable evidence.

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

The repository is a local release candidate, not a production release. `cn-official` is absent until an approved first-party source inventory, independent legal and engineering review, and production signing are all real. The retired legacy corpus is not present in the current runtime or wheel and is never a fallback.

## Start

Supported Python: 3.11 and 3.12.

```powershell
python -m pip install .
jc doctor --json
jc packs list --json
jc packs verify --all --json
```

## Formal workflow

```powershell
jc evaluate --input case-request.json --json
jc verify <run-id> --json
jc replay <run-id> --json
```

CLI, Python, and the four-tool stdio MCP adapter all use the same V4 parser and application service. The machine contracts are generated from `schemas/jc-v4.schema.json` and `mcp_manifest.json`; the version authority is `compiler_core/version.py`.

## Safety boundary

- Only admitted `verified_fact` values enter formal reasoning.
- Review, missing-fact, hypothetical, conflict, unknown, and engine-error outcomes stay distinct.
- Candidate or development packs cannot become formal by changing a flag.
- Audit, verify, and replay bind the exact runtime, pack, trust policy, schema, tool contract, locks, and stored bytes.
- No public entrypoint retains a V3, W1b, caller-trusted, or legacy fallback route.

## Documentation

[Documentation index](docs/README.md) · [CLI](docs/guides/CLI.md) · [Audit and replay](docs/contracts/AUDIT_BUNDLE.md) · [Rule packs](docs/contracts/RULE_PACKS.md) · [V4 release procedure](docs/operations/RELEASE_V4.md)

## Local verification

```powershell
python -B tools/remediate_v4.py verify-wave W0-04
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests/contract tests/formal_e2e tests/mcp_protocol tests/security
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests/packaging
python -B tools/wheel_gate.py --help
python -B tools/build_provenance.py --help
python -B mcp_server.py --test
git diff --check
```

Tests, a clean wheel, and test-only provenance prove a release candidate only. Remote promotion additionally requires the governance and production-signing conditions in `.github/workflows/ci.yml` and `.github/workflows/auto-release.yml`.

## License

[MIT](LICENSE) © 2026 laubeing-droid.
