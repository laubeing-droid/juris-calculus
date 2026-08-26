# V4 formal object and state authority

`tests/fixtures/v4_contract/object-state-matrix.json` is the W0 authority for the target V4 public type registry and terminal state classifier. Runtime code does not become conformant merely because an older class has a similar name.

The registry freezes 73 formal types: the prior 56 non-MCP contract types, four additional state-envelope types needed to make the matrix explicit, and input/output/error envelopes for each of the four MCP tools plus `ToolSpecV4`. Every entry with `schema_kind=object` must emit JSON Schema `additionalProperties=false`, and its Python decoder must reject unknown fields. Closed string enums and string patterns use `additional_properties=null` because that keyword does not apply to non-objects.

Five semantic state axes and one transport outcome form a total terminal classifier:

- execution: lifecycle of the engine attempt;
- decision: semantic outcome exposed by the formal service;
- review: human-review state, not a substitute for formal proof;
- completeness: whether the result covers the admitted subject;
- certificate: independently verified artifact class;
- transport: adapter success/error outcome; it is not a semantic state.

The JSON constraints classify all 6,720 Cartesian combinations; 115 are reachable terminal combinations. The following invariants are absolute:

1. `accepted_formal_result` requires completed execution, complete coverage, no pending result review, a verified formal certificate, and transport success.
2. `hypothetical_result`, `review_only_result`, `missing_required_fact`, `conflict_certificate`, and `unknown` are completed semantic outcomes with transport success; missing material is not an engine admission failure.
3. `blocked` and `engine_error` use transport error and never carry a certificate.
4. Only `accepted_formal_result` may carry `formal_verified`; only `conflict_certificate` may carry `conflict_verified`.

`tools/remediate_v4.py object-state-matrix` independently checks registry completeness,
field closure, state reachability, exact Cartesian counts, and the
illegal-certificate/transport mutations. Runtime code and generated schemas implement
this authority; production status still depends on the separate host, pack, storage,
receipt, and release gates.

## Related documents

- [Input and semantic boundary](INPUT_AND_SEMANTIC_BOUNDARY.md)
- [Formal runtime conformance](FORMAL_RUNTIME_CONFORMANCE.md)
- [Contract authority map](../architecture/contract-authority-v4.md)
- [Documentation index](../README.md)
