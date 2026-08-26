# juris-calculus

JC 4.0.0 is a public, auditable V4 legal-reasoning kernel. It accepts an explicit structured request, admits only verified facts and signed rules, runs one deterministic application service, and emits canonical results with replayable evidence.

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

The bounded Windows/EFS deployment for《中华人民共和国个人信息保护法》第十三至十八条 is `LOCAL_PRODUCTION_ACTIVE` with the `cn-official-local` pack. The public repository has not been remotely released, and `cn-official-local` does not promote the public `cn-official` candidate. The retired legacy corpus is not present in the current runtime or wheel and is never a fallback.

## Start

Supported Python: 3.11 and 3.12.

```powershell
git archive --format=tar HEAD -o source.tar
New-Item -ItemType Directory source
tar -xf source.tar -C source
$epoch = git show -s --format=%ct HEAD
python -B tools/wheel_gate.py --source source --out-dir dist --source-date-epoch $epoch
python -m pip install .\dist\juris_calculus-4.0.0-py3-none-any.whl
$env:JC_RUNTIME_MANIFEST = "<path-to-runtime-manifest.json>"
$env:JC_RUNTIME_FACTORY = "compiler_core.production_runtime"
$env:JC_PRODUCTION_CONFIG = "<path-to-production-runtime.json>"
jc capabilities --json
```

The runtime host supplies `JC_RUNTIME_MANIFEST` and an installed module named by
`JC_RUNTIME_FACTORY`. Its `create_client()` function returns the configured
`JCClient` with the V4 application, trust material, signed pack, and artifact store.

## Formal workflow

```powershell
jc evaluate --input case-input-bundle.json --json
jc verify --input artifact-handle.json --json
jc replay --input artifact-handle.json --json
jc render --input artifact-handle.json --format markdown --audience agent --json
```

CLI, Python, and the four-tool stdio MCP adapter all accept the same closed `CaseInputBundleV4` and use the same application service. `compiler_core/contracts.py` generates the published `schemas/jc-v4.schema.json`; the V4 tool specifications generate `mcp_manifest.json`. The version authority is `compiler_core/version.py`.

`jc-formal --registry <deployment/profile-registry.json> --input <case-input-bundle.json>`
starts the profile-pinned stdio server and emits a formal delivery only after capabilities,
evaluation, run verification, and exact paged certificate bytes all bind. This is the
local-production DSH-compatible consumer; the general `jc` command does not load it.

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
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests/formal_e2e/test_three_entrypoint_error_matrix.py
git diff --check
```

Tests, a clean wheel, and test-only provenance prove a release candidate only. The bounded local-production result is separately recorded in [remediation/v4/STATUS.md](remediation/v4/STATUS.md). Remote promotion additionally requires the governance and production-signing conditions in `.github/workflows/ci.yml` and `.github/workflows/auto-release.yml`.

## Pre-release audit

Before any public push or release, run the tracked zero-trust scan:

```bash
bash scripts/audit-engine.sh
```

Any blocker prevents `git push` and `gh release create`. The local matrix controller and AI prompts are transient ignored tooling; the CI workflow reruns the tracked deterministic scan.

## License

[MIT](LICENSE) © 2026 laubeing-droid.
