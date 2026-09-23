# Changelog

## Unreleased — plan-v4.2 03 卡期限计算（2026-09-22/23）

- 期限引擎（`compiler_core/deadlines.py`）：`legalResult` 附加投影（rawDue/due/status/capState 等，不进计算摘要 seed）与 `businessCutoff`；民法典194/劳动27 中止分支区分"显式不能行使=False→不成立"与"未知→具名待核"；decision 分支新增闭合词表字段 `noDeadline`/`noDeadlineReason`，输出"确定无普通截止日"的具名候选（有截止日期才 CANDIDATE 的旧词表不变，无截止候选同标 CANDIDATE、不造日期）。
- 规则注册表（`configs/deadline_rules_cn.v1.yaml`，27记录/26ID → 31记录/29唯一ID，RT19 活口钉扎）：行政复议60日、行政诉讼6月、刑法87/89追诉时效四档（`statutoryMaxPenalty` 分档，期限已过 `limitation_cap_review_required`，不输出"不再追诉"实体判定）、民诉95/283公告送达（境内30日/涉外60日）、民诉286涉外上诉（判决裁定均30日）；`labor.arbitration.application` v2 以 noDeadline 表达 27条4款"在职欠薪无普通一年截止"（v1 保留为可选历史版本）。全部经 .gov.cn 官方原文逐字钉扎（登记于上游 jusbench-repo `sources-and-engineering.md` 2026-09-23 增量）。
- 矩阵验收（`tests/unit/test_legal_case_matrix_v42.py`，环境变量 `JUS_LEGAL_MATRIX` 指向上游 `matrix-vectors.json`）：3085 格全经真实 JCClient 逐字段比对、零 skip；适配器只调真实入口，不回填 `test.expected`；`noGeneralOneYearLimit` 等按评审约定为格子维度前提/路由标签。
- 单测：RT07 改钉两版并存行为，RT22–RT24 新增三族规则正算/具名待核/顺延/拒绝适用断言；全仓回归 2122 passed / 1 具名 skip / 0 failed。

## 5.0.2 — procedure-event 公开登记口 (IF-05, 2026-09-19)

- 闭合 U02 wire-gap：`JCClient.register_event` 公开方法（`compiler_core/client.py`）——轻校验（非空字符串 `id`/`matterId`、int≥1 的 `revision`，不满足抛 `schema_invalid`）后经既有 `_register_json("procedure-event", …, scope="case")` 规范登记，返回冻结 wire ref（owner=jc/kind/id=digest.hex/version=1/matterId/digest=sha256:…）。验收链自此走公开口，不再依赖客户端私有 `_register_json`；`_register_json` 本体未改（其余 kind 照旧）。
- 对应 IF-05 合同 v1.2.0；聚焦单测见 `tests/unit/test_computation_surface.py`（wire ref 形状 + `_resolve_json` roundtrip + 缺 id/revision/matterId 各抛 schema_invalid）。

## 5.0.1 — C06 math-export integration (jc-c06-integration, 2026-09-14)

- 消费侧落地 legal-math-modeling full-release 出口契约（固定主体 `5084f25e`，run `34797682659`，READY_FOR_LATER_INTEGRATION_DESIGN）：新增 `compiler_core/math_export/`（钉扎身份、完成文档校验与规范指纹、B07 版本失效指纹 commit+tree+toolchain+manifest、公共入口运行见证 `jc/lmm-c06-witness/1.0` 与保守状态映射、独立 checker 子进程网关、跨入口一致性断言），已进 wheel 并入 module-authority。
- 钉扎与证据入库 `proofs/lmm-fullmath/`：MATH_COMPLETION/EXPORT_CONTRACT 字节拷贝、217 强制注册中 18 行绑定提取（C06/C07/B07/F02/EXT02/F05/F08/F09/F10/F12/F14 + 七根）、LMM materializer 期望 fixture、集成证据 JSON；`.gitignore` 为 `proofs/lmm-fullmath/*.json` 开白名单。
- 跨仓验证可执行化：`tools/build_lmm_fullmath_pins.py`（钉扎生成）、`tools/generate_c06_entry_receipts.py`（8 探针 × JCClient/CLI/MCP 三入口 → 见证 + `spec-runtime-refinement-v2` 收据）、`tools/verify_c06_integration.py`（身份复现 → 期望再生成字节比对 → 收据生产 → LMM 独立 checker → 证据 JSON）；新增 `.github/workflows/cross-repo-verification.yml`（call/dispatch），`auto-release.yml` promote 前置 `c06-cross-repo`，`ci.yml` 增加 C06 合同/工作流/集成测试步骤与 dispatch 门控跨仓 lane。CI run 34877978619 全绿，跨仓 lane 以固定 ref 实跑通过（三组收据 passed=true、8 案跨入口一致、`changed_module_mode_used=false`），证据 artifact `c06-integration-evidence-34877978619-1`。
- `local_runtime.build_bundle` 的 `query_refutations` 接受 `(refuter_rule_id, target_rule_id)` 规则对并构造 `ClaimRefutationV5`（basis=本包规则派生摘要）——已准入反驳关系首次经本地公共面可达（force-majeure REFUTED 探针）。
- 修复三个既有缺陷：`tools/wheel_gate.py` 只展开 path_rules 导致 prefix 型生产包（business_root/math_export）从不进 wheel——package lane 首次实跑即挂，现按 production prefix 规则展开（wheel 62 项）；`test_bc28` 内容寻址记录含 `verified_at` 在慢 runner 跨秒 flaky——该测冻结时钟；wheel 输入不变量单测与 gate 保持镜像。
- 诚实边界逐字保留：`actual_JC_Harness_integration`、`E01_real_data_validation`、`truth_of_external_facts`、`unrestricted_natural_language_or_entire_legal_system`；跨仓主张仅限 checker correspondence（C06）与版本失效（B07）；ROOT07/E01/B-LEGAL-REVIEW/X-EXTERNAL-TRUTH 维持原状。契约页见 `docs/contracts/C06_INTEGRATION.md`。

## 5.0.1 — jc-business-root/1 first batch (ROUTE1, 2026-09-11)

- 新增 `compiler_core/business_root/`（codec/spec/solver/checker/analytics/delivery_checker/wire）：有限情景条件本金的生产实现，solver/checker 双枚举双语义（栈机+位掩码）、逐情景守恒律 C≥0、U≥0、C·U=0、C−U+recognized==principal，analytics 独立重算 E[C]/E[U]/E[R]/阈值事件/合法格。移植自 LMM reference @88644bc（MIT），数学权威仍在 LMM，Lean kernelChecked 证据待其 CI。
- 请求扩展 `CaseRequestV4.business_tasks_v1` 与结果扩展 `SemanticResultV4.business_results_v1`：省空序列化——为空时整体不出现在规范字节中，旧请求/旧密封 run 的规范摘要逐字节不变（向量钉扎）。
- 业务类型入注册表（106→124）：BusinessContextV1 等 18 个封闭合同；schema/manifest/向量/状态矩阵再生成。
- Application 业务阶段：business-only 注册路由（不造假规则/claim，decision=hypothetical_result、review 门控、无证书）；逐任务五态 completion（exact/partial/inconsistent/failed/unsupported）与 typed error_code/error_stage；I0 与见证工件随审计包密封；混合请求业务行附加终局结果、与规范结果互不冲销。
- 公开 verify-only 面：`business_delivery_documents`（从已核 run 只读导出两份受保护文件字节）与 `verify_business_delivery`（恢复密封 I0/结果、校验 selection 绑定、严格解析实际 bytes、登记内容寻址交付记录；全程零求值）；`business_capabilities()` 能力查询。
- 本地 runtime builder 接收 `business_tasks`；可运行样例 `examples/harness/sample_local_business.py`；wheel 打入业务实现（pyproject + module-authority FORMAL_CORE 登记）；CI 增加业务验收步（contract+local+仓外 wheel 安装）。
- 验收：tests/contract/test_business_root.py（BC01-BC03/BC10/BC16）、tests/local/test_business_root_local.py（BC04/05/07/09/11/13-16/18/19/22-25/28/29/33/36）、tests/packaging/test_business_wheel_install.py（BC12）；施工报告与未关闭清单见 docs/ulm-consolidated/IMPLEMENTATION_HANDOFF.md。

## 5.0.1 — final remediation (JC-FINAL-FIX-20260908)

- 分支身份改为结构化无分隔符编码：`compose_branch_key_v5` 返回排序数组组件并对规范化结构取摘要，`{"a","b"}` 与 `{"a|b"}`、`("x","y")` 与 `("x|y",)` 不再可能共享身份（FIX-01/B01–B03）。
- 查询反驳统一为 argument → conclusion → 有向反驳关系：`common_refuted`/`possibly_refuted` 由同一逐分支布尔量聚合，论证改名不再改变语义；`QueryResultV5` 合同允许合法 `gate=excluded, excluded=true`，`inconsistent_some` 改为存在语义（FIX-02/C01–C06）。反驳关系与分支门从公开请求（`query_refutations_v5`/`query_gates_v5`）进入查询阶段，跨请求或未知引用被拒。
- solver 预算耗尽在 Application→procedure/assurance 边界统一转换为 `OpenObligationEntryV5`：17 论证 preferred 请求经公开入口返回 `solver_incomplete` + 非空义务 + `completeness=partial`，不再是 `TYPE_MISMATCH`（FIX-03/D01–D02）。
- 优先关系语义落位：已准入 priority 通过登记策略（`target-preferred-rebut/1`，工程测试策略）参与击败判定并留下逐边处置记录；无策略/未知策略/策略不可解的循环进入正式映射覆盖缺口——查询 gate=incomplete、程序保持待判、保证信封 openObligations、顶层 partial、不签发证书；阶段内独立复核拒绝错误映射（FIX-04/E01–E06）。
- 真增量默认启用：`horn-subject-state-v5` 阶段对合格 add-only 子请求以工作队列从父闭包推进增量（复用经密封审计包跨实例恢复），solver/checker 工作量分别计量，增量与强制全量结果等价，非单调变化自动回退并记录原因，错误传播 fail-closed（FIX-05/F01–F11）。
- 程序四路全部可达：`procedural_input_v5` 公开输入驱动 adjudicated_status / procedural_disposition / pending_legal_judgment / solver_incomplete；授权只能由 trust 校验的已存法律签章产生，用户自报布尔永不生效（FIX-06/G01）。
- 新增封闭 Harness 集成合同 `compiler_core/harness_contract.py`（`jc-harness-contract/1`）与三份可运行样本（`examples/harness/`）；接口文档 `docs/contracts/HARNESS_INTEGRATION.md`。
- 合同注册表扩至 105 类型；合成包新增 constitutive Horn 规则族与 15 条预算扩展规则（观察隔离）；schema/manifest/向量再生成。

## 5.0.0 — V5 upgrade (JC-UPGRADE-20260906-01, released 2026-09-07)

- 2026-09-07：tag `v5.0.0` 签名发布——CI run 34150936429 全绿，promote 任务以生产 Ed25519 密钥完成签名并创建 GitHub Release；provenance `BYTE_IDENTICAL_REBUILD`，绑定源提交 `12d4ddd`。`production_release_claimed=false` 保持设计语义：生产采用（部署激活）是宿主的显式决定。
- 2026-09-07：独立核查（对象为固定提交 `7b75b42`）三项阻断修复——stable 攻击方向、定义驱动独立语义校验器、V5 新能力接入唯一正式主链（详见归档报告 `docs/archive/FINAL_UPGRADE_REPORT.md` §八）。

- 公共协议升级为 `jc/5.0`，引擎 major 锁定为 5；正式输入拒绝 `jc/4.0` 与 4.x 引擎版本。
- `compiler_core/contracts.py` 新增 25 个 V5 封闭对象组（情景/查询、前提、结构化论证、七类攻击与 defeat 策略、扩展族与三态求解结果、分支、程序四路输出、量纲精确表达式、组合选择、保证信封、增量 delta、只读经验结果），注册表扩至 100 个类型。
- 证明依据落库：`proofs/lmm-binding.json`、`proofs/runtime-obligation-map.json`（91 模块 / 452 声明全部处置）。
- 修复 Windows 长路径（>260 字符）下 storage/审计包写入、`icacls` 加固与 DACL 校验失败的问题；修复 `icacls /setowner` 在继承 DACL 仅授予 Modify 的卷上的假阳性失败。
- remediation runner 失败命令的完整 stdout/stderr/argv 保全到 `<log>-failed-output/`；CI 无论成败上传运行证据。
- schema 出版物更名为 `schemas/jc-v5.schema.json` 并随注册表再生；`mcp_manifest.json` 同步再生。

## 4.0.0 — Current V4

- CLI、Python、MCP、schema、application、certificate、verify 与 replay 统一到 V4。
- 删除 23 个零消费者旧模块、旧 pipeline 导入 shim、旧 runner 验证器和旧施工状态文档。
- remediation runner 改为小型通用 DAG 执行器，当前使用 3.0 任务定义；2.0 任务定义保持原字节不变。
- 正式 wheel 新增独立 `rule_admission.py`，完整支持 official YAML 规则准入正反验证。
- 生产链测试改为在 pytest 临时目录内生成材料；Git/子进程边界统一使用严格 UTF-8。
- 当前 authority 检查使用 Git 跟踪清单、本地 AST、入口点和 wheel 清单，不依赖外部 CodeGraph。
- CN/HK/US/federation addons 保留用于规则对齐，继续排除在正式 wheel 之外。
- CI 改用当前 V4 runner、authority、cleanup、文档链接、完整测试和隔离 wheel 门禁。

本版本条目只描述当前仓库可复现内容，不声明外部部署、远程发布或历史任务完成状态。
