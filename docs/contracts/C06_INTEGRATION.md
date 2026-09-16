# C06 集成：出口契约差距清单与已装适配（jc/c06-integration/1）

本页回答一个问题：juris-calculus 对钉扎的 legal-math-modeling full-release 主体装了哪些消费接口、哪些差距如实保留。面向集成者与维护者；逐条机器锚点在 `compiler_core/math_export/pins.py` 与 `proofs/lmm-fullmath/`，由 `tests/contract/test_c06_math_export.py` 守护。

对端主体（固定，不得漂移）：legal-math-modeling full-release
run `34797682659` attempt 1，commit `5084f25e69ae27332404dc9f341a61d46ef0fc53`，
tree `184a766a2d22b1c4be31bb119e4b82b76f0be540`，
lean_toolchain_sha256 `54727eec…25`，lake_manifest_sha256 `7230ea7e…3e`。
JC 侧 runtime_ref 固定基线：`c79e03b8d0cfed85c43cc013bf8a0b50326bc858`。

出口契约（EXPORT_CONTRACT.json，status `READY_FOR_LATER_INTEGRATION_DESIGN`）
要求 11 项必需接口。逐项差距与本次安装的 JC 侧适配如下；机器可读副本在
`compiler_core/math_export/pins.py`（`EXPORT_INTERFACES`），由
`tests/contract/test_c06_math_export.py` 守护。

| # | 接口 | 数学仓载体（钉扎主体） | 本次之前 JC 差距 | 已装适配 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | formal_input_types | `theory/spec/canonical_semantics.py`（11 个 Canonical* 类型） | JC 只认自家 V4 合同，无对数学侧输入形的声明 | 探针包以规范 rule/fact 形经 V4 intake 进入；接口清单登记载体 | ADAPTED |
| 2 | canonical_codec_and_proof | `FullMath/Core/IdentityCodec.lean`（F02/EXT02） | 无跨仓身份绑定 | 见 #5 与 witness 摘要链 | ADAPTED |
| 3 | reference_checker_entry | `scripts/verify_runtime_refinement_receipt.py` + `theory/spec/runtime_differential.py` | 收据生产只走内部 API，公共入口无见证 | `compiler_core/math_export/checker_gateway.py`（独立子进程，永不导入 JC 求解器）+ `tools/generate_c06_entry_receipts.py` | ADAPTED |
| 4 | exact_inner_outer_and_statistical_contracts | `Representation/SymbolicRepresentation.lean`、`implementation/probability_ref.py` | 无消费路由 | 仅登记载体；不声明消费 | CARRIED_NOT_CONSUMED |
| 5 | supported_grammar | `Document/ByteSyntax.lean`（M13 形式部分） | 无字节语法层对接 | 本地规则包字节语法用于探针；交付语法仍属数学侧 | PARTIAL_PROBE_ONLY |
| 6 | scope_assumptions | `tools/full_math/spec/SCOPE.json` + 逐绑定 external_assumptions | 无机器校验 | `math_export/subject.py` 校验 + `not_established` 逐字携带 | ADAPTED |
| 7 | certified_names_and_subject | `BINDINGS.json`（217）+ subject 七元组 | 旧 lmm-binding 只覆盖 U01 主体（23c5a310），未覆盖 full-math 主体 | `proofs/lmm-fullmath/`（钉扎 MATH_COMPLETION/EXPORT_CONTRACT/BINDINGS_EXTRACT，18 行绑定）+ `math_export/pins.py` | ADAPTED |
| 8 | law_policy_inputs | `LEGAL_FAMILIES_14.json` + `Burden/Families.lean` | 无（真实法源审核未做） | 探针包均为工程测试材料；族策略保留给 B-LEGAL-REVIEW | DEFERRED_EXTERNAL |
| 9 | model_data_inputs | `reference/extended_algorithms.py` 等 | 无（E01 真实数据未做） | 不声明消费；E01 保持未关闭 | DEFERRED_EXTERNAL |
| 10 | counterexamples | BINDINGS negative_test_ids（434 条）+ 反例定理 | 无反向执行通道 | tampered-bundle 探针执行失败封闭方向；完整负例套件留在数学仓 | PARTIAL_PROBE_ONLY |
| 11 | deferred_production_adapters | `DEFERRED_EXTERNAL.json`（5 项） | C06-PRODUCTION 一直 DEFERRED | 本次即 C06 路线；ROOT07/E01/B-LEGAL-REVIEW/X-EXTERNAL-TRUTH 保持打开 | ADAPTED_C06_ONLY |
| 12 | （验收要求）跨仓一致性验证 | full-release run 34797682659 产物 | 无 release 级验证 | `.github/workflows/cross-repo-verification.yml` + `tools/verify_c06_integration.py`，auto-release 以 `needs` 强制 | ADAPTED |

## C06 生产化语义

- 见证 schema：当前 `jc/lmm-c06-witness/1.1`（`math_export/witness.py`），逐次公共入口
  （`jc_client` / `cli` / `mcp`）求值封印，携带数学主体指纹与固定状态映射
  （accepted→PROVED、refuted→REFUTED、非决定→UNDECIDED、失败封闭/拒绝输入→TAINTED）。
  1.1 收紧两条（JC-01/JC-02 回归见 `tests/contract/test_c06_witness_guard.py`）：
  整体运行失败（`engine_error`/`blocked`）或 intake 拒绝不得被局部 accepted 焦点争点
  升级为成功见证（`status_scope` 记录状态来源：intake/run_global_failure/focus_issue/run，
  争点行按各自范围保留）；run 级 `conflict_certificate` 不指名被击败的主张，读
  UNDECIDED，REFUTED 仅来自争点级 `refuted` 行。校验（JC-02）要求完整字段/类型/一致性
  加调用方提供的期望绑定（case/subject/input/result/audit），自摘要不再是充分验证；
  历史 1.0 见证按旧结构规则只读校验并标记 `legacy_structural_needs_review`。
- 探针矩阵：8 案 = LMM materializer 期望状态逐一对应；PIPL 本地生产链（仓内声明的
  test-only 签名材料）覆盖 6 案三入口；无钥匙本地 harness 覆盖 force-majeure（REFUTED，
  经 `ClaimRefutationV5` 准入反驳）与 bounded-undecided 两案两入口（该面 MCP 求值按设计
  fail-closed，记为能力边界，不计语义票）。
- 收据：每案组一份 `spec-runtime-refinement-v2`，与 LMM 独立 checker 的期望 fixture
  （fixture_digest/source/rule pack 绑定）配对；checker 接受 ⇒ 属于钉扎主体该版本的
  独立 Solutions（`Contracts.target_C06`，semantic link
  `JurisLean.FullMath.Composition.checker_correspondence`）。收据同时记录生产者
  `runtime_commit`/`runtime_tree`/`runtime_worktree_dirty`（JC-03）：传入的
  `--runtime-commit` 与实际 HEAD 不符即类型化拒绝，不得借 SHA 冒充。
- 安装物验证（JC-03）：wheel 构建时 `tools/write_dist_origin.py` 在 dist 内写来源清单
  （`jc/dist-origin/1.0`：源 commit/tree/构建时脏状态 + wheel 与 RECORD 摘要）；
  `tools/verify_c06_integration.py --origin-manifest <清单> --installed-report <运行报告>`
  仅凭该清单与 wheel 字节确定身份，不查任何源检出的 git；安装侧探针由
  `tools/run_installed_c06_probe.py` 在仓外环境用安装包执行（JCClient/CLI/控制台脚本/
  进程内 MCP + JC-01/02 守卫复跑），能力边界如实记录。
- 跨入口一致：同一探针经三入口的见证在 schema/status/lmm 指纹/input 摘要/decision/
  issues 上逐字段相等（`math_export/consistency.py`），任何分歧即失败。
- 同主体证据（B-01）：原证据 run `34797682659` 原样保留；最新同主体观察 run
  `35124268367`（2026-09-16 完成，artifact zip sha256
  `d6b571a8…e3cf`）以 `pins.LATEST_EVIDENCE` 单列登记，属追加证据而非重钉，
  语义四元组不变。

## 版本与同一性（B07）

`SubjectCacheKeyV1(commit, tree, lean_toolchain_sha256, lake_manifest_sha256)`
为 JC 侧缓存/证书的数学仓版本键；键相等才命中，任一字段变化即失效
（`version_change_invalidates`，对应 `TARGET:B07` /
`JurisLean.FullMath.Burden.version_change_invalidates`）。绑定行见
`proofs/lmm-fullmath/BINDINGS_EXTRACT.json`（共绑定 18 行：C06、C07、B07、
F02、EXT:EXT02、F05、F08、F09、F10、F12、F14 与 7 根）。

## 诚实边界（不因本次集成关闭）

`MATH_COMPLETION.not_established` 逐字保留：`actual_JC_Harness_integration`、
`E01_real_data_validation`、`truth_of_external_facts`、
`unrestricted_natural_language_or_entire_legal_system`。五项外部义务
（C06-PRODUCTION 之外：ROOT07-PRODUCTION、E01-EMPIRICAL、B-LEGAL-REVIEW、
X-EXTERNAL-TRUTH）维持原状。本集成不伪造任何审批、签章或密钥：生产链探针
仅使用仓内声明为 test-only 的工程测试签名材料；无钥匙面全部
`signature_status=not_used`。

## 页面出口

- 想复核"这批收据此刻是否仍被接受"：跑 `python -B tools/verify_c06_integration.py --lmm-root <legal-math-modeling 检出>`，或看 CI 的 `c06-cross-repo` lane 与 `c06-integration-evidence-*` artifact。
- 想知道外仓边界的完整规则：读[外仓协议](EXTERNAL_PROTOCOL.md)，LMM 行的允许入口即本集成使用的三类通道。
- 想知道发布时这个验证何时强制执行：读[V5 发布流程](../operations/RELEASE_V5.md)的"CI 闭环"（tag 发布先过 `c06-cross-repo`）。
- 想改接口清单或钉扎主体：先读 `compiler_core/math_export/pins.py` 的守护测试——主体换钉是断代事件，不是编辑常量。
