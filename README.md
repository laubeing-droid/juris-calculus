# juris-calculus

JC is a public, auditable legal-reasoning kernel. It receives an explicit structured case request, applies only admitted rules, writes a replayable audit bundle, and returns a canonical machine result.

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

JC is not a case-management system, a source-document ingestion pipeline, a legal opinion generator, or a lawyer workflow product. Private facts, proprietary rule packs, litigation strategy decisions, and personal writing style stay outside this repository.

## Start

Supported Python: 3.11 and 3.12.

```powershell
python -m pip install .
jc doctor --json
jc packs list --json
jc packs verify --all --json
```

`cn-official` remains blocked until an official first-party source snapshot is supplied. Legacy corpora are available for inspection, governance, and training export; they are never a silent fallback for formal reasoning.

## Core workflow

```powershell
jc evaluate --input case-request.json --json
jc replay <run-id> --json
jc render <run-id> --format markdown --audience agent --json
```

`evaluate` always writes a completed audit bundle: sanitized input, relevant semantic events, canonical result, deterministic graph, manifest, hashes, and completion marker. `replay` verifies bytes and semantic output. `render` only reads a completed bundle; it never re-evaluates facts or rules.

## Interfaces

- **CLI:** primary interface for people, local agents, and automation.
- **Python:** internal application service behind the CLI and adapter.
- **WorkBuddy MCP:** optional compatibility adapter with four tools and no resources. It is not enabled by the core installation and does not contain another evaluator.

## Safety rules

- Only `verified_fact` may enter formal reasoning.
- `UNKNOWN`, `DISPUTED`, and `USER_ASSUMED` remain review-only, branch, or hypothetical states; none produces a formal certificate.
- A rule needs explicit source admission before it is reasoning-eligible.
- Rendering and advisory analysis cannot modify the canonical result.
- Horn, attack, exception, permission, priority, checker, `DecisionStatus`, and fail-closed semantics are protected.

## Documentation

[Documentation index](docs/README.md) · [中文说明](docs/guides/README_CN.md) · [CLI](docs/guides/CLI.md) · [Audit and replay](docs/contracts/AUDIT_BUNDLE.md) · [Rule packs](docs/contracts/RULE_PACKS.md) · [WorkBuddy](docs/guides/WORKBUDDY.md)

## Local verification

```powershell
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_mcp_stdio_protocol.py -q
python -m pytest tests\ -q
python mcp_server.py --test
python tools\supply_chain_gate.py --requirements requirements\core.lock
git diff --check
```

The subprocess stdio test is the MCP transport authority. `mcp_server.py --test` is only an in-process smoke. Test counts and remote CI status are evidence only when recorded by the corresponding run.

## License

[MIT](LICENSE) © 2026 laubeing-droid.
