# juris-calculus 理论成果全量吸收施工方案

> **已归档：** 本文仅保留历史规划与施工上下文，不描述当前运行状态。当前信息见[状态页](remediation/v4/STATUS.md)与[文档索引](docs/README.md)。

日期：2026-08-15

适用基线：`main@5b7bd008966703a33343ef1784fd13f5650b8e66`

方案性质：施工规范；不代表任何功能已经完成
理论输入：已冻结，只消费既有结论，不重启理论研究

## 0. 结论

JC 定位不变：公开、可审计、CLI-first 的法律形式推理运行时内核。

本仓负责把已准入事实和已准入规则送入受保护形式内核，执行 Horn、attack、exception、permission、priority、时间与数值约束，输出确定性的 `DecisionStatus`、checker receipt、solver receipt、certificate、audit bundle 和 replay 结果。

本仓完整吸收冻结理论的 P01—P09，但不把所有上游职责搬进 JC：

- P03、P04、P07、P09 正式侧由 JC 实现；
- P02、P05、P06、P08 由 JC 定义并执行消费门禁；
- P01 由 JC 消费人工研究/复核收据并绑定到 run，不负责组织律师工作流；
- 语义变更必须先取得 `legal-math-modeling` 的版本化规范或反例；
- 候选研究由 Deli 产生，案件编排和律师批准由 Legal Harness 承担。

不可变边界：

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

## 1. 当前基线与未完成项

### 1.1 已落地，可直接继承

- 包、CLI、审计和 MCP 的单一版本源是 `compiler_core.version.__version__`，当前值为 `3.0.2`。
- 外部 `CaseRequest` 和旧 FactCoordinate payload 不能自报 `VERIFIED_FACT`。
- development pack 可加载审查，但不能成为 reasoning-ready 正式包。
- `JCClient` 是公共 Python API；低层求值函数不再由包根导出。
- LLM 提取保持 proposal-only，真实 provider 与 regex provider 显式区分，不允许 mock fallback 冒充真实运行。
- run identity 已进入正常运行、早退、audit、graph、bundle 和 replay 主链。
- 独立 grounded checker 已保留 argument witness、typed attack witness、AAF digest 和 claim projection。
- `cn-official` 继续 inactive/blocked；没有一方官方来源快照时不得改变状态。

以上是当前仓项目记忆记录的 W0/W1 结果。方案施工 W0 仍须以当前 HEAD 重新验证，不把历史测试数字当作当前 PASS。

### 1.2 尚未落地

1. v4 中立合同及从 v3/W1b 合同到 v4 的唯一兼容入口。
2. `SourceSnapshotV2`、`EvidenceManifestV1`、`FactAdmissionAttestationV1` 的运行时闭环。
3. P03 的完整 argument/attack/exception/permission/priority/cycle 语义与独立核验。
4. P04 的多后端执行架构、优化直达快路、ASP/SMT 路由及真实 solver receipt。
5. P07 的正式 `LegalSpec -> Legal-IVL -> targets` 编译架构、逐跳 translation trace 和全链验证。
6. P09 的来源、解释、事实准入分门，以及 attestation 与确切输入的哈希绑定。
7. `cn-official` 完整规则工程平台、首个完整规则域及人工晋级收据。
8. build-bound `RunIdentityV2`、`FormalCertificateV1`、`AuditBundleV2` 和离线自足 replay。
9. CLI、`JCClient`、MCP 对相同请求的结果、错误码、receipt 和审计一致性。
10. 当前 `compiler_core` 中实验、工作流、私域和重复模块的 authority 收敛。

### 1.3 分支事实

`codex/lmm-runtime-receipt` 比当前 `main` 多两个提交，含 runtime refinement fixture 和旧升级施工方案。该分支不是当前主线事实，不自动 merge。W0 必须逐文件判定：移植、按当前合同重写或废弃；禁止为了保留历史投入整枝合并。

## 2. 本仓职责边界

### 2.1 必须负责

1. 中立、稳定、可版本化的输入输出合同。
2. 正式事实准入门和规则包准入门。
3. 受保护的确定性形式求值。
4. argument identity、attack、exception、permission、priority 和 cycle 处理。
5. 时间、数值和 solver 路由的确定性语义。
6. checker、certificate、audit、graph、replay 的字节级绑定。
7. CLI、Python API、MCP 的同义行为。
8. fail-closed：缺失、冲突、未知、中断和不可重放均不得伪装为正式结论。

### 2.2 绝对不负责

- 不抓取互联网，不做通用研究调度。
- 不保存私人案件原始材料、律师策略、个人写作风格或私有 benchmark。
- 不让 LLM、Agent、OCR、RAG 直接创建 `verified_fact`。
- 不自动把候选法源或候选规则晋级为正式规则包。
- 不把算法 checker 宣称为 Lean 定理证明或法律正确性证明。
- 不替 `legal-math-modeling` 发明新语义。
- 不替 Legal Harness 作最终律师批准。

## 3. P01—P09 全量吸收矩阵

| 研究项 | JC 必须落成 | 上游输入 | JC 禁止越界 |
| --- | --- | --- | --- |
| P01 | `HumanResearchReceiptV1` 消费、哈希绑定、缺席时降级/拒绝规则 | Legal Harness | 不组织人工工作流，不把“有人看过”当法律正确性 |
| P02 | `SourceSnapshotV2`、`EvidenceManifestV1` 完整性门 | Deli 候选包 | 不补造缺失来源，不以标题匹配代替内容哈希 |
| P03 | argument/support/attack/exception/permission/priority/cycle 正式求值 | LMM 语义版本、Deli 候选图 | 不把平面 Horn 结果冒充冲突裁决 |
| P04 | IR 驱动的 deterministic/closed-form/ASP/SMT 多后端、优化直达快路、solver receipt、UNKNOWN | LMM solver 合同 | 不用启发式或 LLM 代替 solver acceptance |
| P05 | `ProposalEnvelopeV1` 解包、污染隔离、字段级拒绝 | Deli Agent 输出 | Agent 不得签发 attestation、certificate 或 `DecisionStatus` |
| P06 | 适用时点、法源版本、失效/修订/未知时间门 | Deli 版本候选 | 不把“当前网页”自动解释为争议时点有效法 |
| P07 | 正式 `LegalSpec -> Legal-IVL -> targets`、逐跳 translation receipt、直达差分 oracle | LMM 翻译义务 | 不因 IR 文件存在即宣称语义保持 |
| P08 | `SourcePathV1` 消费、跨文书路径完整性和环/断链检查 | Deli RAG/source path | 检索相关性不得变成法律适用性 |
| P09 | 来源门、解释门、事实门分离；正式 `FactAdmissionAttestationV1` | Deli 候选、Legal Harness 批准 | 任一门通过不得替代其他门 |

## 4. 必须固化的负面研究结果

1. 原始法源结构抽取先于 IR 选择；不得先定表示再剪裁来源。
2. 简单 DOM 候选已经失败；法源快照必须保留正文、层级、版本、定位和内容哈希。
3. 平面 Horn 或 retrieval-only 无法完成 conflict-sensitive 的 exception/priority 任务。
4. argumentation 只在存在冲突结构时启用；普通无冲突链不增加 AAF 成本。
5. 双层 IR 在已测狭窄任务中没有观察到净收益；该结论只说明旧实验覆盖和实现不足，不取得产品架构否决权。
6. 正式目标保持先进双 IR：source-bound rule -> `LegalSpec` -> `Legal-IVL` -> 多后端。直达链是独立差分 oracle，并可在等价性收据成立时成为优化快路。
7. IR 全链必须通过 differential、mutation、round-trip、metamorphic 和 proof-obligation 验证；实验失败推动补全编译器和验证器，不能据此降格成影子功能。
8. 独立 checker 只证明指定算法和输入的一致性，不证明法律结论正确，更不等于 Lean proof。
9. LLM 已观察到 false accept 与 false reject；任何模型输出都保持 proposal-only。
10. source authority、fact reliability、interpretation fidelity、translation fidelity、logical correctness、execution correctness 必须是六个独立状态和收据。
11. 缺失、冲突、无法确定、solver UNKNOWN、执行中断一律 fail-closed。

## 5. 目标正式主链

```text
CaseRequestV4
  -> ProposalEnvelopeV1 quarantine
  -> SourceSnapshotV2 / SourcePathV1 verification
  -> EvidenceManifestV1 verification
  -> FactAdmissionAttestationV1 verification
  -> RulePackDescriptorV2 / RuleV4 admission
  -> LegalSpec compiler
  -> Legal-IVL lowering
  -> verified feature router
       -> deterministic Horn
       -> argumentation / grounded checker
       -> closed-form temporal or numeric evaluator
       -> ASP/SMT sidecar
  -> SemanticResultV4
  -> CheckerReceiptV2 / SolverReceiptV1 / TranslationReceiptV1
  -> FormalCertificateV1
  -> AuditBundleV2 / graph / offline replay
```

并行维护一条不共享编译器实现的 direct oracle，用于逐案差分和故障定位；只有等价性收据成立时才允许作为优化快路。任何早退都生成明确的 blocked/unknown 事件和完整失败审计，不继续伪造 canonical result 或 certificate。

## 6. W0：Git authority、基线和历史分支裁决

### 动作

1. 冻结 `main`、计划分支、upstream、HEAD、tree、版本和 worktree 状态。
2. 重跑受保护边界单测、MCP stdio authority、全量测试、in-process smoke、隐私和供应链检查。
3. 生成 current-head capability inventory；每项只能是 `IMPLEMENTED`、`PARTIAL`、`BLOCKED`、`ABSENT`。
4. 审计 `codex/lmm-runtime-receipt` 的两个提交，按文件形成 adopt/rewrite/drop 清单。
5. 审计 `schemas/w1b/` 和外部产品命名，建立 neutral v4 映射；W1b 不取得新的主合同 authority。
6. 固定一组 P01—P09 正例、反例和负向 fixture；fixture 来源、预期值和 oracle 独立记录。
7. 创建构建外 artifacts 目录，所有测试收据和临时包不得污染 tracked tree。

### 产物

- `docs/audits/current-head-baseline.json`
- `docs/audits/branch-adoption-decision.md`
- `docs/architecture/contract-authority-v4.md`
- `tests/fixtures/theory_absorption/`

### Gate

- worktree 污染、版本漂移、分支来源不明任一存在：停止 W1；
- 历史 PASS 不等于当前 PASS；
- refinement fixture 未经独立 oracle 核对，不进入主线。

## 7. W1：v4 中立合同与唯一兼容入口

### 合同

`CaseRequestV4` 最少包含：

- `request_id`
- `schema_version`
- `legal_context`
- `decision_time`
- `source_bundle_ref`
- `evidence_manifest_ref`
- `fact_attestation_refs`
- `rule_pack_ref`
- `requested_outputs`
- `proposal_refs`

`SemanticResultV4` 最少包含：

- `DecisionStatus`
- admitted/rejected fact refs
- applicable/inapplicable rule refs
- argument and attack refs
- exception/permission/priority resolution
- temporal/numeric result
- receipt refs
- completeness and interruption state
- run identity

### 动作

1. 在 `compiler_core/contracts_v4.py` 建立纯中立 dataclass/typed contract。
2. 在 `schemas/jc-v4.schema.json` 建立 JSON Schema，并增加 Python/JSON round-trip。
3. v3 和 W1b 只通过一个 adapter 进入 v4；adapter 输出 migration receipt。
4. 未知字段、重复 ID、非规范时间、浮点金额、绝对机器路径和未声明扩展 fail closed。
5. canonical serialization 对 map、set、event、graph 和错误顺序统一排序。
6. CLI、`JCClient`、MCP 均只调用同一 application service。

### Gate

- 三个入口对同一 fixture 的 canonical bytes、状态、错误码和 audit digest 完全一致；
- v3 兼容输入不能扩大权限；
- schema version 和 engine version 不匹配时明确拒绝。

## 8. W2：P02、P06、P08 来源与版本消费门

### `SourceSnapshotV2`

最少字段：`source_id`、authority tier、issuer、title、publication/effective/expiry/revision time、retrieved_at、canonical locator、raw hash、normalized hash、structure map、supersedes/superseded_by、signature/receipt ref。

### `EvidenceManifestV1`

最少字段：`evidence_id`、document hash、page/paragraph/coordinate locator、custody/provenance、fact candidate refs、contradiction refs、redaction state、review state。

### `SourcePathV1`

最少字段：有向节点/边、每边关系类型、源/目标 hash、locator、retrieval receipt、断链/环状态、路径用途。检索分数只能保存在 candidate metadata。

### 动作

1. 将现有 `source_manifest.py` 和 `source_anchor.py` 收敛到 v2 source service。
2. 同一标题不同文本必须产生不同 snapshot；同一文本的等价规范化必须可复算。
3. 适用时点先于规则选择：无 decision time、有效期冲突或版本链断裂时不得进入 formal evaluation。
4. `SourcePathV1` 仅证明材料路径存在；路径最后一跳仍须通过 source authority gate。
5. 原始材料不写入审计包；审计仅保存受控 locator、hash、必要片段摘要和外部引用。
6. Deli 输入必须经公共版本化 schema，不接受 Python 内部对象或 `sys.path` 导入。

### Gate

- hash、locator、版本、适用时点任一缺失，输出明确 blocked reason；
- 标题相同内容不同、修订后旧条文、跨文书断链、循环引用均有负向测试；
- source authority 与 legal applicability 分开记录。

## 9. W3：P09 正式事实准入

### 三门状态

1. `source_gate`：来源身份、完整性、版本和 locator。
2. `interpretation_gate`：从材料到命题的解释及争议状态。
3. `fact_gate`：命题是否达到该运行所需准入等级。

三门分别取 `PASS`、`FAIL`、`BLOCKED`、`DISPUTED`；不得相互代替。

### `FactAdmissionAttestationV1`

最少绑定：

- canonical fact proposition hash
- source/evidence refs 及 hash
- interpretation version
- admission basis
- issuer role 和权限
- issued_at / expires_at
- dispute and assumption state
- exact case/run scope
- revocation ref
- signature or approval receipt

### 动作

1. `admission.py` 成为唯一 attestation 验证 authority。
2. 外部输入、Agent、Deli 和兼容 adapter 只能提交 candidate；不能自签 attestation。
3. `UNKNOWN`、`DISPUTED`、`USER_ASSUMED` 可进入审查图，但不能创建 formal certificate。
4. attestation 对 exact proposition 和 exact source bytes 绑定；改一字即失效。
5. 撤销、过期、跨案复用、权限不足、部分证据缺失必须有拒绝事件。
6. 人工批准来自 Legal Harness 的 versioned receipt；JC 只验证格式、权限、绑定和状态。

### Gate

- 无 attestation 的事实不能进入 formal premise；
- 被拒事实仍保留审计可见性，但与 admitted fact 集物理分开；
- proposal injection、状态提权、跨案重放、旧版本重放均失败关闭。

## 10. W4：P03 冲突、例外、许可与优先级

### 前置条件

任何会改变现有 Horn、attack、exception、permission、priority 或 grounded 结果的定义，必须引用已版本化 LMM 规范、定理、有限模型或反例。没有上游语义 authority，不改正式内核。

### 正式结构

- `ArgumentV2`：argument id 由 admitted premises、rule id/version、claim、derivation path 计算。
- `AttackV2`：rebut、undercut、exception、premise challenge、priority defeat 分型。
- `PermissionV1`：许可不是普通正命题，必须保留与禁止义务的关系。
- `PriorityEdgeV1`：边有来源、适用条件和非循环要求/循环处理状态。
- `ArgumentGraphV2`：节点、typed edges、applicability、grounded labels、claim projection。

### 动作

1. `Legal-IVL` 对无冲突 Horn 和冲突论证采用统一 typed semantics；执行器可对无冲突图使用优化快路，但必须保留与完整 argument graph 的等价性测试。
2. 一条适用规则至少对应一个独立 argument，不按 claim 过早合并。
3. exception 必须攻击规则适用性或结论支持，不能仅转写为普通负事实。
4. permission 与 prohibition 冲突由明确 LMM 语义处理，不能以字符串优先级解决。
5. priority cycle、mutual attack、self-attack 和 unsupported attack 全部显式状态化。
6. independent checker 从 canonical graph 重算 grounded labels，不能调用 production evaluator 的内部缓存。
7. claim projection 在 graph acceptance 后执行；保留 argument witnesses。

### Gate

- P03 cyclic attack/exception/priority fixture 全部与独立 oracle 对齐；
- 删除任一 attack/priority edge 会触发 mutation test；
- checker disagreement 一律阻止 certificate；
- 无冲突任务不强制进入 argumentation 路径。

## 11. W5：P04 多后端、数值、时间与 ASP/SMT 路由

### 路由原则

正式运行时完整建设以下后端，并由 typed capability、复杂度和 proof obligation 决定路由：

1. `Legal-IVL` 确定性 Horn backend；
2. `Legal-IVL` argumentation backend；
3. 精确闭式时间/数值 backend；
4. ASP backend；
5. SMT backend；
6. direct oracle/verified fast path。

后端能力全部实现，不以某个简单 fixture 通过作为工程收工。单次任务仍选择与其语义需求匹配的后端，避免无意义求解成本。

### `SolverReceiptV1`

绑定：solver kind/version/binary hash、normalized problem hash、options、timeout、seed、resource limits、SAT/UNSAT/UNKNOWN、model/unsat-core hash、stdout/stderr digest、exit status、started/finished time。

### 动作

1. feature detector 只读 `Legal-IVL` typed rule/constraint，不读取自然语言标签决定路由。
2. 金额统一最小货币单位整数；比例和利率使用有理数；禁止 binary float 进入正式路径。
3. 舍入规则、边界包含性、日历、时区和期间起止全部进入输入身份。
4. ASP 用于离散组合/稳定模型需求；SMT 用于有界算术、时态和一致性义务。
5. timeout、资源耗尽、unsupported theory、UNKNOWN 不得转为 FALSE 或 PASS。
6. production solver 与 checker/fixture oracle 分离；不能用同一个函数同时生成和验证预期值。
7. direct oracle 与四类正式 backend 同期建设；前者负责差分验证和经证明的性能快路，不能取代 IR、ASP 或 SMT 的完整实现。

### Gate

- boundary、overflow、rounding、leap day、timezone、timeout 和 UNKNOWN 有负向测试；
- 同一 normalized problem 在同一 solver identity 下 receipt 可复算；
- 路由选择有 explainable feature receipt；
- 单一 backend 暂时不可用时，只有存在等价且已验证的 backend 才允许受控切换；否则明确 BLOCKED。

## 12. W6：P07 正式双 IR 编译器和翻译收据

### 正式设计

正式生产链采用双 IR：

```text
SourceSnapshotV2 / RuleV4
  -> LegalSpec
  -> Legal-IVL
  -> Horn / Argumentation / Temporal-Numeric / ASP / SMT targets
```

另建 `RuleV4 -> direct oracle`，实现上不得调用正式 compiler/lowering；它负责差分验证，并在产生等价性收据后承担优化快路。

### `TranslationReceiptV1`

每一跳绑定 source/target bytes hash、translator version/build hash、mapping table、lost/defaulted fields、proof obligations、differential result、counterexample ref、status。

### 动作

1. 原文层级、定义、条件、例外、时点、模态、优先级和来源 locator 必须可追溯到 target 节点。
2. `LegalSpec` 保留来源结构、法定术语、模态、时间和解释选择；`Legal-IVL` 统一形式算子和 backend-neutral proof obligation。
3. direct oracle 与双 IR 正式链对 P01—P09 fixtures 做 differential；差异不以修改 expected value 消除。
4. mutation test 删除/翻转 condition、exception、priority、modality 和 temporal bound，确认验证器能捕获。
5. round-trip 只证明结构可逆，不单独证明语义等价。
6. 每一层建立独立 parser、type checker、canonical serializer、lowering validator 和错误模型，禁止同一函数自证正确。
7. IR、backend 和 direct oracle 同步进入性能、正确性、可解释性和可重放基准；基准用于优化实现，不再用于否决完整架构。
8. 对增量编译、内容寻址缓存、并行 proof obligation 和结构化诊断进行正式建设，保证先进架构不是静态数据壳。

### Gate

- 任一 lost/defaulted semantic field 阻止正式编译；
- 所有差异都有 `SPEC_MISMATCH`、`IMPLEMENTATION_MISMATCH`、`TRANSLATION_MISMATCH` 或 `ORACLE_UNRESOLVED` 分类；
- 双 IR 的 public product claim 必须等全链真实运行、receipt、差分、mutation 和 replay 全部通过后发布；施工目标本身不降格。

## 13. W7：中国官方规则工程平台与首个完整规则域

### 首个完整规则域

首个规则域固定为“民事诉讼期间计算”，完整覆盖该域的文书类型、期间类型、起算、届满、顺延、中止/中断（适用时）、法定例外、程序阶段和版本时点。民事裁判文书上诉期间只是其中一组端到端验收 fixture，不是最终施工边界。

平台同时建设来源摄取、结构抽取、规则编译、人工复核、版本演进、签名构建、回归、废止和回滚能力。完成首域后按相同协议持续扩展其他规则域，不把 pilot 当产品终点。

### 流水线

```text
first-party source snapshot
  -> structure extraction
  -> candidate RuleV4
  -> source/interpretation/legal review
  -> mutation and boundary fixtures
  -> LMM semantic conformance
  -> human promotion receipt
  -> signed pack build
  -> JC load/replay
```

### 动作

1. `cn-official` 在来源与正式规则未就绪前继续 blocked；新建完整 staging/build/release 分层，不原地解锁空包。
2. 每条规则绑定精确官方文本快照、条款 locator、公布/施行/修订状态。
3. 法律解释、工程编码和测试预期由不同字段、不同收据承载。
4. 规则晋级由外部人工授权；manifest 状态不能由生成器自动修改。
5. 真实 pilot 使用去标识化合成边界事实，不写入私人案件。
6. 首域未完成时对外状态只能是 `BLOCKED` 或 `PARTIAL`，不能借基础设施 PASS 宣称法律内容 ready；但施工不得停在基础设施或单规则样例。

### Gate

- 第一方来源无法稳定取得：保持 blocked，不以第三方文本替代；
- 每条规则均能回到 snapshot 和 locator；
- 有效期、起算边界、文书类型和例外 mutation 均能改变预期结果；
- 法律审核收据和运行时收据分离。

## 14. W8：build-bound certificate、audit 与 replay

### `RunIdentityV2`

绑定 engine commit/tree/version、wheel/package hash、schema、request、source bundle、evidence manifest、attestations、pack build、compiler、router、solver/checker/translator identity、runtime options。

### 收据分离

- `AdmissionReceiptV1`：准入算法和输入一致性。
- `TranslationReceiptV1`：表示转换和字段保持。
- `CheckerReceiptV2`：argument/evaluation 重算一致性。
- `SolverReceiptV1`：solver 实际运行及结果。
- `ProofReceiptV1`：LMM/Lean theorem、构建和 TCB 引用。
- `HumanApprovalReceiptV1`：律师/规则维护者的授权事实。

任一收据不能冒充另一种证明。

### `FormalCertificateV1`

只在以下条件全部满足时生成：source、fact、rule、translation、evaluation、checker、solver（如使用）、completeness、build identity、replay prerequisites 均 PASS，且不存在 DISPUTED/UNKNOWN/partial/truncated。

### `AuditBundleV2`

必须包含 canonical request/result/events/graph、全部必要 schema、pack material 或内容寻址副本、receipt、run identity、manifest 和 replay 指令；不得包含原始私人叙事、机器绝对路径或密钥。

### 动作

1. bundle 原子写入 Git tree 外目录；失败时只留下可识别 incomplete marker。
2. replay 必须在移动仓库、断网和短临时路径下重算 bytes 与 semantic result。
3. exact replay 与 semantic replay 分开；任何允许差异都进入显式 policy。
4. graph 只从已完成 canonical events/result 派生，renderer 不得重新求值。
5. certificate checker 不导入 production evaluator 私有状态。

### Gate

- 改动任一输入、receipt、pack、binary identity 或 event 顺序都会破坏校验；
- partial/truncated/unknown 无 certificate；
- moved-repo offline replay PASS；
- bundle 隐私、路径和 disclosure 扫描 PASS。

## 15. W9：接口一致性、模块 authority 和真实验收

### 公共入口

1. CLI：文件/stdin 输入，stdout 仅协议输出，stderr 日志，稳定 exit code。
2. `JCClient`：同一 application service，同一 canonical contract。
3. MCP：四工具、零资源边界保持；stdio subprocess 是 transport authority。

### 外仓协议

- Deli 只能通过 `JCClient`、版本化 CLI JSON 或 MCP 提交 candidate bundle。
- Legal Harness 只能通过公共接口提交 attestation/approval refs 和案件运行请求。
- LMM 只通过 versioned semantic manifest、proof receipt 和 refinement fixtures 约束 JC。
- 禁止任何外仓 `sys.path` 导入 `compiler_core` 内部模块。

### 模块 authority 收敛

对 `compiler_core` 全量模块建立四类清册：

- `FORMAL_CORE`：唯一正式主链；
- `ADVISORY`：只能输出候选/审查建议；
- `COMPATIBILITY`：有明确迁移终点的兼容层；
- `REMOVE_OR_EXTERNALIZE`：工作流、私域或无真实调用者模块。

重点核查 `legal_compiler.py`、`legal_ir_v3.py`、`transformer.py`、`proleg_translator.py`、`spec_shadow_harness.py`、`smt_sidecar.py`、各种 domain/workflow 模块，消除多条自称正式的旁路。

### 真实验收

1. P01—P09 每项至少一组正例、一组负例、一组缺失/冲突例。
2. 首个完整官方规则域从 snapshot 到离线 replay 全部跑通。
3. 同一请求经 CLI、`JCClient`、MCP 的 canonical result 与 audit digest 相同。
4. Deli candidate 不能提权；Legal Harness 没有批准收据时不能 formal；LMM mismatch 时不能 certificate。
5. protocol smoke、mock、schema validate、文件存在、历史测试数字均不得单独宣告完成。
6. 发布前执行全量测试、MCP stdio、wheel fresh install、pip-audit、隐私、stale narrative、disclosure 和 Git clean gate。

## 16. 文件级施工地图

| 现有/新增位置 | 施工内容 |
| --- | --- |
| `compiler_core/contracts.py` | 保留 v3 兼容；禁止继续增加 v4 权威字段 |
| `compiler_core/contracts_v4.py` | 新增 v4 中立合同和 canonical validation |
| `schemas/jc-v4.schema.json` | 新增唯一 v4 JSON authority |
| `compiler_core/admission.py` | 唯一事实 attestation 验证入口 |
| `compiler_core/source_manifest.py` | 迁移为 SourceSnapshotV2 service |
| `compiler_core/source_anchor.py` | locator 和内容哈希验证 |
| `compiler_core/rule_packs.py` | pack build attestation、版本和晋级收据 |
| `compiler_core/evaluator.py` | 执行 Legal-IVL；保留独立 direct oracle/verified fast path；typed interruption |
| `compiler_core/argumentation.py` | ArgumentV2/AttackV2/ArgumentGraphV2 |
| `compiler_core/independent_grounded_checker.py` | 从 canonical graph 独立重算 |
| `compiler_core/rule_router.py` | Legal-IVL feature-based 多后端路由和等价 fast-path policy |
| `compiler_core/smt_sidecar.py` | 真实 solver process、限制和 SolverReceiptV1 |
| `compiler_core/legal_ir_v3.py` | 升级/替换为正式 LegalSpec 与 Legal-IVL；提供版本化迁移 |
| `compiler_core/spec_shadow_harness.py` | 改造成双 IR 与独立 direct oracle 的 differential/mutation harness |
| `compiler_core/audit_bundle.py` | AuditBundleV2、原子写入、离线自足 replay |
| `compiler_core/certificate_checker.py` | FormalCertificateV1 条件和收据分离 |
| `compiler_core/application.py` | CLI/Client/MCP 唯一服务层 |
| `compiler_core/client.py` | 稳定公共 API，不泄漏内部对象 |
| `compiler_core/cli.py` | v4 输入、稳定 exit code、receipt 输出 |
| `mcp_server.py` / MCP adapter | 仅协议适配，不复制业务逻辑 |
| `configs/packs/cn-official/` | 完整 staging/build/release 结构与首个规则域 |
| `tests/fixtures/theory_absorption/` | P01—P09 独立 oracle fixtures |
| `tests/unit/` | 合同、准入、argument、router、receipt 单测 |
| `tests/integration/` | 三入口一致性、外仓协议、离线 replay |
| `docs/contracts/` | v4、收据、certificate、replay 规范 |

## 17. 测试与证据门

按风险由窄到宽执行：

1. schema/contract round-trip；
2. fact/rule admission；
3. P03 argumentation differential；
4. P04 temporal/numeric/solver boundary；
5. P07 translation differential/mutation/metamorphic/proof-obligation；
6. certificate tamper；
7. audit/replay；
8. CLI/Client/MCP parity；
9. 现有受保护边界测试；
10. 全量 tests；
11. stdio subprocess MCP；
12. clean wheel/fresh install；
13. supply-chain、隐私、disclosure、stale narrative。

证据等级必须写清：runtime test、differential fixture、finite SMT check、upstream Lean theorem、human legal review 或 empirical heuristic。不得混写为统一 PASS。

## 18. 迁移、回滚与 Git

- 每波独立 feature branch 和本地提交；前一 Gate 未过不进入后一波。
- v3 adapter 至少保留一个明确迁移周期；兼容层不得授予 v4 没有的权限。
- 新 v4、双 IR、多 backend 和官方规则平台在施工分支全量建设；仅在完成 Gate 前不切换公开稳定入口，不把 feature flag 当作长期半成品。
- 回滚使用 revert 或关闭 feature flag，不使用 hard reset。
- W4/W5/W6 若失败，保留现有 v3 受保护内核，结果标记 review-only/blocked，不降低门禁。
- W7 官方来源受阻，保持 `cn-official` blocked，不用候选/第三方语料顶替。
- 不推送、不打 tag、不发布、不改变 GitHub 可见性，除非用户当轮明确授权。

## 19. Definition of Done

以下全部满足，才算本仓吸收完成：

- v4 合同、v3/W1b 兼容和三入口只有一个 authority。
- P01—P09 均有运行时消费点、正负 fixture、收据和 fail-closed 状态。
- P03 冲突结构有版本化 LMM 语义、production evaluator 和独立 checker。
- P04 `Legal-IVL` 多后端 router、独立 direct oracle、数值/时间精确语义和真实 solver receipt 完整。
- P07 双 IR 已成为真实生产编译链，逐跳验证、差分、mutation、增量编译和 replay 完整。
- P09 三门准入物理分离，外部候选无法创建 `verified_fact`。
- 首个完整官方规则域有第一方 snapshot、人工晋级和端到端 replay，平台可继续规模化扩展。
- certificate、audit、graph 和 replay 绑定 exact build 与全部关键输入。
- CLI、`JCClient`、MCP canonical parity 通过。
- 私有案件、商业规则、律师工作流和研究抓取未进入公开内核。
- 当前机器全量 Gate 通过且 Git clean；历史 PASS 不代替当前证据。

## 20. 施工顺序

严格执行：

```text
W0 -> W1 -> W2 -> W3 -> W4 -> W5 -> W6 -> W7 -> W8 -> W9
```

W0 先裁决历史分支；W1—W3 建立合同、来源和事实地基；W4—W6 完整实现论证、正式双 IR 和所有规划 backend；W7 建成官方规则工程平台和首个完整规则域；W8—W9 收口证书、审计、接口和真实验收。Gate 只控制质量和依赖，不是缩减范围或中途收工的理由；授权开始施工后应持续做到 W9 完成。

### [我违规之处]

- 无
