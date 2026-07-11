# Project Memory

## 2026-07-03 LSC Boundary Absorption

- JC may absorb LSC only as engineering boundary mechanisms: fact trust envelopes, degradation statuses, provenance summaries, taint propagation, renderer firewalls, IO declarations, conflict certificates, and review packets.
- Route back to `D:\Codex\数学证明\legal-math-modeling` if a future change alters `verified_fact`, `DecisionStatus`, Horn closure, attack/exception/priority/permission semantics, certificate checker acceptance, formal proof claims, or fail-closed behavior.
- Do not migrate LSC business objects, object schemas, Deadline/Fee/Interest/Jurisdiction/Citation tools, AgentSkill, CLI/API wrappers, China-law concrete rules, or P1/P2 substantive judgments into JC.
- Local verification for the boundary layer used `python -m pytest`; direct `pytest` collection had a pre-existing import-path issue for top-level `tools`.
- `legal-math-modeling` was consolidated to `main` after documenting the LSC runtime-boundary route-back. JC can cite it as a specification boundary only; it cannot use legal-math CI as a claim that runtime metadata is Lean-proved.

## 2026-07-11 MCP / Tri-Rail / Rule Admission Closure

- MCP stdio must be client-driven: no startup output, initialize echoes the client request ID, notifications receive no response, and business calls before initialization fail with `-32002`.
- MCP stdio stdout is protocol-exclusive for the entire process lifetime. Library constructors such as `TriRailCollider` must remain silent; diagnostics belong in structured payloads, logging, or explicit CLI harness output. The transport gate must execute at least one real `tools/call`, not only handshake and listing.
- `python mcp_server.py --test` is only an in-process functional smoke. The authoritative transport gate is `tests/unit/test_mcp_stdio_protocol.py`, which launches a real subprocess.
- Tri-Rail has one implementation in `tools/run_trirail_matrix.py`; MCP, matrix generation, and long-tail pressure testing consume that shared core. Do not restore the removed `PRCAdapter` / `execute_prc_first_override` path.
- YAML rules without an explicit source anchor or an existing authority field are retained as `UNVERIFIED + CANDIDATE_ONLY` training corpus entries and excluded from `FixpointEvaluator` reasoning indexes. Never synthesize an anchor from a rule name or narrative description.
- Current generated inventory after the admission gate: HK 40/133 reasoning-eligible, US 0/81, PRC 21123/21209; the PRC CN track corpus remains 21,144 with 21,081 reasoning-eligible.
- Rule counts in public descriptions must come from runtime inventory. Static `2,117` / `21,145` literals are forbidden in active files; `configs/zh_CN/rules.yaml` length and `_meta.total` must agree.
- Supply-chain audit is fail-closed through `tools/supply_chain_gate.py`: PASS=0, FAIL=1, BLOCKED=2. Proxy/TLS/network failures are evidence of BLOCKED, never PASS.
- Verified local closure on Python 3.11.15 and 3.12.5: 360 passed, 38 skipped on each version; real stdio business calls passed; in-process MCP smoke passed; pip-audit reported zero known vulnerabilities on each version after bypassing a stale process-local proxy.

## 2026-07-11 JC v3 Phase 0 Baseline

- The protected v2 semantic baseline is `tests/unit/test_v3_semantic_baseline.py`; it freezes obligation, prohibition, permission, exception, attack, priority, unresolved conflict, truncation, and independent-checker rejection without retaining timestamps, paths, or random IDs.
- `docs/v3-evaluation-entrypoints.md` is the deletion/migration ledger for every direct production evaluator constructor plus indirect holders. Product paths migrate to one application service; adapters stop returning evaluators; harnesses stay CLI/CI; low-level semantic tests may still call evaluator stages directly.
- The v2 MCP migration inventory is exactly 33 tools and 12 resources, with one disposition per name in the full remediation plan. Do not add a runtime compatibility layer when Phase 7 removes them.
- Cross-platform tracked-file baselines must hash Git index blobs, not raw Windows worktree bytes; CRLF filters otherwise create false file-size and SHA-256 drift.
- Phase 0 closure baseline on Python 3.11.15 and 3.12.5 is 365 passed, 38 skipped on each version after adding five protected semantic fixtures.
- Phase 1 fact-admission bug closure: `classify_boundary_result()` no longer falls through to accepted status for candidate/normalized/source-bound/checked/rejected/stale facts. Formal acceptance now requires complete LegalFact admission plus explicit checker acceptance, formal certificate kind, and actual formal-kernel execution.
- `LegalFact` is the single runtime fact object. The old `FactTrustEnvelope` name is only a migration factory that returns `LegalFact`; fact status/creator enums and `can_enter_formal_kernel()` live with the authoritative object.
- `compiler_core/contracts.py` is the v3 status/request/result/schema fact source. `ResultStatus` and `ExecutionStatus` are separate; immutable semantic/canonical results reject illegal formal-success combinations; `schemas/jc-v3.schema.json` is generated from `schema_document()`.
- Empty `IRState` carries no case date, governing law, contract-validity conclusion, or shared `W1` identifier. Those inputs must be explicit in CaseRequest or fixtures; absence remains unknown/review-only rather than valid by default.
- Public case/pipeline/checklist/trace IDs use SHA-256 canonical content helpers. Canonical Horn/AAF serialization deep-copies inputs, and semantic digests exclude runtime timestamps, paths, PID/temp fields, and digest fields themselves.
- After hidden `Contract_Validity=VALID` removal, Tri-Rail HK/US tracks with no claims correctly report `?`; the 12 scenario classifications and PRC blocking results remain unchanged. Current generated matrix reports reflect this correction and the HTML generator is timestamp-free.

## 2026-07-11 JC v3 Phase 2 Application Service

- `compiler_core/application.py:evaluate_case()` is the sole internal case orchestration service. It validates the request-to-pack binding, performs fact and rule admission, creates a new `IRState` per run/branch, invokes the existing full evaluator, builds/checks the AAF, and constructs one immutable `SemanticResult`; it remains unexported until the CLI migration is complete.
- Source admission belongs before the formal evaluator, not inside Horn/DDL algorithms. Exact manifest ID plus an explicit verified flag and SHA-256 content hash are required; partial-prefix matching and description-derived anchors are forbidden. Rules that fail this gate remain candidates and are not executed.
- The application must call the existing full `FixpointEvaluator.evaluate()` rather than the Horn-only stage, because the latter intentionally omits prohibition, rebuttal, and other DDL behavior. Material used-rule IDs come from deterministic `RULE_APPLIED`, `RULE_EXCEPTION_TRIGGERED`, and `PROHIBITION_BLOCK` events.
- `UNKNOWN` returns missing facts without kernel execution; `DISPUTED` produces deterministic branches and an overall review-only result; `USER_ASSUMED` is hypothetical and cannot carry a formal certificate. Relevant candidate facts/rules, permission conclusions, claim taint, source failure, checker failure, or engine exceptions fail closed.
- PRC CBL rules without an explicit authority field no longer execute. Their narrative descriptions are not source anchors; they stay in corpus/governance data until a real source snapshot is supplied.
- Phase 2 closure baseline on Python 3.11.15 and 3.12.5 is 429 passed, 38 skipped on each version. The old 33-tool MCP manifest dispatch dominates runtime (231s on 3.11 and 197s on 3.12) and is scheduled for removal in Phase 7, not hidden by skipping the test.

## 2026-07-11 JC v3 Phase 3 Packaging and CLI Foundation

- `pyproject.toml` is the package/dependency authority for v3: Python is restricted to 3.11/3.12, `PyYAML` is the only core dependency, and document/pipeline/render/MCP dependencies are extras. `compiler_core.version.__version__` is the package, CLI, and engine version source.
- `configs` and `schemas` are package-data packages, so the wheel reuses tracked resources without duplicating the 14MB CN corpus. Every release wheel must contain `schemas/jc-v3.schema.json`, `configs/render_profiles/neutral.yaml`, the published rule resources, and the `jc` console entry point.
- The default CLI uses stdlib `argparse`. Only implemented commands are registered; at this stage `rules lookup` searches the explicitly labeled `cn-legacy-corpus` and `doctor` validates installed resources. JSON mode keeps stdout to one success document and writes stable four-field errors only to stderr.
- Wheel smoke tests must run outside the repository in a new venv and prove that `compiler_core`, `configs`, and `schemas` resolve from `site-packages`. A source-tree command is not packaging evidence.
- Commit 5 baseline on Python 3.11.15 and 3.12.5 is 436 passed, 38 skipped. The universal wheel was 3,185,540 bytes and independently installed/runs on both supported interpreters.
- Rule packs live under `configs/packs/<pack-id>/manifest.yaml`. A manifest binds rule/source/config file hashes, actual inventory, content digest, dates, governing law, and the source commit. `packs list` only reports declared metadata as `not_run`; only `packs verify` performs hash/admission verification.
- `cn-official` is intentionally empty and BLOCKED because no current rule has an official first-party source snapshot hash. The existing corpora are separately identified as `cn-legacy-corpus` (21,144 candidates), `hk-legacy-corpus` (133), `us-federal-legacy-corpus` (123), and `us-l0-adapter-legacy-corpus` (81). None is a silent fallback for formal evaluation.
- `configs/en_US/rules.yaml` is an explicit tombstone for the old empty default. The duplicate `US-Immunity` rule and constraint IDs were split into `Transactional` and `Use` identities based on their existing terms/targets; pack verification now rejects any duplicate rule or pack ID.
- Setting `JURIS_CONFIG_DIR` alone cannot replace bundled resources. A non-bundled config root requires both an explicit development mode and path; machine output records only `development_override=true` and a path hash, never the absolute path.
- Manifest `build_commit` is the committed source-resource baseline, not a claim that a tracked manifest contains its own commit SHA. The US identity/tombstone source fix is baseline `2053843f397d2ee1c0797831f05f80ba89841e79`; file hashes bind the exact packaged bytes without circular provenance.
- Phase 3 closure baseline on Python 3.11.15 and 3.12.5 is 449 passed, 38 skipped. The final wheel was 3,195,631 bytes, contained all five manifests, and produced doctor=3/list=0 from clean venvs on both versions as designed.

## 2026-07-11 JC v3 Phase 4 Semantic Audit and Graph Foundation

- `compiler_core/audit.py` is the only semantic event/graph implementation. Each case owns one `AuditRecorder`; it assigns contiguous sequence IDs, validates semantic parent references, strips runtime timestamps/paths, and maps application/evaluator callbacks to the v1 audit vocabulary.
- Audit details are per-event allowlists with independent JSON Schema definitions. Unknown fields, unsupported values, overlong text, absolute paths, or nonexistent parent event IDs fail closed; a downstream audit sink failure forces an engine-error result with no accepted claims.
- `RELEVANCE_SET_BUILT` starts from admitted fact keys and recursively includes Horn support, exception, and priority dependencies. Rule admission events are emitted only for this set; unrelated pack rules are not copied into a case log.
- `build_reasoning_graph()` consumes only `SemanticResult` plus `AuditEvent` objects. It cannot access the evaluator and creates only explicit premise/support/attack/exception/priority/permission/prohibition/provenance/taint/checker/branch edges; event adjacency is never treated as legal causation.
- Missing-fact runs do not fabricate checker nodes. Formal claims have rule support, checker validation, source provenance, and certificate links; all graph nodes/edges and semantic events are deterministically sorted/hashable.
- Commit 7 remains an in-memory semantic audit foundation, not a persistent audit chain. Bundle finalization, checksums, default user-state storage, COMPLETE marker, tamper detection, and replay are still Phase 4 commit 8 work.
- Commit 7 baseline on Python 3.11.15 is 464 passed, 38 skipped (479.21s); Python 3.12.5 is 464 passed, 38 skipped (430.39s).
- `compiler_core/audit_bundle.py` is the persistent audit/replay boundary. A formal run writes canonical input/events/result/graph/manifest, hashes those five files, writes checksums, and atomically writes `COMPLETE` last. A missing marker is always interrupted evidence.
- Logical run IDs retain `run::<digest>`; filesystem directories use the deterministic Windows-safe form `run--<digest>`. The encoding is used only in logical artifact refs and never changes semantic result IDs.
- Audit input removes descriptions, raw text, legacy source text, and arbitrary provenance. It retains only structured replay fields and rejects absolute machine paths in retained values. The bundle is path-independent: identical cases in different state roots produce identical result, graph, and bundle digests.
- Verified official pack material is copied once to `packs/<content-digest>/configs/...` and revalidated from its own cached manifest. Replay is offline, distinguishes missing material from mismatch, and compares exact event sequences, semantic results, and graph documents after integrity verification.
- Default state is `%LOCALAPPDATA%/juris-calculus` on Windows and XDG/local state on POSIX. Git-worktree state roots are rejected. POSIX permissions are narrowed; Windows ACL strength remains explicitly unverified rather than claimed.
- Commit 8 baseline on Python 3.11.15 is 489 passed, 38 skipped (464.33s); Python 3.12.5 is 489 passed, 38 skipped (431.97s). A 3,214,530-byte wheel independently completed evaluate/replay on both supported versions from outside the repository.
