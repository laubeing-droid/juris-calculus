# juris-calculus repository rules

JC is a public, auditable runtime kernel. Keep it separate from private case data, commercial rule packs, lawyer workflow automation, litigation strategy, and private benchmarks.

## Non-negotiable boundary

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

Do not weaken `DecisionStatus`, `verified_fact` admission, Horn, attack, exception, permission, priority, checker acceptance, or fail-closed behavior. A change that would alter them belongs first in `legal-math-modeling`.

## Working rules

- Preserve deterministic ordering in results, manifests, audit events, graphs, and MCP dispatch.
- Keep public APIs stable unless the task explicitly changes them.
- Do not add machine paths, credentials, client facts, or proprietary rules to tracked files.
- Do not push, tag, release, or change GitHub visibility without current-turn authorization.
- Generated scratch data belongs in ignored directories, never in the tracked tree.
- Record blocked checks as blocked; do not delete evidence or reinterpret it as PASS.

## Verification

Use the narrowest relevant checks first, then broader checks for user-visible work:

```powershell
python -B tools\remediate_v4.py verify-wave W0-04
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\formal_e2e tests\mcp_protocol
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\
python -B mcp_server.py --test
git diff --check
```

Run supply-chain, privacy, stale-narrative, and disclosure checks when relevant. The stdio subprocess test is the MCP transport authority; `mcp_server.py --test` is only an in-process smoke.

## Post-edit Validation

After making changes to production code, always run the appropriate validation checks:

1. **For core module changes** (compiler_core/*, pipeline/*, addons/*, tools/*):
   - Run the required manifest gate: `python -B tools\remediate_v4.py verify-wave W0-04`
   - Run the V4 formal and MCP protocol tests: `python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\formal_e2e tests\mcp_protocol`

2. **For configuration changes** (configs/*, schemas/*, pyproject.toml):
   - Run the full test suite: `python -m pytest tests\ -q`
   - Validate JSON schemas: `python -c "import json; json.load(open('schemas/jc-v4.schema.json'))"`

3. **For documentation changes** (README*, memory.md, AGENTS.md):
   - Run `git diff --check` to verify formatting
   - Ensure any referenced commands or paths are accurate

4. **For any change that might affect the MCP server**:
   - Run the in-process smoke test: `python mcp_server.py --test`

Document the validation results in your commit message or change summary.

## Core Code Boundary

### Critical (fail-closed)
- `compiler_core/evaluator.py` — Fixed-point evaluation engine
- `compiler_core/reasoning_boundary.py` — DecisionStatus classification
- `compiler_core/contracts.py` — CaseRequest/CanonicalResult contracts
- `compiler_core/types.py` — Core type definitions
- `compiler_core/step_verifier.py` — Step verification logic

Changes to these files require:
1. Full test suite pass
2. Explicit review of fail-closed behavior preservation
3. Evidence that `DecisionStatus`, `verified_fact`, or checker acceptance is not weakened

### Core (high scrutiny)
- `compiler_core/*.py` — All other compiler modules
- `pipeline/*.py` — Processing pipeline
- `mcp_server.py` — MCP transport
- `schemas/*.json` — Schema definitions

Changes require:
1. Focused boundary test pass
2. MCP protocol test pass (if applicable)

### Extension (standard)
- `addons/*` — Jurisdiction adapters
- `tools/*` — Development tooling
- `configs/*` — Configuration files
- `tests/*` — Test files

Standard validation applies.

### Documentation
- `README*`, `memory.md`, `AGENTS.md`, `CHANGELOG.md`
- No runtime impact; formatting and accuracy checks only

## Documentation and commits

Document evidence level precisely: runtime test, differential fixture, finite SMT check, upstream Lean theorem, or empirical heuristic. Keep README, manifest, CLI, and MCP statements aligned with runtime behavior; never publish static rule or test counts as permanent facts.

Each local commit should state changed files, reason, new project knowledge, impact, verification, and remaining risk.
