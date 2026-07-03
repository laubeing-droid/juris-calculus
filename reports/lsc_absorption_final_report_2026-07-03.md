# LSC Absorption Final Report 2026-07-03

## Status

github_actions_status: blocked_auth_required
workflow: ci.yml
branch: codex/lsc-boundary-absorption
run_id: unavailable
run_url: unavailable
conclusion: not_run

Local engineering phases 0-10 were implemented and locally validated. Phase 11 is blocked because `gh auth status` reports an invalid GitHub token in the keyring for `laubeing-droid`. This report does not claim CI success or completed migration.

## Phase Results

| Phase | Status | Evidence |
|---|---|---|
| Phase 0 snapshot and baseline | validated | `reports/lsc_absorption_snapshot_2026-07-03.md` |
| Phase 1 boundary docs | validated | `docs/lsc_boundary_absorption.md` and four root contract notes |
| Phase 2 fact trust envelope | validated | `compiler_core/fact_trust_envelope.py`, boundary tests |
| Phase 3 result degradation protocol | validated | `compiler_core/lsc_boundary_status.py`, boundary tests |
| Phase 4 provenance audit fields | validated | boundary result audit fields and `export_boundary_json` |
| Phase 5 derived taint propagation | validated | `compiler_core/taint.py`, derived provenance taint tests |
| Phase 6 output / renderer firewall | validated | `compiler_core/output_firewall.py`, renderer tests |
| Phase 7 cross-module IO declaration | validated | `compiler_core/io_contracts.py`, `configs/lsc_boundary_io_contracts.yaml` |
| Phase 8 conflict certificate / review packet | validated | `compiler_core/review_packet.py`, conflict/review tests |
| Phase 9 test matrix | validated | 8 `test_lsc_boundary*.py` files, 35 assertions |
| Phase 10 final report / Deli status log | validated | this report records Deli task statuses; no Deli runtime dependency was added |
| Phase 11 GitHub Actions CI | needs_more_evidence | blocked by invalid `gh` authentication |

## Modified Files

### New Files

- `compiler_core/fact_trust_envelope.py`
- `compiler_core/lsc_boundary_status.py`
- `compiler_core/taint.py`
- `compiler_core/output_firewall.py`
- `compiler_core/review_packet.py`
- `compiler_core/io_contracts.py`
- `configs/lsc_boundary_io_contracts.yaml`
- `docs/lsc_boundary_absorption.md`
- `reports/lsc_absorption_snapshot_2026-07-03.md`
- `reports/lsc_absorption_final_report_2026-07-03.md`
- `memory.md`
- `tests/unit/test_lsc_boundary_fact_trust_envelope.py`
- `tests/unit/test_lsc_boundary_result_status.py`
- `tests/unit/test_lsc_boundary_provenance.py`
- `tests/unit/test_lsc_boundary_taint_propagation.py`
- `tests/unit/test_lsc_boundary_renderer_firewall.py`
- `tests/unit/test_lsc_boundary_io_contracts.py`
- `tests/unit/test_lsc_boundary_conflict_certificate.py`
- `tests/unit/test_lsc_boundary_review_packet.py`

### Modified Files

- `FACT_VERIFICATION_STATES.md`
- `LLM_INGESTION_CONTRACT.md`
- `SEMANTIC_BOUNDARY_CHECKLIST.md`
- `FORMAL_RUNTIME_CONFORMANCE.md`
- `compiler_core/post_freeze_surface.py`
- `compiler_core/proof_trace_renderer.py`
- `compiler_core/result_exporter.py`
- `mcp_server.py`

## LSC Files Whose Ideas Were Migrated

| LSC source | Migrated idea | JC target |
|---|---|---|
| `schemas/fact_coordinate.schema.json` | FactCoordinate status/provenance/alternatives | `compiler_core/fact_trust_envelope.py` |
| `core/fact_registry.py` | fact trust, consumption/ownership firewall | `fact_trust_envelope.py`, `io_contracts.py` |
| `tests/test_fact_registry_schema.py` and `tests/test_fact_value_validation.py` | status/value boundary cases | fact trust and IO tests |
| `schemas/calculus_result.schema.json` | mutually exclusive deterministic/hypothetical/degraded/conflict/error states | `compiler_core/lsc_boundary_status.py` |
| `core/conditional_calculus.py` | USER_ASSUMED/DISPUTED/UNKNOWN degradation and output firewall | `lsc_boundary_status.py`, `output_firewall.py` |
| `tests/test_base_flow_*.py` | deterministic, disputed, hypothetical, missing, engine-error cases | boundary result tests |
| `core/derived_fact.py` | derived fact provenance and taint cannot be laundered | `compiler_core/taint.py`, derived taint tests |
| `tests/test_derivation_dag.py`, `tests/test_derived_fact_builder.py`, `tests/test_optional_user_assumed_pollution.py` | derived/optional taint scenarios | taint propagation tests |
| `tests/test_output_provenance_trace.py`, `tests/test_output_value_derivation_firewall.py` | audit fields and provenance summary | provenance tests and `export_boundary_json` |
| `tests/test_output_contamination_blocked.py`, `tests/test_output_format_guards.py`, `tests/test_schema_guards.py` | renderer/output firewall | `output_firewall.py`, renderer tests |
| `core/io_declaration.py`, `core/pipeline.py` | explicit consumed/produced keys and ownership collisions | `io_contracts.py`, `lsc_boundary_io_contracts.yaml` |
| `docs/UNKNOWN_CONFLICT_DEGRADED_cross_object_demo.md` | review-only and conflict packet shape | `review_packet.py`, conflict/review tests |
| `docs/defeasible_rules.md`, `docs/formal_models.md` | boundary-language mapping only | `docs/lsc_boundary_absorption.md` |

## LSC Files Not Migrated

| LSC source | Reason |
|---|---|
| `core/objects/` | Contains legal business objects; prohibited from JC absorption |
| `schemas/objects/` | Object schemas bind Deadline/Fee/Interest/Jurisdiction/Citation and other business semantics |
| `tests/objects/` | Object assertions encode business behavior; only boundary test ideas were reused |
| `skills/legal-skill-calculus/` | AgentSkill wrapper/playbooks/tools are explicitly prohibited |
| `core/cli.py`, `core/api.py` | LSC external surfaces are explicitly prohibited |
| Deadline/Fee/Interest/Jurisdiction/Citation fixtures and docs | Business tools and China-law workflow semantics are prohibited |
| `docs/object_dictionary.yaml`, `docs/60_object_classification.yaml` | Used only to confirm non-migration boundary |
| China-law concrete rules and P1/P2 merits examples | Would change legal semantics and require legal-math-modeling route-back |

## Boundary Matrix Coverage

The 8 boundary files cover at least these 24 scenarios:

1. verified fact normal boundary admission.
2. candidate/checked fact rejected from formal-kernel entry.
3. LLM/candidate style output remains candidate/review-only.
4. USER_ASSUMED required fact -> hypothetical_result.
5. USER_ASSUMED optional fact when used -> hypothetical_result.
6. USER_ASSUMED optional fact when unused -> clean boundary result.
7. DISPUTED required fact -> review_only_result.
8. UNKNOWN required fact -> missing_required_fact.
9. COURT_FIXED with court provenance -> verified boundary gate.
10. COURT_FIXED-like verified fact without court provenance -> no silent upgrade.
11. derived fact inherits assumption taint.
12. derived/conditional taint is retained as disclosure.
13. conflict rules -> conflict_certificate.
14. conflict_certificate does not auto-resolve priority.
15. renderer does not make hypothetical output final legal advice.
16. renderer treats degraded output as review packet.
17. renderer treats engine_error as non-advice.
18. output includes `used_fact_keys`.
19. output includes `used_rule_ids`.
20. output includes `source_snapshot_ids`.
21. output includes provenance summary only.
22. pipeline step cannot read undeclared fact.
23. pipeline step cannot output undeclared final conclusion.
24. MCP/API payload preserves machine-readable `lsc_boundary.result_status`.

## Verification

| Command | Result |
|---|---|
| `python -m pytest tests/unit/test_lsc_boundary_fact_trust_envelope.py tests/unit/test_lsc_boundary_result_status.py tests/unit/test_lsc_boundary_provenance.py tests/unit/test_lsc_boundary_taint_propagation.py tests/unit/test_lsc_boundary_renderer_firewall.py tests/unit/test_lsc_boundary_io_contracts.py tests/unit/test_lsc_boundary_conflict_certificate.py tests/unit/test_lsc_boundary_review_packet.py -v --tb=short` | 35 passed |
| `python -m pytest tests/test_mcp_smoke.py tests/test_canonical_serialization.py tests/test_composition_safety.py tests/test_conflict_case.py tests/test_incremental_grounded.py tests/unit/test_argumentation.py tests/unit/test_conflict_of_laws.py tests/unit/test_agent_protocol.py tests/unit/test_anti_degradation.py -v --tb=short` | 40 passed, 4 skipped |
| `python -m pytest tests/unit/test_mcp_manifest_dispatch.py tests/unit/test_post_freeze_surface.py -v --tb=short` | 16 passed |
| `python mcp_server.py --test` | passed; 33 tools, 12 resources |
| `git diff --check` | no whitespace errors; line-ending warnings only |
| `gh auth status` | blocked: invalid token in keyring |

Baseline note: direct `pytest tests/unit/test_agent_protocol.py tests/unit/test_anti_degradation.py` failed before migration changes with `ModuleNotFoundError: No module named 'tools'`. The same tests collect correctly under `python -m pytest`.

## Route-Back Assessment

No legal-math-modeling route-back was triggered. The work did not change `verified_fact`, `DecisionStatus`, Horn closure, attack/exception/priority/permission semantics, certificate checker acceptance, formal proof claims, or fail-closed behavior.

## Deli Task Log

| Deli task | Status |
|---|---|
| LSC-JC-00 Snapshot and baseline | validated |
| LSC-JC-01 Boundary docs | validated |
| LSC-JC-02 Fact trust envelope | validated |
| LSC-JC-03 Result status degradation | validated |
| LSC-JC-04 Provenance audit fields | validated |
| LSC-JC-05 Taint propagation | validated |
| LSC-JC-06 Renderer firewall | validated |
| LSC-JC-07 IO contracts | validated |
| LSC-JC-08 Conflict certificate and review packet | validated |
| LSC-JC-09 Test matrix | validated |
| LSC-JC-10 Final report | validated |
| LSC-JC-11 GitHub Actions CI | needs_more_evidence: auth blocked |

## Remaining Risks

- Phase 11 cannot be completed until GitHub CLI authentication is repaired.
- This implementation is an engineering boundary layer. It deliberately does not prove new formal semantics.
- Existing source-anchor warnings remain in MCP smoke output and were not modified by this migration.

## [我违规之处]

无。

