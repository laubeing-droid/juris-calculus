# P0-P2 Execution Roadmap

This roadmap is an implementation contract for the next upgrade. It treats the research memo as input to verify, not as authority.

## P0: Make the symbolic chain measurable and auditable

Acceptance targets:

- Relevance-sensitive fixtures and runner exist.
- Claims can carry stable execution trace ids and proof events.
- AAF attack edges can be built from explicit rule metadata, not only text notes.
- Rule quality audit reports blocking issues in machine-readable form.

Deliverables:

- `tests/relevance_sensitivity/*.yaml`
- `tools/relevance_sensitivity_runner.py`
- `compiler_core/proof_trace.py`
- `compiler_core/argumentation.py` explicit attack builder
- `tools/rule_quality_auditor.py`
- focused unit tests

## P1: Add minimal Typed Legal IR and constraint sidecar

Acceptance targets:

- A small IR schema validates rule id, type, source anchor, temporal validity, typed conditions, exceptions, and priority.
- Existing Horn-style rules can be represented as a compatibility subset.
- SMT sidecar handles dates, numbers, and mutually exclusive states without becoming a legal decision maker.
- Missing optional SMT dependency degrades to `UNAVAILABLE`, not CI failure.

Deliverables:

- `compiler_core/legal_ir_v3.py`
- `compiler_core/type_checker.py`
- `compiler_core/source_anchor.py`
- `compiler_core/smt_sidecar.py`
- focused unit tests

## P2: Prepare neural assistance without letting it decide

Acceptance targets:

- Neural/LLM candidates enter shadow state only.
- Divergence reports compare official and shadow outputs.
- Neural contracts exist for features, outputs, model cards, and promotion policy.
- No network/API key is required for tests.

Deliverables:

- `compiler_core/shadow_state.py`
- `tools/shadow_divergence_report.py`
- `neural/contracts/*.yaml`
- focused unit tests

## Non-goals for this increment

- No end-to-end neural adjudication.
- No replacement of `FixpointEvaluator`.
- No mandatory Z3 dependency.
- No full migration of all YAML rules to IR v3.
- No automatic promotion of neural output into official `IRState`.
