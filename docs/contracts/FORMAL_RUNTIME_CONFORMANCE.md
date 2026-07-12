# Runtime claims and evidence limits

| Repository | Responsibility |
|---|---|
| `legal-math-modeling` | Formal specification and theorem statements. |
| `juris-calculus` | Python runtime, deterministic tests, audit/replay, CLI, and optional MCP adapter. |

JC does not claim that every Python path is machine-proved or that it supplies a final legal opinion for a real case.

| Evidence | Permitted claim |
|---|---|
| Runtime test | Regression evidence for the executed path. |
| Spec-shadow fixture | Differential evidence for the covered fixture. |
| Finite SMT check | Bounded check, not a universal theorem. |
| Upstream Lean theorem | Specification evidence from the upstream theorem. |
| Heuristic/diagnostic | Task-specific empirical observation. |

Acceptance paths must not contain silent placeholders. An intentionally incomplete feature must be outside the acceptance path or fail closed; it must name its limitation and never be presented as a formal proof.

Minimum local checks:

```powershell
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\unit\test_mcp_stdio_protocol.py -q
python -m pytest tests\ -q
python mcp_server.py --test
```

The real stdio subprocess test is the transport authority. The in-process smoke is not a readiness or product-UI claim. A blocked check must remain blocked in the report.
