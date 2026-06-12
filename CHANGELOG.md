# juris-calculus Changelog

## v2.0.0 -- Addon Architecture (2026-06-12)

- Plugin registry with auto-discovery (scans addons/ directory)
- HK/US moved from core to addons/hk/ and addons/us/
- Blueprint split: core (14 CN MoE domains) + addon-local blueprints
- config_paths.py: all config paths parameterized via JURIS_CONFIG_DIR
- L0 concept degradation: unmapped concepts -> UNVERIFIED
- Federation by legal family: addons/federation/common_law.py
- US data: 53 titles, 266 courts, 419 federal terms, 3084 state vocabulary
- State term parser: ingest_state_terms.py + addons/us/parser.py
- NLNI cold start: cold_start_status() in neural_leaf.py
- 43/43 tests passing, 0 hardcoded paths remaining

## v1.2.0 — Tri-Rail (2026-06-04)

### Multi-Jurisdiction Collision Detection

- **Tri-Rail Collider** (`tools/run_trirail_matrix.py`): 12 cross-border conflict classes
- **PRC triple-rail engine** (`adapter/prc_adapter.py`): CBL gate (60 blocking rules) + SPC judicial tendency (23 rules) + CN statutory law (2,117 rules)
- **PRC-US Semantic Alignment Framework** (`configs/prc_us_alignment/`): 60 CBL blocking rules, 23 SPC rules, 10 procedural justice defense rules, 26 cross-jurisdiction fact bridges
- **Parallax Matrix** (`tools/run_parallax_matrix.py`): 65 PRC × 81 US divergence heatmap

### Jurisdiction Expansion

- **HK**: Expanded from 64 to 93 Horn rules (Cap 26/32/622/571/4A), `configs/hk/`
- **US**: 50-state topological router (`configs/en_US/state_router.yaml`) + WI/NJ threat signatures (24 total, `configs/us/threat_signatures/`)
- **UK**: Distillation workbench output (`configs/uk/rules_candidates.yaml`)

### Tools & Infrastructure

- **Action Agent** (`tools/action_agent/`): MemoCompiler with Jinja2 templates for partner-ready memos
- **MCP Server** (`mcp_server.py`): 9 resources + 7 tools for AI assistant integration
- **Operator Registry** (`tools/operator_registry.py`): 68 operators with bootstrap/snapshot/rollback and JSON Schema validation
- **Long-tail saturation engine** (`tools/press_long_tail.py`): Cross-jurisdiction counterexample generation
- **Shadow Runner** (`tools/shadow_runner.py`): Multi-instance adversarial testing with logic hash comparison
- **Audit tools**: `tools/audit_full.py` (cross-dimension logic consistency), `tools/pruner.py` (rule pruning)

### Pipeline Upgrades

- `pipeline/alignment_loader.py`: YAML hot-load with FastPath interceptor
- `pipeline/guardian.py`: NOMINEE gate + error classifier
- `pipeline/prc_us_alignment.py`: 3-layer alignment watchdog
- `compiler_core/parallax_inference.py`: Cross-jurisdiction parallel inference engine

### Repository Cleanup

- Removed empty `src/` package skeleton (13 files)
- Removed 12 one-shot build tools (outputs committed, tools retired)
- Removed 3 superseded test files
- Archived all reports to paper directory
- Zero hardcoded paths, zero personal identifiers in tracked files
- Tracked files: 157 → 106 (-32%)

---

## v1.0.3 (V6) — 2026-06-03

### Kernel Upgrades

- `EvidenceClassifier`: A/B/C evidence carrier level classification
- `TaintStatus` enum: CLEAR, TAINTED, ATTEMPTED_HIJACK, VERBATIM_MISMATCH
- Discretionary concept auto-TAINTED (显失公平, 公序良俗, etc.)
- `NegativeSpec`: reverse requirement gap detection
- M1 Multiplication Penalty: h==0 or p==0 → score *= 0.5
- `CRITICAL_CLARITY_FAILURE` circuit breaker
- AND-premise enhancement: single premise 48.2% → 31.9%, 690 atoms injected
- OCR concept label injection: 1,453 total, 1,921 unique concepts
- GitHub Actions: auto-release + rules-yaml-lint with Tarjan SCC cycle detection
- MCP Server (initial): evidence_review, argument_lint, contract_review
