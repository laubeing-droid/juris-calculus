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

## 2026-07-11 JC v3 Phase 4 Entrypoint Migration

- `compiler_core`包根只导出正式application、audit bundle和contracts；CLI和MCP通过`evaluate_registered_case()`共享显式pack解析与完整审计落包。
- 旧MCP `_juris_evaluate_core/_sync`、自由文本求值和独立stratified执行体已删除。迁移期旧工具名只接受完整`CaseRequest`；strategy只接受审计run ID，Phase 7将删除旧33工具表。
- 无消费者的automated/batch/multi-jurisdiction/multi-solver/parallax/federation重复执行模块已删除。法域adapter不再返回裸evaluator。
- `pipeline/pipeline.py`只负责案卷摄取并输出`CANDIDATE_ONLY`事实；它不得自动晋升事实或执行正式规则。正式求值要求调用`jc evaluate`。
- 旧`LitigationChainRenderer`、ProofTree语言renderer和任意trace renderer均已删除；`post_freeze_surface` toy report不再求值并返回`AUDITED_RUN_REQUIRED`。展示只允许从完整审计run进入`compiler_core/rendering.py`。
- `tests/unit/test_v3_entrypoint_boundary.py`以AST固定唯一正式入口，并仅允许application、底层语义stage和明确CLI/CI harness直接构造evaluator。新增或恢复生产绕行会直接失败。
- Phase 4提交9验证基线：Python 3.11.15与3.12.5均为486 passed、38 skipped；两版本进程内MCP smoke均通过。旧33工具/12 resources仍存在但已无独立正式求值体，按Phase 7删除，不能把当前smoke表述为v3 MCP surface完成。

## 2026-07-11 JC v3 Phase 5 Rendering Boundary

- `compiler_core/rendering.py`是唯一展示实现。它先验证完整审计包，只消费`SemanticResult`与`graph.json`，生成Markdown、Mermaid或显式HTML；任何格式都不能调用evaluator或修改canonical bytes。
- 展示产物写入独立`renders/<run>/<result-digest>/<profile-hash>/`，每份正文带不重复正文的`.render.json`旁车，绑定result/profile/renderer/audience/format/content SHA-256并只返回逻辑引用。
- `jc render` 固定只接受包内neutral profile。展示层不得接受命令行、私有目录或环境变量的个人profile覆盖；如有个人文风需求，只能在JC公共内核之外做后处理。
- 旧litigation、ProofTree语言和任意trace renderer均已删除。MCP旧`format_proof_trace`只返回`AUDITED_RUN_REQUIRED`，Phase 7将删除该工具名。
- HTML只在用户明确调用时生成，转义全部文本并以CSP禁用脚本和网络资源；Mermaid只映射现有Graph JSON中的节点和显式边。
- JC 公共内核的展示层固定为 neutral、stable、auditable 输出；个人律师文风不属于当前内核范围，不再维护个人 profile 机制或样例阻断项。
- Phase 5验证基线：Python 3.11.15与3.12.5均为486 passed、38 skipped。wheel为3,219,692字节，仓库外安装后从site-packages成功加载renderer/neutral profile并注册`jc render`。

## 2026-07-11 JC v3 Phase 6 Governance and Advisory

- `MissingFactReview`是SemanticResult的一部分：UNKNOWN事实记录受影响rule/claim、允许回答类型和verified fact来源要求；Graph使用`missing_premise`/`potential_conclusion`边，绝不把潜在结论当作已推导。
- `compiler_core/rule_governance.py`是唯一规则质量实现，旧tool只是wrapper。Pack治理复用manifest hash/inventory/source准入；candidate finding阻断promotion但不阻断candidate corpus留存，自动promotion永远为false。
- 真实`cn-legacy-corpus`治理为21,144/0/21,144，runtime blocking=0，promotion blocking=2,067：2,004条悬空exception引用与63条缺来源。不得猜测修复；它们继续candidate-only，完整artifact约434KB。
- `compiler_core/training.py`是唯一训练导出实现。真实CN corpus以seed 42导出16,915 train/2,114 dev/2,115 test，总约17.2MB；dataset hash为`01deb2b047d9133d90d7004b9ffce07aec035d878776d95e1b62bbf44f0bb4cc`，不含案件事实且不能写回config root。
- `compiler_core/analysis.py`只读完整审计run，策略与类案输出固定为ADVISORY、review required、无formal certificate，并写独立analysis artifact。策略路径只来自missing/attack/branch/claim/source结构。
- 类案初版使用fact/rule/claim/edge集合的确定性Jaccard加权和带digest/source hash的JSON index，不使用数据库、向量或网络。仓库只含synthetic fixture；真实类案实务质量因无授权index保持BLOCKED。
- Tri-Rail保留为explicit engineering harness。它记录HK/US/PRC legacy pack/config digest，但由于三套official reasoning-ready packs不存在，普通与fast-path均formal_kernel_used=false；低层分类不具备案件结论资格。
- 修复`build_attack_edges_from_rules()`仅测试时依赖顺序掩盖的缺陷：现在显式attacks/priority/exception引用统一解析rule ID到claim ID并稳定排序；正式application的受保护attack算法未改变。
- Phase 6最终双版本基线：Python 3.11.15和3.12.5均495 passed、38 skipped。wheel为3,236,396字节、SHA-256=`bf4e20a36ee2197692cb757e36a5251650c1846f73fd69ec9ad5ac35288b6c21`；仓库外安装从site-packages加载analysis/governance/training并注册四组Phase 6 CLI。

## 2026-07-11 JC v3 Phase 7 CLI-First WorkBuddy Adapter

- CLI/application remains the primary JC interface. WorkBuddy is the only current reason to retain MCP: official WorkBuddy documentation supports custom MCP connectors and also describes Skill + CLI, so the adapter stays dormant until explicitly registered.
- The production MCP surface is exactly `jc_evaluate`, `jc_lookup_rule`, `jc_analyze_strategy`, and `jc_analyze_similar_cases`. The old 33 tools and 12 whole-corpus resources have no runtime compatibility layer.
- `addons/workbuddy_mcp.py` is transport-only. It calls the existing audit application, bounded pack lookup, and read-only analysis services; it may not construct evaluators, load a parallel rule set, render lawyer prose, expose full event streams, or return absolute paths.
- Adapter artifacts use `run://<encoded-run-id>/...` logical references. Tool errors are compact, fail-closed, traceback-free, and do not terminate the stdio process.
- The stdio contract remains startup-silent, notification-silent, initialization-gated, and error-surviving. Resource lists are empty; `python mcp_server.py --test` is an in-process surface smoke and explicitly does not claim readiness.
- The obsolete `post_freeze_surface`, fixed Action Agent memo generator/template, and stale agent methodology table were deleted because they had no valid production consumer after the four-tool cut.
- Phase 7 closure baseline on Python 3.11.15 and 3.12.5 is 479 passed, 38 skipped on each version. The reduction is the deleted legacy surface test suite; protected semantics, application, audit, replay, graph, render, governance, training, and advisory gates remain in the full run.
- A wheel built over a stale `build/lib` directory can resurrect deleted Python modules even when the source tree and tests are correct. Local and CI packaging gates must remove verified generated `build`/egg-info directories first, then inspect the wheel archive for forbidden legacy modules before installation.
- The clean Phase 7 wheel is 3,218,675 bytes with SHA-256 `c78bdc86996311e81229e9e641db515d4782cf7ebf1ed1ddaaa7f298dcc5b657`; an outside-repository target install loaded the four-tool adapter from site-packages and reported zero resources.

## 2026-07-11 JC v3 Phase 8 Engineering Gates

- Core dependency installation is separated from documents, pipeline, render, and WorkBuddy profiles. `requirements-core.lock` pins PyYAML 6.0.3 with hashes for CPython 3.11/3.12 on Windows x86-64 and manylinux x86-64; CI test tooling is version-pinned separately.
- GitHub CI pins action commits and legal-math-modeling commit `a3a015941f75091c87d57aa956e712f1546dd7d4`. Local implementation does not imply remote verification; Actions remain NOT_EXECUTED until an authorized push.
- `RulePackRegistry` caches only immutable, digest-bound loaded packs within one registry. It never caches case state, recorder state, or semantic results across runs.
- The performance gate now measures the audited application rather than legacy toy operations. Fixed synthetic-fixture observations were cold 0.779225s, warm 0.687969s, disputed branch 1.386098s, 1,257,141 peak bytes, 10 audit events, and a 9,218-byte bundle; committed budgets are explicit regression ceilings, not corpus-throughput claims.
- Clean-wheel verification removes only repository-contained generated build caches, rejects known deleted modules, installs the wheel outside the source tree, and checks the dormant adapter remains four tools/zero resources.
- Active runtime terminology is `reasoning_boundary` and `FactCoordinate`; the former external framework name is retained only in dated historical migration evidence, not module names, JSON keys, tests, or active configuration.
- Phase 8 engineering full-suite baseline is 484 passed, 38 skipped on both Python 3.11.15 (215.31s) and 3.12.5 (198.80s). Local supply-chain audit found zero known core vulnerabilities; remote CI remains NOT_EXECUTED.
- Final build backend is pinned to setuptools 83.0.0 and wheel 0.47.0. Binding wheel timestamps to the Git commit epoch produces two identical isolated wheels: 3,218,231 bytes, SHA-256 `2b5a46ff7fad5ed5932f7acc83a18fd2c908137e659f9b0582f6ebc9bb613543`.
- Core, documents, pipeline, and render dependency profiles each passed pip-audit with zero known vulnerabilities. WorkBuddy adds no dependency beyond core. Product-level WorkBuddy E2E, real authorized case-index quality, personal style samples, official CN rules, and remote CI remain explicitly blocked/not executed.

## 2026-07-12 Repo Slimming: Legacy Config Deletion Boundary

- The following top-level config files were deleted with zero live-code references and no active-harness fallout: `configs/base_ontology.yaml`, `configs/domain_corporate.yaml`, `configs/jurisdiction_spec_template.yaml`, `configs/knowledge_layers.yaml`, `configs/obstruction_registry.yaml`, `configs/reasoning_boundary_io_contracts.yaml`.
- `configs/__init__.py`, `configs/core_ontology.yaml`, `configs/L0_overrides_cn.yaml`, and `configs/L0_overrides_hk.yaml` remain live runtime/package resources and are not safe deletion candidates.
- Additional top-level config artifacts can be removed only if the repository is willing to break old audit/tooling chains: `agent_collaboration_protocol.yaml` (agent protocol auditor tests/docs), `domain_mapping.json` (cross-domain test), `juris_blueprint.json` (US lookup + blind reconstruction tooling + config path helper), `juris_contracts.yaml` and `juris_phase_matrix.yaml` (phase runner / KG audit loop / matrix tests), `lexicon_index.json` (distill tool), and `perf_patterns.yaml` (performance baseline/blueprint tools and tests).
