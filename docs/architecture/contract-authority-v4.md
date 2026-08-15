# 合同 Authority 清册（v4 施工基准）

状态：W0 建立；随 W1 施工生效更新。
依据：20260815 施工方案 §6 动作 5、§7、§16。

## 1. Authority 规则

1. v4 施工完成后，`compiler_core/contracts_v4.py` + `schemas/jc-v4.schema.json` 是唯一 v4 权威；二者字段必须逐一对应，round-trip 测试强制。
2. v3（`compiler_core/contracts.py` + `schemas/jc-v3.schema.json`）与 W1b（`schemas/w1b/*.schema.json`）冻结：禁止再增加权威字段；只能通过唯一 adapter 投影到 v4，adapter 输出 migration receipt。
3. 兼容层不得授予 v4 没有的权限（方案 §7 Gate、§18）。
4. 外部产品命名（LegalOS、LCCC、Deli、WorkBuddy 等）不出现在 v4 中立合同字段名中；仅允许出现在 adapter 文档与外仓协议章节。

## 2. 当前合同清册（W0 冻结快照）

| 合同/schema | 位置 | 当前 authority 级别 | v4 施工后级别 |
| --- | --- | --- | --- |
| `CaseRequest` / `SemanticResult`（v3） | `compiler_core/contracts.py` | v3 唯一权威 | COMPATIBILITY：只进 adapter |
| `schemas/jc-v3.schema.json` | `schemas/` | v3 JSON authority | COMPATIBILITY |
| `JCCaseRequest`（W1b） | `schemas/w1b/case-request.schema.json` | W1b 外部消费合同 | COMPATIBILITY：adapter 输入之一 |
| `JCRuleAdmissionRequest`（W1b） | `schemas/w1b/rule-admission-request.schema.json` | W1b 准入请求合同 | COMPATIBILITY：映射到 v4 rule admission |
| `JCAdmissionResult`（W1b） | `schemas/w1b/admission-result.schema.json` | W1b 准入结果合同 | COMPATIBILITY：由 v4 admission receipt 投影 |
| `JCProofBundleRef`（W1b） | `schemas/w1b/proof-bundle-ref.schema.json` | W1b 证明包引用 | COMPATIBILITY：映射到 v4 receipt refs |
| `CaseRequestV4` / `SemanticResultV4` | 待建 `contracts_v4.py` / `jc-v4.schema.json` | 不存在（ABSENT） | v4 唯一权威 |

W1b 不取得新的主合同 authority（方案 §6 动作 5）：上述 W1b schema 保持“外部消费投影”地位，任何 v4 字段变更不反向服从 W1b 命名。

## 3. W1b → v4 中立映射

| W1b 字段 | v4 中立字段（CaseRequestV4） | 备注 |
| --- | --- | --- |
| `schema_version`（const `"3.0"`） | `schema_version`（`jc/4.0`） | 版本不匹配必须显式拒绝 |
| `jurisdiction` / `governing_law` | `legal_context.jurisdiction` / `legal_context.governing_law` | 结构化为 legal_context |
| `as_of_date` | `decision_time` | v4 要求规范 RFC3339；非规范时间 fail closed |
| `facts[].status=verified_fact` 自报 | 禁止 | 外部输入只能提交 candidate；verified 状态只来自 `FactAdmissionAttestationV1`（W3） |
| `facts[]` | `proposal_refs` + `fact_attestation_refs` | 事实内容与准入凭据分离 |
| `rule_pack_id` / `rule_pack_version` / `rule_pack_digest` | `rule_pack_ref`（三元组结构） | digest 必须 sha256 |
| `external_source_refs` | `source_bundle_ref` / `evidence_manifest_ref` | W2 合同接管 |
| 无对应 | `request_id`、`requested_outputs` | v4 新增必填 |

| W1b 准入合同 | v4 对应 | 备注 |
| --- | --- | --- |
| `JCRuleAdmissionRequest.snapshot_verification_receipt` | `SourceSnapshotV2` 完整性门（W2） | `result=verified` 语义保留 |
| `JCRuleAdmissionRequest.fact_approval_ref` | `FactAdmissionAttestationV1` 消费（W3） | evidence_anchor_refs → evidence manifest refs |
| `JCRuleAdmissionRequest.locator` | `SourceSnapshotV2.canonical_locator` | page_map_status 进入 locator 校验状态 |
| `JCAdmissionResult.status` | v4 admission receipt status | `produced_by=jc` 不变：JC 独立拥有准入终态 |
| `JCProofBundleRef` | receipt refs（`CheckerReceiptV2`/`SolverReceiptV1`/…） | 收据分离后按类型引用 |

## 4. adapter 约束（W1 落实）

1. 唯一兼容入口：`compiler_core/compat_v3_v4.py`（W1 新建），CLI/Client/MCP 不得各自携带兼容逻辑。
2. adapter 输出 migration receipt：记录来源 schema 版本、字段映射、defaulted 字段、被拒字段；defaulted 字段不得静默扩权。
3. v3/W1b 输入中出现未知字段、重复 ID、绝对机器路径、浮点金额 → fail closed，错误码与 v4 主链一致。
4. adapter 不得读取 v4 内部状态；只消费 v4 公共验证函数。

## 5. 外仓命名隔离

- `owner: lccc|legalos` 等外部枚举只存在于 W1b 兼容 schema；v4 使用中立 issuer/role 词汇表。
- Deli 候选、Legal Harness 批准、LMM 语义清单的入口在 W9 外仓协议中定义，均通过公共接口。
