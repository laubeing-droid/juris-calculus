# juris-calculus V4 单主链全量切换与生产投产施工方案

> **已归档：** 本文仅保留历史规划与施工上下文，不描述当前运行状态。当前信息见[状态页](remediation/v4/STATUS.md)与[文档索引](docs/README.md)。

> 日期：2026-08-19
> 审计基线：`main@6f4f91a67047d0beef0ed43acf55d3a2b3803015`
> 当前结论：**No-Go。当前产品主链仍是 V3，V4 是未接入公共入口的旁路原型。**
> 本方案取代根目录 `20260815_juris-calculus理论成果全量吸收施工方案.md` 中保留 V3/W1b/compat 的施工条款。

## 0. 已锁定决策

1. 当前源码、公共 API、CLI、Python Client、MCP、Schema、测试、wheel、审计包、正式规则包和发布身份全部切换为 V4。
2. 不保留 V3/W1b 运行时兼容、adapter、自动升级、隐式 fallback、双写或双 authority。
3. 历史 V3 复现仅使用冻结的 `v3.0.2` tag、旧 wheel、旧 lock 和隔离环境；V4 进程明确拒绝 V3 输入和 V3 bundle。
4. 施工顺序固定为：**V4 单主链闭合 → 正式 `cn-official` → DSH formal profile/plugin**。
5. candidate、教材蒸馏、旧法域配置、三轨、训练、策略、类案等资产不因无法支持正式结论而丢弃；它们迁出 formal core、默认 wheel 和正式 registry。
6. `4.0.0-rc.*` 只能表示 V4 内核已闭合；只有真实、签名、可重放的 `cn-official` 至少一个完整领域通过后，才允许发布 `4.0.0` 并宣称具备正式法律生产能力。
7. DSH 的通用即插即用不受影响；只有其 formal legal profile 对 JC V4 建立硬依赖。JC 缺失或 readiness 不成立时，formal profile 拒绝激活，DSH 的 general/advisory 能力仍可运行但不得产出 JC formal certificate。

## 1. 本次“投入生产”的定义

### 1.1 两级终态

| 终态 | 必须成立 | 禁止宣称 |
|---|---|---|
| V4 Kernel RC | V4-only 合同和主链闭合；合成签名 official test pack 正向/负向 E2E；wheel、审计、回放、并发、供应链门禁通过 | 不得称可输出中国法正式结论 |
| V4 Legal Production | 上述全部成立；真实 `cn-official` 完整领域通过法源、规则、审批、签名、变异、回放和 installed-wheel E2E；运维存储和信任根就绪 | 不得用 candidate、测试 pack 或 review receipt 冒充正式法律能力 |

### 1.2 V4 主链唯一拓扑

```text
CLI / JCClient / formal MCP
             |
             v
       CaseRequestV4 parser
             |
             v
   ArtifactResolver + TrustPolicy
             |
             v
 source gate -> evidence gate -> fact admission
             |
             v
 signed official pack -> RuleV4 -> LegalSpec -> LegalIVL
             |
             v
 certified backend -> independent checker -> argument resolution
             |
             v
 SemanticResultV4 -> FormalCertificateV4 -> AuditBundleV4
             |
             v
 atomic store -> verify -> offline replay -> bounded artifact handle
```

任何模块不得绕过 `ApplicationV4` 直接构造 gate PASS、solver/checker receipt、formal result、certificate 或 COMPLETE。

## 2. 审计覆盖与事实基线

### 2.1 全仓覆盖

固定快照共 291 个 tracked 文件、约 15.8 MB blob；本方案逐区处置如下。

| 区域 | 文件数 | 当前角色 | 本方案动作 |
|---|---:|---|---|
| `compiler_core/` | 90 | V3 主链、V4 原型、advisory/compat 混装 | 收敛为 V4 formal core；其余吸收、删除或外迁 |
| `tests/` | 90 | 69 个 unit 文件、2 个根脚本、19 个其他项/fixtures；无 integration/e2e | 重建 V4 unit/integration/e2e/chaos/security/installed-wheel 分层 |
| `configs/` | 38 | candidate/legacy、私域三轨、renderer、空 `cn-official` 混装 | core wheel 清空法律语料；正式 pack 独立签名分发；candidate 外迁 |
| `docs/` | 18 | V3、W1b、V4 staged、当前事实互相冲突 | 重写 current docs；历史由 Git tag 保存，不参与当前 authority |
| `pipeline/` | 11 | 案卷扫描、外部 LLM、规则改写、候选处理 | 整体退出 formal core/wheel；危险原地改写器删除 |
| `addons/` | 10 | WorkBuddy V3 MCP、CN/HK/US legacy plugin | formal MCP 重写并移出 addons；法域 addons 外迁 |
| `schemas/` | 7 | V3、V4、W1b 三套合同 | 只保留生成的完整 `jc-v4.schema.json` |
| `tools/` | 7 | build/pack/perf/supply-chain 与私域工具混装 | 保留并重写生产工具；三轨/实验工具外迁 |
| `requirements/` | 5 | 仅 core lock 有 hashes | 生产、构建和被发布 profile 全量传递锁定 |
| `.github/workflows/` | 2 | 源码测试较完整，release 身份/制品不足 | 重建不可变 build→attest→promote 流程 |
| 根目录 | 13 | 版本、README、HANDOFF、memory、MCP、旧计划漂移 | 一次性切到 V4 current-state 口径 |

### 2.2 当前 P0 证据

| P0 | 直接证据 | 生产影响 |
|---|---|---|
| V4 不在生产调用图 | `compiler_core/cli.py:24`、`compiler_core/client.py:16`、`compiler_core/application.py:14-25`、`compiler_core/audit_bundle.py:17`、`addons/workbuddy_mcp.py:14` 均导入 V3 contracts；V4 模块仅被单测或彼此局部导入 | 无法把 staged 类存在等同主链完成 |
| V4 接受 V3 引擎 | `compiler_core/contracts_v4.py:411-418` 只拒绝 major `<3`；`tests/unit/test_contracts_v4.py:147-151` 明确放行 `3.0.2` | Schema/engine 身份可错配 |
| 摘要文法互斥 | `compiler_core/jcs.py:125-126` 产出 `sha256-`；`compiler_core/contracts_v4.py:66` 接受裸 hex/`sha256:`；source/fact/backend/certificate 多处只收 `sha256:` | request、identity、receipt、bundle 无法闭合互引 |
| Python/Schema parser 不等价 | `compiler_core/contracts_v4.py:255-265,384-401` 会先对字段 `tuple(...)`，字符串可能被拆成字符序列；`compiler_core/contracts_v4.py:130-138` 又不递归 list/tuple 检查 float | 不同入口可接受不同非法输入 |
| V4 Schema 仅是外壳 | `schemas/jc-v4.schema.json:6-9,140-150` 仅覆盖 request/result，resolution、temporal、run identity 为开放 object | 未知字段和第二语义通道无法阻断 |
| source/fact 信任可自报 | `compiler_core/source_service_v2.py:416-432` 不读真实字节或验签；`compiler_core/fact_admission_v1.py:224-237,297-348` 可覆盖 attestation、由调用者传 GateOutcome | 外部能伪造“已验证” |
| RulePlatform 是内存模拟器 | `compiler_core/rule_platform_cn.py:216-264` 以 bool/角色字符串/自造 receipt 激活 domain | 无真实 build、review、release 或 pack 绑定 |
| backend/IR/receipt 自证 | `compiler_core/backend_router_v1.py:92-124` 仅路由 feature；`compiler_core/legal_spec_ivl.py:228-309` 丢字段却写 PASS；`compiler_core/certificate_v1.py:250-313` 信 caller-supplied gate/receipt | 不能构成独立证明链 |
| V3 语义会在直切时丢失 | `compiler_core/contracts.py:852-909` 和 `compiler_core/application.py:628-751` 承载 claims、branches、missing review、taint、checker、certificate、状态矩阵；当前 `SemanticResultV4` 无等价完整字段 | 直接替换 parser 会弱化 fail-closed |
| formal/advisory 权威冲突 | `compiler_core/application.py:26,29` 正式链依赖被 registry 标为 ADVISORY 的 `domain_config`、`litigation_engineering`；两套 module registry 又冲突 | 标签不等于边界，审计不可相信 |
| MCP 仍是 V3 且任意读路径 | `addons/workbuddy_mcp.py:211-216,257-265,459-470`；`mcp_manifest.json:6-115` | DSH/模型可提交宿主路径；formal/advisory 混装 |
| MCP 错误被标成功 | `addons/workbuddy_mcp.py:220,342`：engine_error 不等于 `status=error`，故 `isError=false` | 调用方可能把引擎失败当工具成功 |
| cn-official 不产出 | `configs/packs/cn-official/manifest.yaml:1-18` 为 3.0.2、blocked、0 条；四个 legacy pack 共 21,481 条且 eligible 全为 0 | 当前无法证明任何 public formal-success |
| pack 信任只验形状 | `compiler_core/rule_packs.py:194-215,414-437,505-527` 仍走 V3 loader；build attestation 只验 hex；source verified/hash 不回读原件 | manifest 自声明可冒充信任 |
| 审计存储不具并发恢复 | `compiler_core/audit_bundle.py:224-250,448-502,562-577` 固定 staging、无仲裁、残留目录永久阻断、未 fsync 父目录 | 同 run/pack 并发和崩溃后不幂等 |
| Windows 隐私门禁缺失 | `compiler_core/audit_bundle.py:78-107,580-585` 仅报告 `acl_verified=false`，只在 POSIX chmod；bundle 仍含结构化事实 | 正式数据存储能力未证明 |
| wheel 混装全仓 | `pyproject.toml:39-46` 打入 `compiler_core*`、`addons*`、`pipeline*`、`configs*`、`schemas*` | 私域、candidate、外部 LLM、规则改写器进入产品面 |
| 发布身份失真 | `compiler_core/version.py:3` 仍为 3.0.2；`CHANGELOG.md:3` 称 Unreleased；当前 HEAD 比 `v3.0.2` 多 21 commits | source/tag/wheel/运行身份不可对应 |
| wheel/release gate 不足 | `tools/wheel_gate.py:19-84` 只查少量禁用模块和 MCP smoke；`.github/workflows/auto-release.yml:35-75` 不 build/attest/附 wheel | 不能证明发布制品就是通过测试的 V4 |

### 2.3 当前测试和数据边界

- 静态清册有 71 个 Python 测试文件、496 个 `test_` 定义；只有 `tests/unit` 与 fixtures，没有 tracked integration/e2e 目录。
- `tests/unit/test_adversarial.py:12`、`tests/unit/test_trirail_collision.py:15`、`tests/unit/test_zh_rules.py:16` 整文件 skip，共 28 个用例不进门禁。
- `tests/unit/test_contracts_v4.py:199-233` 只比 Python/Schema 字段和枚举，没有用 JSON Schema validator；`compiler_core/contracts_v4.py:130-138` 又未递归检查 list/tuple 中的 float。
- `configs/zh_CN/source_manifest.yaml:2-76` 用 `verified:true` 标教材和法典，但没有可解析原始字节、内容 hash、版本、locator、许可或再分发记录。
- [中等] (50-80%) 候选语料存在出处和分发许可风险；当前仓库不足以判断权利状态。未建立合法复用记录前，禁止进入 official pack 或 core wheel。
- 本方案未核验 21,481 条 candidate 的实体法律正确性；它们不是本次 V4 系统施工的真值集。

### 2.4 P01-P09 当前生产可达性

当前 production import graph 中九门可达数为 0/9；文件/测试存在不算 runtime consumption。

| 门 | 当前状态 | 目标波次 |
|---|---|---|
| P01 Human research/approval | 仅方案、fixture 或无结构 kind；未进入 application | S1/S2 trust 与 typed receipt；S8 真实审批 |
| P02 Source snapshot/evidence | `source_service_v2.py` 孤立 | S2 |
| P03 Typed argumentation | `argumentation_v2.py` 仅单测；生产用旧 argumentation | S3 |
| P04 Backend/solver | 只有 feature router/receipt dataclass，无 executor | S3 |
| P05 Proposal envelope | V4 只有字符串 `proposal_refs` | S1/S2 |
| P06 Temporal applicability | staged gate 未进入主链 | S2/S3 |
| P07 LegalSpec→LegalIVL | 孤立单规则 compiler/differential | S3 |
| P08 Source path | 孤立对象和单测，终点受 edge 顺序影响 | S2 |
| P09 Fact admission | 孤立内存 service；生产仍用 V3 fact status | S2 |

## 3. 不可妥协的不变量

### 3.1 Authority

1. `compiler_core/contracts.py` 是 V4 Python wire contract 唯一源；`schemas/jc-v4.schema.json` 和 `mcp_manifest.json` 由其确定性生成，禁止手改生成物。
2. 一个机器可读 `docs/architecture/module-authority.json` 描述当前 module class、允许入边和消费者；删除另外两套 registry。
3. public entrypoint 只有 `ApplicationV4`；CLI、Client、MCP 只负责 I/O、错误映射和传递，不实现法律求值、准入或兼容。
4. external payload 只能提交待验证数据和 opaque/content-addressed refs，不能提交 `GateOutcome`、PASS、solver/checker receipt、certificate 或 active 状态。
5. formal 和 advisory 物理分离：不同 package/wheel、不同 MCP server/tool list、不同 registry；advisory 永远不能签 formal certificate。

### 3.2 V4-only

1. V4 当前源码和 wheel 中不存在 `compat_v3_v4.py`、`legal_ir_v3.py`、`jc-v3.schema.json`、`schemas/w1b/` 及其测试/fixture。
2. V3 payload 一律返回 `UNSUPPORTED_SCHEMA_VERSION`；不猜测、不转换、不补默认字段。
3. V4 内部模块不再使用 `_v1`/`_v2`/`_v3` 文件名制造并行代际；包版本已定义当前内部实现代际。公开对象可保留 `V4` 后缀以显式标识 wire contract。
4. 施工分支允许在未发布状态下暂存旧文件，但 cutover commit 必须同时切换全部入口并删除旧 authority；任何中间 commit 不得发布或合入 production branch。

### 3.3 Fail closed

1. formal result 必须由 JC 内部重新计算所有 gate，且每项 receipt 的 subject digest 精确绑定本次 request、source/evidence、pack、result、run identity。
2. candidate、unknown key、过期/撤销 receipt、未认证存储、unsupported semantics、solver/checker disagreement、translation loss、incomplete bundle 均不能生成 formal certificate。
3. 失败不能静默降级到旧 evaluator、advisory、candidate pack、默认法域、默认配置或普通工具成功。
4. “文件存在”“字段非空”“64 位 hex”“角色字符串”“测试类通过”均不构成信任证明。

### 3.4 Determinism and privacy

1. semantic bytes 只由 schema-validated 数据决定；墙钟时间、pid、绝对路径、随机 staging 名、日志顺序不进入 semantic digest。
2. 金额统一用整数最小货币单位；比例用整数 numerator/denominator；wire contract 禁止 float。
3. 原始案卷、叙述性文本、密钥、token、机器路径不进入 stdout/stderr、events、certificate、manifest 或默认 audit bundle。
4. state provider 必须声明并证明路径隔离、权限、加密、容量、retention、legal hold、清除和恢复能力；production mode 对能力缺失直接拒绝启动。

## 4. V4 合同闭合设计

### 4.1 唯一摘要和规范化规则

| 项目 | V4 决定 |
|---|---|
| 摘要文法 | 只允许 `sha256:<64 lowercase hex>` |
| 摘要类型 | 单一不可变 `DigestV4`；禁止任意 string 代替 digest |
| JSON 规范化 | RFC 8785 JCS；顶层 object/array；禁止 float、NaN、Infinity、重复 key |
| 文本规范化 | source 原文 hash 对原始 bytes；normalized hash 对明确版本化 profile 的输出；JCS 本身不偷偷改 Unicode |
| subject binding | receipt 对 `kind + schema_version + subject_digest + issuer + policy_digest` 的 canonical payload 签名 |
| run identity | request、engine/wheel/tree、schema、ToolSpec、pack、trust policy、algorithm profile、lock digest 全部绑定 |
| 观测数据 | started/finished time、host、pid、性能指标放 observability envelope，不进入 semantic result digest |

删除 `jcs.py` 与 `canonical_serialization.py` 的双实现；保留一个通过 RFC 官方向量、Unicode/排序/整数边界测试的实现。所有 hash helper 只能调用该实现。

### 4.2 完整公开对象集

`schemas/jc-v4.schema.json` 的 `$defs` 至少覆盖下列全部对象，且 `additionalProperties:false`：

- `DigestV4`、`CanonicalTimeV4`、`ContentRefV4`、`ArtifactHandleV4`、`ErrorV4`；
- `SignatureEnvelopeV4`、`TrustPolicyV4`、`StorageCapabilityV4`、`ObservabilityEnvelopeV4`；
- `CaseRequestV4`、`LegalContextV4`、`RequestedOutputV4`、`ResourceLimitsV4`；
- `SourceSnapshotV4`、`CanonicalLocatorV4`、`SourceVersionEdgeV4`、`SourceBundleV4`；
- `EvidenceManifestV4`、`EvidenceItemV4`、`ContradictionRefV4`；
- `FactCandidateV4`、`FactAttestationV4`、`FactAdmissionReceiptV4`；
- `RuleV4`、`PackManifestV4`、`PackSignatureV4`、`RulePromotionReceiptV4`；
- `LegalSpecV4`、`LegalIVLV4`、`TranslationReceiptV4`；
- `ArgumentV4`、`AttackV4`、`PriorityEdgeV4`、`PermissionResolutionV4`、`ExceptionResolutionV4`；
- `BackendInvocationV4`、`SolverReceiptV4`、`CheckerReceiptV4`、`ProofReceiptV4`；
- `ExecutionStatusV4`、`DecisionStatusV4`、`ReviewStateV4`、`RuntimeProfileV4`；
- `ClaimResultV4`、`BranchResultV4`、`MissingFactRequirementV4`、`SemanticResultV4`；
- `RunIdentityV4`、`FormalCertificateV4`、`ConflictCertificateV4`、`CertificateEnvelopeV4`；
- `AuditManifestV4`、`AuditBundleIndexV4`、`EvaluationEnvelopeV4`、`VerificationResultV4`、`ReplayResultV4`；
- MCP 四个 tools 的 input/output/error envelope 和生成式 `ToolSpecV4`。

禁止开放 Mapping 作为正式扩展槽。确需扩展时使用具名、版本化、枚举受限的 union，并在 minor schema 兼容矩阵中登记。

### 4.3 输入资源边界

在解析 JSON 前检查字节上限；解析后检查深度、字符串长度、数组长度、总引用数、控制字符和数字类型。限值写入单一 `ENGINE_LIMITS_V4`，由 schema、Python parser、CLI、MCP 和 capabilities 共同生成/公布。W0 用攻击面与基准确定数值，未批准限值不得进入 RC。

文件路径不是 wire contract。CLI 仅允许 `stdin` 或显式本地文件，由 CLI 自己在受控边界读取；MCP 只接受结构化 object 或 JC 签发的 opaque ref。任何 absolute、UNC、device path、`..`、symlink escape 都不能进入 formal resolver。

## 5. V3 → V4 信息守恒，不等于兼容

删除 V3 代码前，先把其仍正确的产品语义改写成 V4 测试和 typed fields。该过程不提供 V3 parser，也不接受 V3 payload。

| 现有 V3 语义 | V4 落点 | 强化要求 |
|---|---|---|
| `execution_status` | `ExecutionStatusV4` | 增加 unsupported、resource_exhausted、cancelled；与 decision status 正交 |
| `result_status` | `DecisionStatusV4` | 保留 formal/hypothetical/review/missing/conflict/unknown/engine_error；增加 pre-evaluation blocked |
| `formal_kernel_used` | `RuntimeProfileV4` + backend receipt | 由实际 provider/build 推导，调用者不能传 bool |
| `review_required` | `ReviewStateV4` | 给出具体 unresolved item、责任角色和解除条件 |
| `checker_accepted` | `CheckerReceiptV4` | 重新计算且绑定 IR/result；不保存裸 bool 作为 authority |
| `certificate_kind` | typed certificate union | formal、conflict、none 状态矩阵闭合 |
| `claims` | `ClaimResultV4[]` | 每个结论绑定 arguments、facts、rules、sources、label、proof/checker refs |
| `branches` | `BranchResultV4[]` | 绑定 assumption set 和 branch digest；分支结果不得升级整体 formal |
| `used_fact_ids` | admitted fact content refs | 绑定 proposition/value/attestation/source/evidence digest |
| `used_rule_ids` | RuleV4 content refs | 绑定签名 pack、source locator、effective interval 和 promotion receipt |
| `source_ids` | SourceSnapshotV4 refs | 从真实 bytes 重算 raw/normalized hash并验签 |
| `missing_fact_ids/review` | `MissingFactRequirementV4[]` | 保留 impacted rules/claims、允许答案类型、所需来源和优先级 |
| `taint/risk_labels` | typed taint/risk code | 传播规则机器可验；禁止自由文本决定 formal gate |
| `checker_receipt` | `CheckerReceiptV4` | subject/build/algorithm/input/output digest 完整绑定 |
| pack id/version/digest | `PackManifestV4` ref | pack 独立版本；运行时验签；active 为推导状态 |
| `run_id/result_digest` | `RunIdentityV4` + typed digests | 绑定 wheel/tree/schema/tool/pack/trust/lock，而非仅 engine version |

### 5.1 终态矩阵

| Decision status | 必须条件 | Certificate | Transport |
|---|---|---|---|
| `accepted_formal_result` | execution completed、completeness complete、非空 typed conclusion、全部内部 gate/checker 通过、signed active pack、零 translation loss/taint/candidate | `FormalCertificateV4` 必须存在且验签 | 成功 |
| `hypothetical_result` | assumptions 非空且逐项显式；不可混入 admitted fact | none | 成功、明确非正式 |
| `review_only_result` | unresolved review items 非空 | none | 成功、明确非正式 |
| `missing_required_fact` | missing requirements 非空并绑定受影响规则/结论 | none | 成功、允许上游补材料 |
| `conflict_certificate` | conflict witnesses、攻击/优先级/permission resolution 完整 | 仅 conflict certificate | 成功、明确无正式单一结论 |
| `unknown` | 求值完成但语义不足，reason code 非空 | none | 成功、明确非正式 |
| `blocked` | source/fact/pack/trust/storage/unsupported gate 在求值前失败 | none | CLI admission code / MCP `isError=true` / Client typed exception |
| `engine_error` | 内部未预期故障；不得携带 accepted claims | none | CLI engine code / MCP `isError=true` / Client typed exception |

`review_only`、`missing_required_fact`、`conflict_certificate` 是合法语义结果，不应被 transport 当崩溃；schema、trust、pack、storage、engine 失败必须是 transport error。三入口共用同一错误映射表。

## 6. 信任、来源、事实和规则

### 6.1 ArtifactResolver

新增 V4 content-addressed resolver，职责只有：按 typed ref 取受控 bytes、限制大小/类型、重算 digest、验证 scope、返回不可变材料。它不读取调用者给出的任意路径，不自动联网，不搜索“最像”的材料。

同 ID 同 digest 注册必须幂等；同 ID 异 digest 必须报 collision。任何 silent overwrite、silent dedup、最后一项胜出均删除。

### 6.2 TrustPolicy and signatures

1. V4 production trust policy 只允许 Ed25519 签名；canonical payload 使用统一 JCS。
2. runtime 只包含 verifier 和公钥/策略引用；私钥不进入仓库、wheel、环境样例或 audit bundle。
3. trust policy 定义 key id、issuer、role、scope、validity、revocation、allowed artifact kind 和 policy digest。
4. source authenticity、human/legal/engineering approval、pack release、service certificate 分开签发，禁止一个角色跨 scope 授权。
5. 未知 key、过期、撤销、scope/subject 不符、签名 bit flip 全部 fail closed。
6. 发布供应链 attestation 与 JC 法律/审批签名分离；普通 SHA-256 摘要不得再称“签名证明”。

正式 runtime 增加并锁定成熟的 Ed25519 verifier 依赖；依赖选择、license、wheel availability 和 hashes 在 W0 完成，未通过供应链 gate 不开工签名链。

### 6.3 SourceSnapshotV4

每个 snapshot 必须绑定：法源身份、jurisdiction、authority tier、issuer、公布/生效/失效时间、原始 bytes digest、规范化 profile/digest、结构化 locator、版本前后关系、真实性 receipt、取得方式和许可/分发状态。

版本图必须满足：节点 digest 唯一、同一法源身份、无环、时间单调、前后关系一致；请求使用的 root→terminal 路径必须连通且 terminal 明确，禁止以数组最后一项替代拓扑验证。

### 6.4 FactAdmissionV4

事实准入只消费已验证 source/evidence、typed fact candidate 和具权限 attestation。attestation 签名 subject 至少绑定 request/case scope、proposition digest、value、source/evidence digest、issuer role、validity、nonce/replay policy。

replay 规则：相同内容在相同 scope 重试返回同一结果；跨 scope 或异内容复用 receipt 失败。不得用进程内 mutable set 破坏 deterministic offline replay。

### 6.5 RuleV4 and PackManifestV4

`RuleV4` 至少包含：rule digest、jurisdiction/governing law、typed variables、premise/conclusion、modality、permission、exception、priority/attack、temporal/numeric semantics、source snapshot/locator、interpretation choices、promotion receipts 和 effective interval。

`PackManifestV4` 绑定：pack 独立版本、engine API compatibility、全部 rule/source/config/receipt digest、compiler build、source tree、schema、trust policy、coverage/verification receipts 和 release signature。`active` 不存为可手改 bool，而由 runtime 验签和完整性检查推导。

candidate pack 只能进入 corpus/review 流程；任何 development override 都不能进入 formal application。一个候选或三个自报角色不能激活整个 domain。

## 7. 语义执行、IR、后端和独立校验

### 7.1 双 IR

`RuleV4 → LegalSpecV4 → LegalIVLV4` 每跳必须：

- 解析、类型检查、序列化、digest 各自独立；
- 输出 exhaustive field coverage；任何 lost/defaulted/unsupported field 进入 formal path 即失败；
- interpretation choice 显式且绑定审批 receipt；
- translation receipt 由框架从 canonical before/after 自动计算，调用者不能传 PASS；
- direct oracle 与 lowered evaluator 不共享被测转换代码。

### 7.2 ArgumentationV4

重写并统一旧 `argumentation.py` 与 `argumentation_v2.py`：priority 必须实际改变 defeat relation；permission 必须有 holds/does_not_hold/disputed 三个可达且有 witness 的状态；exception、rebuttal、undercut 类型闭合。

self attack、mutual attack、priority cycle、duplicate claim/multiple arguments、UNDEC、disconnected graph 和快路/全路 projection 必须有同一 reference oracle。任何 UNDEC 不得被 graph state 粗略标为 accepted。

### 7.3 BackendRouterV4

router 只能从 validated LegalIVL 自动提取 features，外部不能提交 `ProblemFeatures`。每个 provider 实现统一接口并登记 certified semantics、limits、build digest、proof/checker 能力。

首个 V4 RC 只启用已通过独立 conformance 的 provider：Horn/fixpoint、AAF grounded、整数/有理数/日历 closed-form。SMT/ASP provider 未具真实 solver、proof/model checker 和 pinned runtime 前保持 `unsupported_semantics`，不得用 receipt dataclass 冒充完成。

solver receipt 分离 invocation identity、semantic result digest 和 observability；重放比较 semantic result，不比较墙钟字段。timeout、crash、unknown、wrong model/proof 均不生成 formal result。

### 7.4 Independent checker

checker 只读 canonical IR、argument graph 和 backend result，不能调用生产 evaluator 的内部状态或接收其 PASS。formal certificate 至少要求：IR type check、translation zero-loss、backend result check、argument grounded recomputation、claim projection check、pack/source/fact binding check 全部通过。

性能优化器、incremental/stratified/SMT 快路只有在与 reference implementation 做全域差分和 mutation gate 后才能登记为 certified；否则留在实验工具，不进入 wheel。

## 8. CertificateV4、AuditBundleV4 和状态存储

### 8.1 证书

`FormalCertificateV4` 不是若干 PASS 字符串的摘要。签发函数只接受 `ApplicationV4` 内部生成的 immutable evaluation context，并重新验证：

- decision status 为 `accepted_formal_result`；
- request/result/run identity digest 完整对应；
- source/evidence/fact/rule/translation/backend/checker/proof receipts 均存在、验签、未过期/撤销、subject/scope 对应；
- pack runtime 推导为 active，且 pack/build/trust policy 与 run identity 相同；
- completeness complete、无 interruption、无 translation loss、无 candidate/assumption/unknown/taint；
- audit core projection 的文件集和 digest 已完成预验证。

`ConflictCertificateV4` 使用独立 type 和 gate，不能被 consumer 当作 formal conclusion。certificate payload 与外部服务/发布签名分层：内部 deterministic certificate 证明材料闭合；需要对外身份担保时，再由受信 service signer 签名。

### 8.2 审计包文件集

```text
input.json
source-index.json
fact-admission.json
rule-pack.json
translation-receipts.jsonl
backend-receipts.jsonl
checker-receipts.jsonl
events.jsonl
graph.json
result.json
certificate.json
manifest.json
checksums.sha256
COMPLETE
```

文件按固定顺序、确定性 JSON/JSONL 写入。`certificate.json` 始终存在，内容是 `none|conflict|formal` 的 typed envelope；`none` 不包含证书。空 receipt 流也写成合法空文件。`checksums.sha256` 可使用标准裸 hex；所有 JSON 内 digest 仍只用 `sha256:<hex>`。

为避免 certificate↔manifest 循环摘要，先计算不含 `certificate.json`、full manifest、checksums、COMPLETE 的 `bundle_core_digest`；certificate 绑定该 digest。随后 manifest 记录 core/certificate/file digests并计算最终 bundle digest。`COMPLETE` 只在逐文件 hash、manifest、result、certificate、receipt chain 和一次本地 full verify 全部成功后落盘。

### 8.3 并发、崩溃和幂等

每次写入使用唯一 staging 目录；相同 content-addressed run/pack 并发采用原子竞胜，赢家发布 final，失败者验证 final 内容后返回同一逻辑结果。固定 `.tmp`、遇残留就永久失败、覆盖已有 final 均禁止。

每个落盘阶段必须支持 fault injection。孤儿 staging 只能在验证 owner/age/final 状态后隔离或回收，并写审计事件。文件和目录同步语义按 Windows/POSIX 分别实现并记录 durability capability；无法满足 production durability 的 state provider 不得进入 formal mode。

### 8.4 存储与隐私

V4 state 使用独立 namespace，不迁移或覆盖 V3 bundle。production deployment 必须提供：

- 仓库外路径、realpath containment、无 symlink escape；
- Windows 可验证 DACL 或 POSIX 0700/0600；
- 加密卷或等价 at-rest encryption；
- quota、磁盘余量、backup/restore、retention、legal hold、可审计清除；
- PII/secret/path canary 门禁；
- artifact access scope 和 bounded pagination。

若这些能力由 DSH/宿主提供，JC 仍须接收并验证 `StorageCapabilityV4`，将 provider/policy digest 写入 run identity；不能只在 `doctor` 中提示后继续签证书。

## 9. 三个公共入口与 formal MCP

### 9.1 唯一服务调用

```python
ApplicationV4.evaluate(request, runtime_context) -> EvaluationEnvelopeV4
ApplicationV4.verify(run_ref) -> VerificationResultV4
ApplicationV4.replay(run_ref) -> ReplayResultV4
```

CLI、`JCClient`、MCP 均先把外部 payload 交给同一 V4 parser，再调用上述服务。任何入口特有的规则查找、fact promotion、certificate、error fallback 都删除。

### 9.2 CLI

保留并改写：`jc capabilities`、`jc doctor`、`jc packs list|verify`、`jc evaluate`、`jc verify`、`jc replay`。candidate lookup、training、strategy、similar cases、rendering 迁到独立 advisory 工具。

CLI 输入支持 bounded stdin 和显式本地文件；文件读取只属于 CLI 用户边界，不进入 V4 request。stdout 始终单个 UTF-8 JSON；诊断到 stderr；绝对路径和 traceback 不出现在机器结果。

错误映射由 `ErrorV4` 单源生成：invalid input=2、pre-evaluation admission/trust/pack/storage blocked=3、engine/internal=4、verify/replay mismatch=5、required component missing=6。合法 review/missing/conflict/unknown 语义结果返回 0，但明确没有 formal certificate。

### 9.3 Python Client

包根只导出 `JCClient`、V4 contract、typed errors、verify/replay result。`ApplicationV4`、loaded pack、gate internals、backend providers 不从包根导出。Client 接收 Mapping 时重新严格解析；接收 model 时也通过 canonical round-trip 防止调用者持有可变内部对象。

### 9.4 MCP

正式 MCP 迁出 `addons/workbuddy_mcp.py`，由根 `mcp_server.py` 和 `compiler_core/mcp.py` 提供通用 V4 stdio adapter。只暴露四个 tools、零 resources：

| Tool | 输入 | 输出 |
|---|---|---|
| `jc_capabilities` | 空对象 | engine/build/schema/tool/pack/trust/storage digests 和 readiness |
| `jc_evaluate` | 严格 `CaseRequestV4` object 或受控 opaque request ref | compact result、certificate/run/artifact handles |
| `jc_verify_run` | opaque run ref、是否执行 offline replay | typed verify/replay result |
| `jc_read_artifact` | capability handle、offset、bounded length | 受限 chunk、content type、artifact digest |

禁止 `input_path`、`index_path`、动态 `--manifest` 和 formal/advisory 混装。`mcp_manifest.json` 由 contracts 生成并逐字节校验；运行时验证必须使用同一生成对象。schema/pack/trust/storage/engine 失败和内部异常均 `isError=true`；合法非正式语义结果 `isError=false`。

artifact handle 是 adapter 签发的非语义 capability，不是宿主路径；不得让 LLM 由 `run_id` 猜测其他案件材料。读取有 scope、失效时间、总量和分页上限，输出继续通过 privacy firewall。

## 10. 目标 formal core 文件图

V4 cutover 后，正式 wheel 只允许以下 core 职责。内部实现可以拆小，但不得新增第二 orchestration、第二 contract 或未登记 backend。

| 目标路径 | 唯一职责 | 吸收的现有路径 |
|---|---|---|
| `compiler_core/__init__.py` | V4 public exports | 重写现包根 |
| `compiler_core/version.py` | 唯一 engine/package/protocol version | `version.py` |
| `compiler_core/contracts.py` | 全部 V4 wire models、invariants、schema/tool spec generator | `contracts_v4.py`、`completion_status.py`、`types.py` 的正式字段、`trust_labels.py` |
| `compiler_core/canonical_serialization.py` | 唯一 JCS、DigestV4、canonical bytes | `jcs.py`、现 canonical helpers |
| `compiler_core/trust.py` | signature/trust policy/issuer/revocation verify | 当前缺失 |
| `compiler_core/artifact_store.py` | content resolver、state capability、atomic content store | `config_paths.py`、audit cache 的通用部分 |
| `compiler_core/source_service.py` | source/evidence/version/path gate | `source_service_v2.py`、`source_anchor.py`、`source_manifest.py`、`evidence_chain_validator.py` |
| `compiler_core/fact_admission.py` | fact three-gate admission | `fact_admission_v1.py`、`fact_trust_envelope.py` |
| `compiler_core/rule_packs.py` | signed pack registry/runtime verify | 重写现文件；不负责 candidate build |
| `compiler_core/legal_ir.py` | RuleV4、LegalSpec、LegalIVL、type/lowering validation | `legal_spec_ivl.py`、`type_checker.py`、`constraint_validator.py` |
| `compiler_core/backends/` | 已认证 Horn/AAF/exact providers | `evaluator.py` 中可证明语义；未认证实现不迁入 |
| `compiler_core/backend_router.py` | 从 LegalIVL 派生特征并选择 certified provider | `backend_router_v1.py`、`rule_router.py` |
| `compiler_core/argumentation.py` | typed attacks/priority/permission/grounded semantics | `argumentation.py`、`argumentation_v2.py`、`defeasible_priority.py` |
| `compiler_core/independent_checker.py` | 与生产 provider 分离的 reference verification | `independent_grounded_checker.py` 及经证明的 proof checks |
| `compiler_core/certificates.py` | typed receipt gate、formal/conflict certificate | `certificate_v1.py`、`certificate_checker.py`、旧 label certificate 的有效部分 |
| `compiler_core/audit.py` | typed append-only semantic events | `audit.py`、`proof_trace.py` 的有效部分 |
| `compiler_core/audit_bundle.py` | V4 writer/verify/replay | 重写现文件 |
| `compiler_core/application.py` | 唯一 orchestration 和状态矩阵 | `application.py`、`reasoning_boundary.py`、`taint.py`、`output_firewall.py` 的正式不变量 |
| `compiler_core/client.py` | public Python facade | 重写现文件 |
| `compiler_core/cli.py` | public CLI adapter | 重写现文件 |
| `compiler_core/mcp.py` | public formal MCP adapter | `addons/workbuddy_mcp.py` 的协议壳，不迁移其 V3/advisory/path 语义 |
| `compiler_core/resources.py` | schema/static resource lookup | 重写现文件 |

`rule_platform_cn.py` 属于后续 `cn-official` 规则工程/发布面，不进入 engine core wheel；V4 core 只保留完整 pack/receipt contract 和 runtime verifier。

## 11. 90 个 `compiler_core` 模块处置清册

以下五组覆盖当前 90 个 `.py` 文件且不重复。删除/外迁前必须跑 tracked consumer graph；外迁资产保留来源、license、hash 和消费方，不做静默丢弃。

### 11.1 保留职责并按 V4 重写：12

`__init__`, `application`, `audit`, `audit_bundle`, `canonical_serialization`, `cli`, `client`, `contracts`, `independent_grounded_checker`, `resources`, `rule_packs`, `version`。

其中 `contracts.py` 的 V3 内容全部替换为 V4，不保留旧 class 或 alias；`independent_grounded_checker.py` 最终改名 `independent_checker.py`。

### 11.2 合并/改名为单一 V4 实现：8

`argumentation`, `argumentation_v2`, `backend_router_v1`, `certificate_v1`, `evaluator`, `fact_admission_v1`, `legal_spec_ivl`, `source_service_v2`。

最终只留下第 10 节的无版本后缀模块和 certified backends；旧文件名删除。

### 11.3 迁移有效不变量后删除：23

`admission`, `certificate_checker`, `completion_status`, `config_paths`, `constraint_validator`, `contracts_v4`, `defeasible_priority`, `domain_config`, `evidence_chain_validator`, `fact_trust_envelope`, `output_firewall`, `proof_trace`, `reasoning_boundary`, `rule_router`, `source_anchor`, `source_manifest`, `stratified_evaluator`, `taint`, `trust_labels`, `type_checker`, `types`, `validity_state_machine`, `jcs`。

删除门禁不是零调用者一项；还必须证明其正确不变量已在 V4 contract/测试中落地。`domain_config` 的可变全局、吞异常和未绑定 YAML 行为不得迁移。

### 11.4 退出 formal core/wheel：43

`adapter_base`, `adjudication_draft`, `analysis`, `arbitration_reasoning`, `banach_verifier`, `breakthrough_candidates`, `breakthrough_verification`, `burden_of_proof`, `classifier`, `compliance_monitoring`, `conflict_of_laws`, `criminal_complexity`, `criminal_sentencing`, `cross_jurisdiction_compare`, `cross_jurisdiction_router`, `evidence_checklist`, `evidence_evaluation`, `grounded_smt_verifier`, `horn_completeness`, `incremental_grounded`, `invariance_metrics`, `ip_valuation`, `kg_recall`, `legal_memory`, `legal_reasoning`, `litigation_engineering`, `plugin_registry`, `prc_collision_engine`, `proof_trace_visualizer`, `proof_tree`, `rendering`, `result_diff`, `result_exporter`, `review_packet`, `rule_governance`, `rule_lookup`, `rule_platform_cn`, `smt_sidecar`, `spec_shadow_harness`, `step_verifier`, `training`, `transformer`, `universal_grounded_smt`。

处置规则：

- 有真实消费方者迁到独立 advisory/corpora/rule-engineering/tooling 分发；
- 仅做 conformance 的 `spec_shadow_harness`、SMT/reference 工具可移到 `tools/` 或测试环境，但不进 wheel；
- 零消费 stub 直接删除，Git history 已提供恢复；
- `litigation_engineering` 失去 formal certificate 权限；需要的 witness 算法经独立测试后吸收进 checker/certificates；
- `rendering`、analysis、review packet 只能消费 verified V4 result，不得被 formal core 反向导入。

### 11.5 直接删除且不提供当前 runtime 替代：4

`compat_v3_v4`, `g8_evaluator_patch`, `legal_ir_v3`, `proleg_translator`。

历史行为由 tag 保存；V4 current source 不承担兼容或旧实验翻译。

## 12. 其他目录逐角落处置

| 路径 | 必做动作 | 完成证明 |
|---|---|---|
| `addons/workbuddy_mcp.py` | 协议壳迁入 formal `compiler_core/mcp.py`；删除 V3、路径和 advisory tools | 安装后旧 import 失败；四工具 V4 stdio E2E |
| `addons/cn|hk|us|federation/**` | 连同 adapter/plugin registry/三轨外迁 | core wheel exact allowlist 不含 addons；资产导出 manifest 有 hash/license/consumer |
| `pipeline/fix_single_premise.py` | 删除启发式原地覆写规则工具 | 仓库和 wheel 均不存在；生成物 hash 未被误纳 official |
| `pipeline/experimental/llm_client.py` | 外迁 proposal-only 工具；网络发送与 formal 物理隔离 | formal dependency/import/network gate 为零 |
| `pipeline/pipeline.py` 等其余 `pipeline/**` | 整体外迁；禁止案卷扫描和过程报告写入 core 仓库 | core wheel、formal import graph、SBOM 均不含 pipeline |
| `configs/packs/*legacy*`、`configs/{zh_CN,hk,us,en_US,prc_us_alignment}` | 导出 candidate/corpora 数据制品；保留 provenance/许可/审核状态；从 core wheel 移除 | corpus manifest 行数/hash 对账；formal registry 不发现 candidate |
| `configs/packs/cn-official/**` | 删除空目录模拟发布；后续用真实不可变 pack artifact | core repo 不靠 README/空目录声称平台完成 |
| `configs/core_ontology.yaml`、overrides、domain config | 若影响 formal 语义，进入签名 pack/config digest；否则外迁 | run identity 和 pack manifest 能定位实际 config bytes |
| `configs/render_profiles/**` | 随 renderer 外迁 | formal result digest 不依赖 profile |
| `schemas/jc-v3.schema.json`、`schemas/w1b/**` | 删除 | V4 source/wheel purity gate |
| `schemas/jc-v4.schema.json` | 由 V4 contracts 生成完整 suite | generator diff=0；Python/Schema differential fuzz |
| `mcp_manifest.json` | 由同一 contract/tool registry 生成 | runtime/committed manifest byte-identical |
| `mcp_server.py` | 改为通用 V4 formal MCP 薄启动器 | `jc-mcp` console entrypoint + stdio lifecycle |
| `tools/build_rule_pack_manifests.py` | 当前 V3 builder 删除；后续 rule-engineering builder 读取 clean tree/materials，不接受 caller commit | synth/official pack build 可复现且验签 |
| `tools/build_provenance.py` | 绑定 clean tree、actual spec HEAD、wheel/tree/schema/tool/lock/pack/trust digest | signed build provenance，脏树/错 spec/tag 失败 |
| `tools/wheel_gate.py` | exact allowlist、双 build、仓库外安装和 V4 E2E/replay | 两次 wheel SHA-256 相同；旧 imports 失败 |
| `tools/supply_chain_gate.py` | 审计最终 wheel、全部生产/build locks、license、SBOM | 零未锁生产依赖、零未处理 blocker |
| `tools/perf_baseline.py` | 改走 V4 installed-wheel + signed synthetic/official pack | p50/p95/p99、吞吐、RSS、bundle/event 大小报告 |
| `tools/run_trirail_matrix.py`、`fast_path_interceptor.py` | 外迁私域/实验 tooling | 不进 core wheel，不被 formal CI 当 authority |
| `tests/unit/test_v3*`、`test_w1b*`、V3 fixture | 删除；正确语义改写为 V4 tests | 旧 imports 为零，信息守恒矩阵覆盖 |
| `tests/run_benchmark_zh.py`、`stress_test_facts.py` | 删除失效脚本或改成正式 pytest performance/chaos | CI 实际收集；不存在引用缺失 fixture |
| `requirements/*.lock` | 生产、构建、测试和发布 profile 解析全部传递依赖并带 hash | `--require-hashes` clean install；lock digest 入 provenance |
| `.github/workflows/ci.yml` | 增加 static/type/property/integration/e2e/chaos/security/dual-build/installed-wheel jobs | required jobs 全过，无整文件 skip |
| `.github/workflows/auto-release.yml` | 改为晋级 CI 已生成的同一 digest，不在 tag 后重建 | tag/version/METADATA/capability identity 一致 |
| `.gitignore` | 保留敏感输出保护，但显式列出全部应跟踪生成物；CI 查 ignored authority | 新 schema/manifest 不会静默未跟踪 |
| `README.md`、`HANDOFF.md`、`AGENTS.md`、`memory.md`、`CHANGELOG.md` | 全部改为 V4 current state；删除旧 HEAD/绝对机器路径/V3 命令 | docs command/path/version validator |
| `docs/**` | 重写 contract/architecture/operations；删除旧 active migration 和混时点 baseline | 一个 current-state manifest；无不存在路径/双 registry |
| `pyproject.toml` | 精确 package allowlist、V4 version、formal MCP entrypoint、runtime dependencies、metadata/license files | wheel contents/METADATA/RECORD gate |
| `LICENSE` | 保留 MIT；新增第三方 NOTICE/license ledger | wheel 和 SBOM 包含必要 notices |

旧方案和 V2→V3 migration 不留作 current docs；Git tag 已保存历史。新方案在施工完成后可进入 archive，但不得继续解释当前 authority。

## 13. 原子施工波次

全部施工在受保护的 `v4-cutover` 分支完成。`main` 在 cutover 前冻结功能开发；任何含双主链、未闭合 receipt 或未切完入口的中间 commit 均标记 `releaseable=false`，不得合入生产分支或发布。每波在工作区内先写测试、再实现、全绿后提交；不提交故意失败测试。

### S0：冻结 V4.0 合同和切换清册

**目标**：先把语义、摘要、状态、错误、limits、module authority、wheel allowlist 和删除清册定死，避免边接线边改合同。

**动作**：

- 写出完整 V4 object/field/invariant 表和第 5 节信息守恒 golden cases；
- 建立单一 machine `module-authority.json`，包含 module class、允许 imports、public constructors 和 formal sink；
- 建立当前 291 文件 disposition manifest，记录迁出数据的行数、hash、来源、license 状态和消费方；
- 冻结 `sha256:<hex>`、canonical time、amount/rational、ref/error grammar；
- 确定 `ENGINE_LIMITS_V4` 和性能预算制定方法；
- 选定并锁定 signature verifier、JSON Schema test validator、ruff/mypy/property/mutation 工具；
- 冻结四个 formal MCP tools 和 ToolSpec digest 算法；
- 建立 synthetic signed official pack，仅用于系统测试，名称和 issuer 必须显式含 `test`，不能进入 production trust policy。

**门禁**：所有新增 schema/model/status 有正负 golden；90 模块与 291 文件处置无遗漏；没有 unresolved generic Mapping；依赖和 license 决策已记录。

**回退**：revert S0 spec commit；不改 runtime。

### S1：合同、规范化、信任和 artifact 基座

**目标**：先解决所有 V4 对象不能组合、caller 可伪造和路径无界问题。

**主要路径**：`contracts.py`、`canonical_serialization.py`、新 `trust.py`、新 `artifact_store.py`、`schemas/jc-v4.schema.json`、`mcp_manifest.json`、contract/property/security tests。

**动作**：

- 用 V4 model 替换 `contracts.py`，吸收 staged V4 全部公开对象；
- 实现唯一 JCS/DigestV4；删除三套 digest grammar；
- 生成完整 JSON Schema 和 ToolSpec；生成物手改 gate；
- 实现严格 parser、深度/大小/Unicode/数字/重复 ID/collision limits；
- 实现 Ed25519 envelope、trust policy、role/scope/validity/revocation verify；
- 实现 content resolver、opaque ref、同内容幂等/异内容 collision；
- 建立 `RunIdentityV4` build injection，调用者不能提交 commit/tree/wheel/schema/trust 值。

**门禁**：Python/Schema/CLI-parser/MCP-validator 接受拒绝完全一致；RFC/JCS vectors、签名篡改、未知/过期/撤销 key、路径/资源攻击、cross-process digest 全过；V4 engine major 只接受 4。

**回退**：revert S1；S0 spec 保留。此时仍不发布。

### S2：来源、证据、事实和 signed pack runtime

**目标**：把 P02/P06/P08/P09 和正式 pack loader 接成真实、不可伪造的纵切面。

**主要路径**：新 `source_service.py`、`fact_admission.py`、重写 `rule_packs.py`、synthetic pack fixture、source/fact/pack integration tests。

**动作**：

- resolver 读取实际 source/evidence bytes 并复算 raw/normalized hashes；
- 实现 locator、source version graph、root-terminal path、applicability；
- EvidenceManifest 绑定 request/case/run scope，重复 ref 直接失败；
- FactAdmission 只接 refs，内部生成 gate result；实现 signer role 和 replay policy；
- pack registry 验证 V4 manifest、每项 material、signature、trust policy、engine API 和 config；
- 删除 development override 进入 formal 的可能；candidate 只能返回 corpus/review handle；
- 用 synthetic signed pack 打通 source→fact→rule load，不进行法律实体正确性宣称。

**门禁**：任一 byte/digest/locator/time/signature/role/scope/graph edge 篡改均失败；同请求 retry/replay 幂等；伪造 GateOutcome/PASS 无公共构造入口；空 official pack 不可能 integrity valid/reasoning ready。

**回退**：revert S2；S1 contract/trust 可独立保留。此时仍不发布。

### S3：RuleV4、双 IR、argumentation 和 certified backends

**目标**：关闭 P03/P04/P07，不再用 staged receipt 自证。

**主要路径**：新 `legal_ir.py`、`backends/`、`backend_router.py`、统一 `argumentation.py`、`independent_checker.py`、semantic/property/mutation tests。

**动作**：

- 统一 `LegalRule`、`RuleV4`、`CandidateRuleV4` 为唯一 RuleV4；
- 实现 LegalSpec/LegalIVL strict parser、type check、zero-loss lowering 和 exhaustive coverage；
- 实现 Horn/fixpoint、AAF、exact arithmetic/calendar providers；router 从 IVL 派生特征；
- 重写 priority、permission、exception、attack/defeat 和 grounded semantics；
- 实现与生产 provider 分离的 reference checker/differential oracle；
- 未认证 SMT/ASP 返回 unsupported，不启用 sidecar fallback；
- 把 W1b admitted/rejected/pending-review 的有效规则准入语义改写为 V4 rule-engineering receipt contract，但不保留 W1b runtime/API。

**门禁**：translation 任意 lost/defaulted field 阻断 formal；快路与 reference 全域差分；priority 被忽略、permission disputed 不可达、duplicate claim witness 被覆盖等 mutation 全被杀死；solver/provider receipt 只能由真实 invocation 生成。

**回退**：revert S3；不回落旧 evaluator，不发布。

### S4：ApplicationV4、状态矩阵、certificate 和 AuditBundleV4

**目标**：形成唯一可执行 V4 主链和可离线验证的正式结果。

**主要路径**：`application.py`、`certificates.py`、`audit.py`、`audit_bundle.py`、`artifact_store.py`、state/status/concurrency/chaos tests。

**动作**：

- Application 按固定阶段调用 resolver→source/evidence→fact→pack→IR→backend→checker→result→certificate→bundle；
- 实现第 5.1 节状态矩阵和三入口共享 error taxonomy；
- certificate 函数不再接受 caller gate map，按 actual receipts 重算；
- 实现 V4 events、manifest、checksums、COMPLETE、verify 和 offline replay；
- 实现唯一 staging、原子竞胜、orphan recovery、fsync/durability capability；
- 引入独立 V4 state namespace、retention/GC hooks 和 privacy firewall；
- V3 bundle 明确返回 unsupported，而不是半解析。

**门禁**：synthetic signed pack 的 formal/review/missing/conflict/unknown/blocked/engine_error 全状态 E2E；每个落盘点 kill、同/异 run 并发、同 pack 并发、磁盘满/权限/长路径/symlink tests；任一 artifact bit flip verify/replay 失败；FormalCertificate 只能出现在唯一合法状态。

**回退**：revert S4；V4 state namespace 不影响 V3 历史数据。仍不发布。

### S5：公共入口原子切换并删除旧 authority

**目标**：一个 cutover commit 同时让包根、CLI、Client、formal MCP 只走 V4，并删除 V3/W1b/compat。

**主要路径**：`__init__.py`、`cli.py`、`client.py`、新 `mcp.py`、`mcp_server.py`、`pyproject.toml`、三入口 tests，以及第 11/12 节全部 delete/externalize paths。

**动作**：

- 切换所有入口到同一 `ApplicationV4`；
- formal MCP 改为四工具，删除 path/advisory semantics；
- 删除 V3/W1b/compat schema、代码、tests、fixtures、active docs；
- staged `_v1/_v2` 文件有效代码迁入无版本后缀 target 后删除旧文件；
- candidate/addons/pipeline/private tooling 完成可核验外迁或删除；
- package root 不再导出 analysis/rendering/loaded pack/evaluator internals；
- 版本设为 `4.0.0-rc.1`，schema API 为 `jc/4.0`。

**门禁**：AST formal graph 只有一个 application sink；生产源码和 wheel 中旧 import/path 为零；安装后 V3/W1b/compat import 必须失败；CLI/Client/MCP canonical result、run identity、receipt refs、error class 完全一致。

**回退**：cutover 未合入 production 前可整体 `git revert`。合入后不启用 V3 feature flag；若 RC 失败，停止晋级并发布修复后的新 V4 RC。

### S6：wheel、CI、供应链、发布和 current docs 收口

**目标**：证明交付制品而非源码树可运行，并消除版本/文档/权威漂移。

**主要路径**：`pyproject.toml`、requirements locks、`tools/{wheel_gate,supply_chain_gate,build_provenance,perf_baseline}.py`、workflows、README/HANDOFF/AGENTS/memory/CHANGELOG/docs、SECURITY/CODEOWNERS/NOTICE。

**动作**：

- wheel exact allowlist，只含 formal core、唯一 V4 schema、license/notice；
- 全 production/build 依赖和 transitive dependencies 带 hashes；
- 两个干净相同 build profile 独立构建并比较 wheel bytes；
- 仓库外 venv 安装 wheel + locked deps，运行 doctor/capabilities/CLI/Client/MCP/formal E2E/verify/replay；
- SBOM 覆盖 wheel 文件、依赖、schema、ToolSpec、synthetic test pack/build materials；
- provenance 绑定 clean source tree、actual spec commit、wheel/schema/tool/lock/trust digests并生成 artifact attestation；
- rewrite release workflow：构建一次，晋级同一 digest；校验 tag/version/METADATA/CLI/MCP/run identity；
- 重写全部 current docs 和 machine registry；命令/path/link 自动校验；
- 增加 vulnerability disclosure、code ownership、branch/tag/release governance 配置。

**门禁**：源码 tests 全过不够；installed-wheel 全矩阵通过、双构建 hash 相同、wheel exact contents、旧 import 失败、SBOM/provenance/checksums/attestation 完整、current docs 零 stale path/version。

**回退**：revert S6 配置或生成新 RC；不对已签 artifact 原地覆盖。

### S7：V4 Kernel RC 投产演练

**目标**：在没有正式 cn-official 内容前证明内核生产属性，但保持 `formal_ready=false`。

**动作**：

- 在 Windows 和 Ubuntu 目标部署形态做 clean install；
- 验证真实 state provider DACL/permissions、加密、retention、backup/restore、capacity；
- 用 synthetic signed pack 做正负 E2E、并发、kill、restart、replay、revocation 演练；
- 采集 p50/p95/p99、吞吐、RSS、bundle/event 大小并批准预算；
- 演练坏 engine/pack/trust key 撤销、artifact rollback 和停止 formal service；
- 发布 `4.0.0-rc.N` wheel、SBOM、provenance、checksums、attestation；capabilities 明确 `legal_production_ready=false`。

**门禁**：第 15 节除真实 cn-official 和 DSH 外全部 PASS；任何 failure 都生成新的 RC，禁止原地替换。

### S8：正式 cn-official 与 4.0.0

该波次另写法律/规则工程实施方案，不在本次系统施工中伪造法源或规则。开始条件是 S7 完成；完成条件见第 17 节。真实 pack 通过后重新跑 installed-wheel 全套 E2E，随后把同一 V4 engine artifact 与独立签名 pack 组合晋级，发布 `4.0.0`。

### S9：DSH formal profile/plugin

只在 S8 完成后实施。DSH adapter 消费第 9.4 节固定工具合同，不改 JC 主链，不把 JC 语义复制进 DSH agent loop。详见第 18 节。

## 14. 测试体系与语义 mutation 门禁

### 14.1 测试分层

| 层 | 目录 | 必测内容 |
|---|---|---|
| unit | `tests/unit/` | typed models、canonicalization、状态矩阵、纯算法和单项错误码 |
| contract | `tests/contract/` | Python/JSON Schema/CLI/Client/MCP 同一黄金语料 differential |
| property | `tests/property/` | Hypothesis 生成 nested/Unicode/limits/graph/IR/receipt 正负例 |
| integration | `tests/integration/` | artifact→source→fact→pack→IR→backend→checker→certificate |
| e2e | `tests/e2e/` | 源码树和 installed wheel 三入口、verify/replay、synthetic/official pack |
| security | `tests/security/` | path、symlink、UNC/device、zip/path traversal、signature、revocation、secret/PII canary |
| chaos | `tests/chaos/` | 并发、逐阶段 kill、磁盘满、权限、orphan recovery、cancel/retry |
| determinism | `tests/determinism/` | Python/OS/hash seed/locale/timezone/cross-process canonical bytes |
| performance | `tests/performance/` | fixed corpus 的延迟/吞吐/RSS/artifact size/event count |
| packaging | `tests/packaging/` | wheel allowlist、METADATA/RECORD/LICENSE、旧 import 失败、clean install |

required CI job 不允许 module-level skip。重型/法域测试要么作为明确 required profile 安装依赖并运行，要么从正式门禁移出并删除虚假覆盖叙事；不能保留“requires heavy deps”而长期 skip。

### 14.2 必杀 mutations

不采用一个总 mutation 百分比掩盖关键 gate。下列每个 mutation 必须被测试杀死：

- engine `major>=3`、digest 前缀放宽、unknown field/float/list 检查缺失；
- source hash 不复算、signature 非空即通过、version graph 断开/环/乱序仍通过；
- attestation ID 覆盖、caller GateOutcome PASS、cross-scope replay 通过；
- candidate/development/empty pack reasoning-ready；build attestation 只验 hex；
- translation 丢字段仍 PASS、direct oracle 与生产 lowering 共用被测逻辑；
- priority 不参与 defeat、permission disputed 不可达、同 claim witness 覆盖；
- router 信 external features、solver receipt 无真实 invocation、wrong model/proof 通过；
- checker receipt subject/run/build 不匹配；UNKNOWN/DISPUTED/partial 仍签 formal；
- bundle 少文件/换 event/换 graph/换 receipt/先写 COMPLETE 仍 verify；
- CLI/MCP engine failure 返回成功、artifact handle 可越 scope；
- wheel 混入 V3/W1b/addons/pipeline/candidate 后 gate 仍 PASS。

### 14.3 正向和负向正式纵切面

S4 前使用 synthetic signed pack，覆盖：

1. 一条可证明 formal 结论；
2. 缺 fact；
3. disputed fact branches；
4. exception 成立/不成立；
5. permission 与 prohibition 冲突；
6. priority cycle 和合法 priority；
7. temporal boundary、整数金额和有理比例；
8. source/receipt/pack/key 篡改；
9. backend timeout/crash/unknown；
10. checker disagreement；
11. candidate pack；
12. incomplete/crashed bundle 和 deterministic replay。

synthetic pack 只能证明系统机制，不能证明任何中国法命题。

## 15. CI、构建和发布门禁

### 15.1 CI 必需 jobs

1. generated artifacts diff、AST authority graph、V4 purity、secret/PII path scan；
2. ruff、mypy、unit、contract、property、mutation；
3. integration/e2e/security；
4. Ubuntu 3.11/3.12、Windows 3.12 determinism 和 chaos 子集；
5. production/build locks `--require-hashes` install、dependency vulnerability/license audit；
6. clean build A/B 字节比较；
7. wheel exact inspection、仓库外 clean install、installed-wheel E2E/replay/MCP；
8. SBOM、provenance、checksums、artifact attestation；
9. performance regression；
10. docs/path/command/current-state validation。

现有 actions SHA pinning和三平台矩阵保留；full pytest 后不重复跑相同 MCP 单测，专门 job 应运行真实 installed-wheel stdio lifecycle。

### 15.2 wheel exact allowlist

允许：第 10 节 formal modules、`schemas/jc-v4.schema.json`、license/notice、package metadata。拒绝：addons、pipeline、candidate/legacy configs、rule-engineering、advisory/rendering/analysis、V3/W1b/compat、tests、reports、机器路径和密钥模式。

engine wheel 不捆绑 `cn-official`；pack 作为独立、签名、可撤销、独立版本 artifact 安装。clean install E2E 显式安装批准 digest 的 pack。

### 15.3 身份和 release

必须满足：

```text
tag version
= compiler_core.version.__version__
= wheel METADATA version
= jc capabilities engine_version
= MCP serverInfo.version
= RunIdentityV4 engine_version
```

正式运行还必须绑定 exact source commit/tree、wheel digest、schema digest、ToolSpec digest、lock digest、pack digest、trust policy digest。Release 只晋级 CI 已测试的同一 artifact digest；tag job 不重新 build。

Release 附：wheel、SHA-256 checksums、CycloneDX SBOM、build provenance/attestation、V4 schema/ToolSpec digest、支持矩阵、known limitations、rollback/revocation 指令。`CHANGELOG` 在 tag 前去掉 Unreleased，不能重复发布同一版本。

### 15.4 治理

本地 checkout 无法证明远端 branch/tag protection、管理员绕过和签名策略。S6 必须现场核验并保存外部证据：protected main/tag、required CI、formal core/contract/generator/pack CODEOWNERS、双人审批、安全披露、坏制品/pack/key 撤销流程。未核验不得发布 4.0.0。

## 16. 运维、可观测性和回退

### 16.1 readiness 与 health 分离

`health=true` 只表示进程存活；`formal_ready=true` 必须实时推导并同时满足：批准的 V4 engine build、Schema/ToolSpec digest、active signed pack、有效 trust policy、未撤销 keys、verified state provider、容量和 offline self-check。

`cn-official` 缺失/blocked 时可以 health=true，但 formal_ready 必须 false。doctor、capabilities、CLI、MCP 和部署探针复用同一 readiness evaluator。

### 16.2 可观测性

允许记录：阶段耗时、状态码、对象数量、artifact 大小、provider/build/pack/trust 的公开 digest、retry/collision/replay 计数。禁止记录：原始案情、事实文本、证据内容、密钥/token、签名私材、绝对路径、完整 request/result。

每个 run 的 semantic events 确定排序；普通日志可带 wall-clock，但不能进入 replay 比较。错误只返回稳定 code、stage、retryable 和 opaque correlation id，不回显异常 repr/traceback 给模型或用户 stdout。

### 16.3 rollout

1. RC 在隔离环境只用 synthetic pack；
2. 正式 pack 安装后先运行 verify、negative tamper、offline replay 和 readiness；
3. 选择授权的非生产材料做 dark run，不向业务方签发结果；
4. 小比例 canary 只使用 V4，观察错误、latency、storage、replay；
5. 扩大流量前复核 artifact digest 和 trust/pack revocation 状态；
6. 任一 formal invariant 失败立即停止 formal endpoint，而不是回落 advisory/V3。

### 16.4 回退边界

- 施工阶段：每波 green commit 可用 `git revert` 回退，不用 hard reset；
- RC/生产：只切换到上一份已签名、已验收的 V4 wheel + pack digest；不从历史 tag 现场重建；
- 首次 V4 上线若尚无上一份 V4，失败时停止 formal service并修复，不启用 V3 fallback；
- pack rollback 只能切到仍在有效期、未撤销且与 engine API兼容的上一份签名 V4 pack；
- V3 bundle 保持只读历史存储，需要时在隔离的 V3 环境重放；V4 state 不读、不改、不迁移它；
- bad engine、pack、key、trust policy 和 certificate 均有独立撤销清单，撤销本身签名并进入 readiness。

## 17. `cn-official` 后续施工的开始与完成条件

### 17.1 开始条件

- S7 V4 Kernel RC 全部门禁通过；
- RuleV4、SourceSnapshotV4、FactAttestationV4、PackManifestV4、review/promotion receipts 和签名协议冻结；
- pack builder、source ingestion、coverage/变异测试工具不在 core runtime，但产物能被 V4 verifier 消费；
- 明确法源取得、版本、locator、许可/再分发和人工审核责任；
- 明确 first domain。旧方案的“民事诉讼期间计算”不自动继承，须按可获得第一方法源、业务优先级、边界可闭合性重新决定。

### 17.2 一个“完整领域”的最低交付

1. 第一方/权威原始法源 bytes、规范化 profile、结构 locator、版本链和真实性 receipt；
2. 该领域现行、失效、过渡、例外、permission/priority/temporal/numeric 的覆盖清册；
3. 每条 RuleV4 的 source locator、interpretation choice、legal/engineering review 和 promotion receipt；
4. 边界、反例、冲突、缺事实、变异、differential、replay 测试；
5. pack compiler/source tree/schema/trust/coverage receipts 的完整 digest；
6. 不可变 pack manifest、release signature、独立 pack version、compatibility 声明和撤销信息；
7. V4 installed-wheel 对真实 pack 的 formal/review/missing/conflict 正负 E2E；
8. 人工抽样复核只验证法律/解释质量，不代替机器 hash/signature/gate。

书籍、OCR、类案和 legacy 规则可以用于 discovery 与候选生成；未逐条回到可验证正式法源并完成审批，不得进入 official reasoning denominator。

### 17.3 4.0.0 最终门禁

`cn-official` 至少一个完整领域满足上述全部条件，且：

- clean installed V4 wheel 能从 signed pack 独立启动并输出一个可 verify/replay 的正式结果；
- 任一 source/rule/receipt/key/pack/artifact 篡改均阻断；
- candidate-only 数量和 official eligible 数量从同一 manifest 实算，不允许报告与 registry 冲突；
- readiness、certificate、audit、SBOM、provenance 均绑定同一 engine/pack/trust digests；
- 法律审查人、工程审查人、发布审批人职责分离并可验签；
- 生产存储、retention、backup/restore、key/pack revocation 演练通过。

未达成时只保持 `4.0.0-rc.N` 和 `formal_ready=false`，不靠免责声明发布正式法律能力。

## 18. DSH 化冻结接口

DSH 工作不进入 S0-S8 的 JC runtime 实现；本阶段只冻结其未来不能改变的接缝。

1. DSH 使用 out-of-tree formal profile/plugin + JC formal MCP tools；不修改 DSH agent loop 来复制 JC semantics。
2. profile 激活先调用 `jc_capabilities`，精确比较 engine build/wheel/tree、schema、ToolSpec、pack、trust policy、storage readiness digests。
3. JC 缺失、非 V4、digest 未批准、pack 非 active、storage/trust 不 ready 时，formal profile fail closed；general/advisory DSH 继续可用但不能标 formal。
4. DSH 只能提交 CaseRequestV4 object/opaque refs；不能调用 evaluator/backend、构造 GateOutcome/receipt/certificate、传宿主路径或直接读 state root。
5. DSH 只消费 `SemanticResultV4`、certificate/run/artifact handles 和稳定 errors；不得根据自然语言输出猜 formal 状态。
6. MCP resources 不作为前提；artifact 通过 bounded `jc_read_artifact` 读取。
7. 对接时锁定一个经验证的 DSH release/commit 和 Node/Python/OS 矩阵；禁止追随未固定 master 自动漂移。
8. DSH sandbox 不能替代 JC 的 resolver、trust、signature、privacy 和 storage gates；JC 必须对不可信调用者独立安全。
9. conformance 覆盖启动/handshake、crash/reconnect、cancel/timeout、retry/idempotency、MCP `isError`、artifact pagination、V3 rejection 和 pack/key revocation。

因此，“DSH 即插即用”是平台能力，“formal legal profile 必须经 JC”是该 profile 的 capability 依赖，两者不存在架构冲突。

## 19. 生产完成定义（Definition of Done）

下列项目必须全部有机器证据和 artifact digest；任何一项缺失均不算完成。

| Gate | PASS 证据 |
|---|---|
| V4 purity | production AST/import graph、wheel exact list、旧 import negative tests；V3/W1b/compat 为零 |
| Contract closure | 完整 generated schema/tool spec；Python/Schema/三入口/property differential PASS |
| Digest/identity | 单一 grammar；跨进程/平台 determinism；wheel/tree/schema/tool/pack/trust/lock 全绑定 |
| Trust/source/fact | 真实 bytes hash、签名、role/scope/time/revocation、graph/path、replay/collision 全部正负测试 |
| Rule/IR/backend | 唯一 RuleV4、zero-loss lowering、certified providers、reference differential、critical mutations killed |
| State matrix | formal/hypothetical/review/missing/conflict/unknown/blocked/error 每态正负例和证书约束 |
| Certificate | caller 无法制造 PASS；subject/run/build/receipt/bundle 绑定；签名 verify/revoke |
| Audit/replay | atomic COMPLETE、bit-flip detection、offline replay、并发/kill/disk/permission recovery |
| Privacy/storage | DACL/permissions、encryption、retention/legal hold/clear、backup/restore、PII/secret/path canary |
| Entrypoints | CLI/Client/MCP canonical parity、稳定 errors、MCP `isError`、bounded artifacts |
| Package | 双 build byte-identical、clean installed-wheel E2E、METADATA/RECORD/LICENSE/NOTICE、旧 import 失败 |
| Supply chain | 全锁/hashes、SBOM、vulnerability/license gate、provenance/attestation/checksums |
| Version/release | tag/source/METADATA/CLI/MCP/run identity 一致；release 晋级同一 tested digest |
| Docs/authority | 一个 machine registry；current docs path/command/version validation；无 stale absolute path |
| Operations | readiness/health、canary、rollback/revocation、capacity/performance、incident drill |
| Legal production | 至少一个真实 `cn-official` 完整领域 installed-wheel formal E2E + replay |

建议最终交付一个机器可读 `release-evidence.json`，只引用上述原始 reports 的 digest，不复制或手填 PASS。顶层结论必须由 verifier 重新计算。

## 20. 硬停止条件

出现任一条件，停止当前波次，修根因后重跑全量相关门禁：

- 发现第二个 contract/schema/tool manifest authority；
- 任一 public/formal consumer 仍 import V3/W1b/compat 或旧 evaluator；
- external payload 能构造 PASS、active、receipt、certificate 或 build identity；
- schema/Python/入口接受集不一致，或存在开放 formal Mapping；
- digest/signature/subject/scope/run/build 任一绑定不闭合；
- translation loss、checker disagreement、candidate/unknown/taint 能签 formal；
- 并发、崩溃、磁盘、权限测试产生不可恢复或覆盖已有 artifact；
- wheel 出现未 allowlist 模块、candidate/私域数据、路径或 secret；
- required test skip、mutation survivor、installed-wheel E2E 或 replay 失败；
- tag/version/wheel/provenance digest 不一致；
- `cn-official` 仍为空/blocked，却准备发布 formal-ready；
- Windows DACL/加密/retention 或目标 storage capability 无法验证；
- 候选资产在无 provenance/license/consumer 对账时被删除或晋级 official。

## 21. 施工记录和提交纪律

每波保留一份简洁 evidence manifest，列出：改动文件、根因、迁移的不变量、新增/删除 public surface、测试命令、exit code、报告 digest、wheel/pack/schema/tool digest、已知限制。报告必须引用原始输出，不能靠人工写“COMPLETE”。

每个 green commit 的 message/body 包含：

- files changed；
- root cause；
- new project knowledge；
- impact and compatibility break；
- exact validation and exit codes。

不在同一 commit 做无关格式化；不修改 lock/env 原件，除非该波明确授权并完成供应链验证；不用 hard reset。发现范围外问题写入本方案债务清册或专门 issue，不顺手改变相邻语义。

## 22. 开工前必须指定的外部输入

| 输入 | 最迟波次 | 未提供时处理 |
|---|---|---|
| service/pack/human approval key custody、issuer/role/revocation policy | S1 | 只能使用隔离 test trust root；禁止 production certificate |
| production state provider、Windows DACL、encryption、retention/legal hold/backup | S4/S7 | production mode/readiness 拒绝 |
| engine limits、latency/throughput/RSS/storage budgets | S0/S7 | RC 不晋级；不得用未批准魔数宣称性能 |
| candidate/corpora 外迁目标和 license/provenance owner | S5 | 不删除资产，也不让其留在 core wheel；cutover 阻塞 |
| 首个 cn-official 完整领域和第一方法源 | S8 | formal_ready 保持 false，不发布 4.0.0 |
| remote branch/tag protection、CODEOWNERS、release signer | S6 | release job 禁止晋级 |
| DSH pinned release/commit 和 deployment topology | S9 | 不开始 DSH profile，不改 JC contract |

这些输入不会改变 V4-only、零兼容、唯一 application 和 fail-closed 决策；它们只决定对应 production gate 何时能 PASS。

## 23. 本方案交付边界

本方案基于固定 HEAD 的静态全仓审计。当前任务不修改生产代码、不生成 schema/pack、不运行 test/build，也不核验 candidate 法律实体内容、签名密钥、远端保护策略或生产存储。实施时必须重新固定开工 HEAD；若仓库已前进，先生成 diff/consumer graph 并更新处置清册，不能直接照旧行号施工。

### [我违规之处]
- 无
