# Juris Calculus V4 单主链生产投产全量代码审计

审计日期：2026-08-19

结论：**No-Go**

问题计数：**P0 15 / P1 20 / P2 7 / P3 2**

审计性质：只读代码审计；**本轮没有修复任何 Bug**。

## 1. 审计基线、范围、限制

### 1.1 已锁定边界

- 当前产品、公共 API、CLI、Client、MCP、Schema、正式运行链必须全部 V4。
- 当前 runtime 不保留 V3/W1b adapter、fallback、auto-upgrade、双写或双 authority。
- V3 历史结果只允许冻结 tag、wheel、lock、隔离环境回放。
- 顺序固定为：V4 单主链闭环 → 真实 `cn-official` → DSH formal profile。
- 通用 DSH 不依赖 JC；只有 formal legal profile 强制经过 JC，并以可独立验证的 JC 证书为交付条件。

### 1.2 Git 基线

| 项目 | 值 |
| --- | --- |
| 本地分支 | `main` |
| 本地 HEAD | `bfd90f9124fb6930f7dc6596c739ac1e5ef1c319` |
| 本地 tree | `b30441f66e8576c0b1e24e731b1306452816de06` |
| HEAD 主题 | `docs(plan): define V4-only production cutover` |
| 远端默认分支/HEAD | `main` / `6f4f91a67047d0beef0ed43acf55d3a2b3803015` |
| 本地相对远端 | ahead 1 / behind 0（审计报告提交前） |
| 最新 tag | `v3.0.2`；HEAD 在其后 22 commits、101 个 changed files |
| 源码版本 | `compiler_core/version.py:3` 仍为 `3.0.2` |
| 用户既有改动 | 两份 tracked 施工方案被删除且未暂存；本轮未恢复、未提交 |

远端元数据于 2026-08-19 通过 GitHub API 与 `git ls-remote` 复核：[JC 仓库](https://github.com/laubeing-droid/juris-calculus)、[最近成功 CI 31927470559](https://github.com/laubeing-droid/juris-calculus/actions/runs/31927470559)、[v3.0.2 release](https://github.com/laubeing-droid/juris-calculus/releases/tag/v3.0.2)。该 CI 对应远端 `6f4f91a...`，不对应本地 `bfd90f9...`；唯一 release 没有资产。

### 1.3 方法和限制

- 静态：`git ls-tree/ls-files`、`rg`、Python AST、逐入口 import/call trace、Schema/manifest/contract 对照、wheel RECORD。
- 动态：最小反例、Python 3.11/3.12 全集测试、MCP stdio、双构建、干净 wheel 安装、CLI/pack/evaluate、供应链、SBOM、provenance。
- 三个只读分域审计结果均由主审再次核到源码行号或动态结果；未把子审结论直接复制为事实。
- 未执行破坏性 TOCTOU、junction、DACL、掉电、磁盘满、100 进程竞争实验；这些列入第 19 节。
- 没有 production key、正式 trust store、真实 `cn-official`、生产 state provider、DSH deployment；因此不能验证正式签名、法律规则正确性、真实吞吐和灾备。

## 2. Git、文件、测试、构建定量盘点

| 项目 | 结果 |
| --- | --- |
| HEAD tracked entries | 292；全部 `100644` regular blobs；15,907,000 bytes |
| Python | production 120 files / 约 23,160 物理行；tests 71 files / 约 8,912 物理行 |
| 测试静态量 | 68 test modules；496 test definitions；11 parametrize；4 pytest fixtures；0 xfail |
| 跳过 | 3 个整文件、28 个用例：`test_adversarial.py`、`test_trirail_collision.py`、`test_zh_rules.py` |
| 测试层级 | `tests/unit` + fixtures；无独立 integration/E2E/security/chaos/packaging 目录 |
| Python 3.12.5 全集 | exit 1；505 passed / 28 skipped / 5 failed；167.74 s |
| Python 3.11.15 全集 | exit 1；505 passed / 28 skipped / 5 failed；236.06 s |
| MCP 专项 | exit 0；8 passed；自检 exit 0，但报告 V3.0.2、4 tools、0 resources、readiness false |
| 双 wheel | 两份 2,656,407 bytes，SHA-256 均为 `20cdecc1c07e843c79fdd45faea790746d3f9b31b41df47db1c3bf77d5de7ddf` |
| wheel 条目 | 157：core 90、addons 9、pipeline 11、configs 38、schemas 3、dist-info 6 |
| 供应链 | `core.lock` pip-audit exit 0，当前 0 known vulnerabilities；SBOM exit 0 |
| 安装后正式运行 | `doctor` / `packs verify cn-official` / `evaluate` 均 exit 3（blocked） |

五个全集失败均来自 `tests/unit/test_spec_shadow_harness.py`：硬编码/环境指定的 `D:/Codex/数学证明/legal-math-modeling` 不存在，且在 `D:/Codex` 未找到 `reference_semantics.py` 或 `certificate_schema.py`。因此本地全集不是绿色，也不是自包含测试。

## 3. 292 个 tracked 文件完整覆盖证明

分类规则按路径和已登记 authority 顺序单值判定；附录 A 列出全部 292 行。规范编码为：按 path 升序、UTF-8、每行 `path<TAB>primary-role<LF>`。

| 唯一主类 | 数量 |
| --- | ---: |
| production-code | 70 |
| tests | 71 |
| Schema/protocol | 7 |
| config/rule-pack | 34 |
| CLI/Client/MCP | 5 |
| CI/build/release | 12 |
| docs/baseline/memory | 26 |
| fixture/generated | 19 |
| legacy/candidate/advisory | 45 |
| other-assets | 3 |
| **合计** | **292** |

校验：HEAD paths 292；分类 rows 292；unique paths 292；missing 0；extra 0；duplicate 0。映射 SHA-256：`3b92c71964bfaf37e8bbb0c660b16f5aa2b3e8c8e4abad6b0890f94faa367fd2`。

“production-code”只是文件主类，不表示正式生产可达；其内大量模块被 `module-authority-v4.json` 列为 advisory。生产可达性见第 5 节。

## 4. 三入口到证书、审计包、回放的真实调用图

```text
jc evaluate                 JCClient.evaluate              MCP evaluate_case
compiler_core/cli.py        compiler_core/client.py         addons/workbuddy_mcp.py
        │                          │                              │
        └────────────── CaseRequest.from_dict (V3) ──────────────┘
                                   │
                    evaluate_to_audit_bundle (V3)
                    compiler_core/audit_bundle.py
                                   │
                    application.evaluate (V3 orchestrator)
                                   │
       RulePackRegistry → V3 RulePackDescriptor / YAML loader
                                   │
       domain_config fallback → FixpointEvaluator / old argumentation
                                   │
       reasoning_boundary / checker → litigation_engineering certificate draft
                                   │
       仅取 certificate.verifiable 布尔值；证书对象被丢弃
                                   │
       AuditBundle schema 1.0 writer → COMPLETE → V3 replay
```

证据：

- CLI：`compiler_core/cli.py:17-24,445-475`。
- Client：`compiler_core/client.py:9-19,36-43`。
- MCP：`addons/workbuddy_mcp.py:12-18,208-228`。
- V3 orchestrator：`compiler_core/application.py:1,14-30,46-202`。
- audit/write/reuse：`compiler_core/audit_bundle.py:121-155,448-502`。
- pack loader：`compiler_core/rule_packs.py:194-268`。
- 证书草稿被折成布尔值：`compiler_core/application.py:650-659,719-757`。
- V4 `AuditBundleV2` 仅为数据类，无 production writer/replay：`compiler_core/certificate_v1.py:197-247`。

结论：三个入口共享的是 **V3 Application**，不是 `ApplicationV4`。V4 staged modules 没有形成从公共请求到证书、审计包、回放的生产链。

## 5. V4 生产可达矩阵

| V4 能力 | 当前消费者 | 生产状态 | 判定 |
| --- | --- | --- | --- |
| `contracts_v4` | `compat_v3_v4`、unit tests | 三入口零引用 | 孤岛/兼容旁路 |
| `source_service_v2` | unit tests | Application 不调用 | 测试专用 staged |
| `fact_admission_v1` | unit tests | V3 fact status 仍生效 | 测试专用 staged |
| `rule_platform_cn` | unit tests | 不生成可执行 RuleV4/pack | 模拟治理孤岛 |
| `argumentation_v2` | unit tests | production 用旧 argumentation/evaluator | 测试专用 staged |
| `legal_spec_ivl` | unit tests | 无 pack/application consumer | 孤立 compiler |
| `backend_router_v1` | unit tests | 不调用真实 provider | DTO/router 孤岛 |
| `certificate_v1` | unit tests | Application 不调用 | 未接入、可伪造 |
| `AuditBundleV2` | 无 production writer | V3 storage schema 1.0 | 数据类孤岛 |
| `CaseRequestV4 → SemanticResultV4` | 无 ApplicationV4 | 不存在纵向 E2E | 未实现 |

## 6. V3、W1b、legacy、advisory、candidate 残留矩阵

| 残留 | 当前位置/行为 | wheel | 正式影响 |
| --- | --- | --- | --- |
| V3 public API | `compiler_core/__init__.py:1-45` | 是 | 当前唯一公共边界 |
| V3 request/application | `contracts.py`、`application.py` | 是 | 三入口实际执行 |
| V3 schema | `schemas/jc-v3.schema.json` | 是 | doctor 将其当 schema |
| V3 IR | `compiler_core/legal_ir_v3.py` | 是 | compatibility 模块仍发布 |
| V3→V4 adapter | `compiler_core/compat_v3_v4.py` | 是 | 违反零兼容决策 |
| W1b | `schemas/w1b/**` + tests | schemas 未入 wheel、源码仍 active | 多协议权威 |
| legacy packs | 4 packs，21,481 candidate rules | manifests/底层 corpora 全入 wheel | 0 reasoning eligible |
| advisory core | authority registry 中 40 个 advisory | 大量入 wheel | formal/advisory 物理边界未建立 |
| addons/WorkBuddy | `addons/**` | 9 entries | formal MCP 与 advisory 同包 |
| pipeline/实验 LLM | `pipeline/**` | 11 entries | 网络/规则工程面进入生产包 |

安装后 `packs verify --all --json`：总 candidate 21,481，总 reasoning eligible 0；`cn-official` 为 0 rules、blocked、缺 build attestation，却显示 `integrity_valid=true`。

## 7. Python contract—JSON Schema—MCP manifest 一致性矩阵

| 对象/字段 | Python | JSON Schema | MCP | 结果 |
| --- | --- | --- | --- | --- |
| 当前请求 | V3 `CaseRequest` | wheel 同时带 V3/V4 | `evaluate_case` 解析 V3 | V4 未成为公共合同 |
| `schema_version` | V4 只接受 `jc/4.0` | V4 const | MCP 无 V4 envelope | 不闭合 |
| engine match | `major >= 3` | 无等价门 | 无 | V3.0.2 被 V4 接受 |
| `fact_attestation_refs` | `tuple(value)`，字符串会拆字符 | array of string | 无 V4 校验 | Python/Schema 分裂 |
| nested numeric | float 检查只递归 Mapping | Schema 约束局部 | 无 | list 内 float 可进入 |
| RFC3339/date | Python calendar/time regex | Schema regex 可接非法日历日 | 无统一 codec | 接受集不同 |
| `run_identity` | 开放 `Mapping` | 开放 object | 响应不返回 | 正式身份无封闭字段集 |
| result subobjects | 开放 `Mapping` | 多处任意 object | output 不按 schema 验证 | 可塞未声明状态 |
| MCP error | `engine_error` / admission blocked | manifest error schema 多版本 | `isError` 仅识别 literal `error` | 失败可呈协议成功 |
| manifest authority | 内嵌 DEFAULT、根 manifest | 两者不同 | tools/list 用所选 manifest、parser 固定 DEFAULT | 三重真源 |

最小动态结果：`'ab' → ('a','b')`；list 内 `1.5` 被接受；`require_engine_match('3.0.2')` 成功；V4 request digest 不能构造 certificate request identity。

## 8. digest、identity、trust 组合矩阵

| 对象 | 当前 grammar/来源 | 是否复算真实对象 | 能否直接组合 | 结论 |
| --- | --- | --- | --- | --- |
| JCS digest | `sha256-<hex>` | 对 Python object 复算 | 与其他 V4 receipt 不兼容 | FAIL |
| CaseRequestV4 | `sha256-` | 是 | RunIdentity 只收 `sha256:` | FAIL |
| SourceSnapshot | `sha256:` 字符串 | 只验格式；不取源字节/签名 | 可由调用者伪造 | FAIL |
| Fact attestation | `sha256:` + receipt ref | proposition hash 可复算；签名/ref 不解析 | 调用者可注册 | FAIL |
| Rule pack | 裸 64 hex | hash 后重新开文件求值 | 存在 TOCTOU | FAIL |
| build attestation | 64 hex/commit 字符串 | 不验签，不绑定 HEAD/tree | run identity 不消费 | FAIL |
| IR receipts | `sha256-` receipt digest、内部 source/target 为 `sha256:` | 只证明当前降级对象 | AuditBundleV2 receipt refs 不收 `sha256-` | FAIL |
| SolverReceipt | `sha256:` 字段 | caller DTO；无 provider invocation | 可挪用/伪造 | FAIL |
| FormalCertificate | caller gate/receipts/digests | 不解析 issuer/signature/trust store | 可直接 `issued=True` | FAIL |
| AuditBundleV2 | caller digests | 无 writer/verifier/replay | 与实际 receipt grammar 冲突 | FAIL |
| V3 run ID | version/profile/request/pack | 不绑定 commit/tree/wheel/config/backend | 同版本不同 build 可碰撞 | FAIL |
| wheel provenance | commit + wheel hash | 构建工具可生成 | release 不发布/签名 | PARTIAL |

`compiler_core/jcs.py:125-126` 与 [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) 不一致的动态向量：JC 输出 `\\u000a`、`1e21`、保留 `9007199254740993`；Node 24 输出短换行 escape、`1e+21`、IEEE-754 值 `9007199254740992`。跨语言身份不能假定一致。

## 9. 严重级别总表

### P0（15）

| ID | 标题 |
| --- | --- |
| P0-01 | 三公共入口和包根仍是 V3；不存在 ApplicationV4 单主链 |
| P0-02 | 正式生产零产出：外部 verified 降级，`cn-official` 空，全部 pack 0 eligible |
| P0-03 | V4 digest grammar 自相矛盾，request/receipt/bundle 无法组合 |
| P0-04 | Source/Fact trust 仅信 caller 对象和字符串 ref，可伪造 PASS |
| P0-05 | RulePlatform 可把非可执行 candidate 伪激活，未生成/绑定真实 pack |
| P0-06 | Backend 不执行 solver/provider，SolverReceipt 为 caller DTO |
| P0-07 | FormalCertificate/AuditBundleV2 信 caller 自报 gate/digest，无签名验证 |
| P0-08 | V3 Application 丢弃证书，只用 advisory `verifiable` 布尔值宣告 formal |
| P0-09 | MCP 将 blocked/engine_error 呈现为协议成功，且没有 verify/read 闭环 |
| P0-10 | MCP 可读取任意本地/UNC/device 路径 |
| P0-11 | pack verify→重开→求值 TOCTOU，可在摘要 A 下执行字节 B |
| P0-12 | 已有 COMPLETE 可返回旧 digest + 本次新 result；run identity 不绑 build |
| P0-13 | state 子目录 symlink/junction 可逃逸并重定向事实/缓存/审计写入 |
| P0-14 | production wheel 混装 V3/compat/advisory/candidate/network/pipeline 面 |
| P0-15 | tag/version/release 未绑定，可发布错误 commit 或无产物 release |

### P1（20）

| ID | 标题 |
| --- | --- |
| P1-01 | JCS 不满足跨语言 RFC 8785/IEEE-754 约束 |
| P1-02 | V4 Python/Schema 对 tuple、float、date、开放 object 接受集分裂 |
| P1-03 | source/fact/IR 用 RFC3339 字符串比较时间，含小数秒时结论反转 |
| P1-04 | SourcePath 只查 hash/cycle，不查单根连通性，断链图可 PASS |
| P1-05 | LegalSpec/IVL 丢 authority/terms/interpretation/source，却发 PASS 收据 |
| P1-06 | argumentation priority 不生效、UNDEC 却 accepted、witness 被覆盖 |
| P1-07 | evaluator 丢 namespace/domain，正式 patch 配置不实际生效 |
| P1-08 | pack attestation 只验格式且空 official 可 integrity valid |
| P1-09 | CLI lookup 将有 source anchor 的 candidate 错标 reasoning eligible |
| P1-10 | run/pack 无跨进程锁；固定 staging 和残留会永久阻断重试 |
| P1-11 | 仅 fsync 文件，不 fsync 目录/pack copy，成功后掉电不可保证重放 |
| P1-12 | Windows DACL 未验证却 fail-open，doctor 仍判 state present |
| P1-13 | V3/V4 state/cache 无 generation 隔离，V4 writer/replay 不存在 |
| P1-14 | MCP manifest 多真源且 input/output schema 不对真实 codec 做闭环验证 |
| P1-15 | MCP/JSON/index/state 无完整大小、深度、超时、取消、背压、配额 |
| P1-16 | domain config 缺失/损坏被吞并回退到可变全局默认 |
| P1-17 | 路径隐私黑名单不完整，capabilities 主动输出绝对安装路径 |
| P1-18 | MCP 将 ENOSPC/EACCES 等 OSError 误报无重试 INVALID_TOOL_INPUT |
| P1-19 | wheel gate 仅短 blacklist + import smoke，不能证明 V4 formal-only |
| P1-20 | 仅 core.lock 完整 hash；dev/optional 传递依赖和 release 证据未锁闭 |

### P2（7）/P3（2）

- P2-01：全集测试依赖仓库外 companion checkout，本地两个 Python 矩阵均失败。
- P2-02：28 个用例整文件 skip；无独立 production installed E2E/security/concurrency/chaos 目录。
- P2-03：多项测试直接构造 trusted fact、PASS gate、receipt，或明确接受 V3 engine/compat 错误行为。
- P2-04：README/CHANGELOG/HANDOFF/baseline/memory、两份 module registry 同时声称不同当前事实。
- P2-05：DSH 为 developer preview，正式 adapter 必须 pin commit 并有兼容性合同测试。
- P2-06：`wheel_gate.py` 从无 `.git` 的归档源码执行会失败，发布检查耦合 Git checkout。
- P2-07：安装包根没有 `compiler_core.__version__`，版本只能从子模块/CLI 取得。
- P3-01：`packs verify --all --json` 默认输出 21,481 个 ID，机器输出过大且不利诊断。
- P3-02：V2→V3、W1b、WorkBuddy 历史指南仍处 current docs，需归档而非继续维护。

## 10. P0/P1 证据、复现和修复测试设计

### P0-01　三入口仍是 V3

- **证据**：`compiler_core/__init__.py:1-16,26-45`；`compiler_core/cli.py:17-24,445-475`；`compiler_core/client.py:9-19,36-43`；`addons/workbuddy_mcp.py:12-18,208-216`；`compiler_core/application.py:1,14-30`；`compiler_core/version.py:3`。
- **当前/触发**：调用任一 CLI/Client/MCP evaluate，均解析 `compiler_core.contracts.CaseRequest` 并进入 V3 audit/application。
- **影响**：V4 单主链、正式 `cn-official`、DSH formal 的共同前提不存在；所有当前运行仍是 V3。
- **根因**：V4 以并列模块加入，没有入口、公共导出、状态、协议的原子 cutover。
- **修复**：建立唯一 ApplicationV4；同一 cutover commit 切包根、CLI、Client、formal MCP、Schema、manifest，删除 V3/W1b/compat runtime。
- **测试**：安装 wheel 后三入口同一 V4 vector 输出逐字节同构；AST/import gate 保证旧模块零生产入边；V3 payload/import 必须失败。
- **依赖**：先解决 P0-03～P0-07 和 P1-01～P1-06。

### P0-02　正式运行零产出

- **证据**：`compiler_core/contracts.py:160-170,910-930`；`tests/unit/test_application_service.py:119-133`；`configs/packs/cn-official/manifest.yaml:1-18`。
- **当前/触发**：公开 `from_dict` 把 caller 的 `verified_fact` 降为 checked；正式成功测试绕过 parser 直接构造 trusted fact。安装后 official pack 验证/求值 exit 3。
- **影响**：公共生产请求不能形成正式前提；`cn-official` 0 rule；其余四 pack 合计 21,481 candidate、0 eligible。
- **根因**：事实准入、正式 pack 与公共入口没有纵向闭环。
- **修复**：外部请求只能提交 candidate/artifact refs；由 V4 trust/admission service 生成不可伪造 admission；真实 signed pack 只在 kernel RC 后建设。
- **测试**：通过唯一外部 codec 的 synthetic signed pack 正向 E2E；缺任一 source/fact/signature/role/pack 字节必阻断；禁止测试直构 trusted 内部对象替代入口。
- **依赖**：P0-01、P0-04、P0-05。

### P0-03　V4 digest 无法组合

- **证据**：`compiler_core/jcs.py:125-126`；`compiler_core/contracts_v4.py:66,104-106,289-290`；`compiler_core/certificate_v1.py:53,73-75,107-108,219-225`；`compiler_core/source_service_v2.py:26,66-68`。
- **当前/触发**：`CaseRequestV4.canonical_digest()` 产出 `sha256-...`，RunIdentity/receipt/bundle 多数要求 `sha256:...` 或裸 hex；合法对象无法互填。
- **影响**：正式身份、certificate、bundle 无法由现有 V4 对象闭合；调用者只能重写/伪造摘要字符串。
- **根因**：没有唯一 digest type/grammar 和 code-generated validator。
- **修复**：冻结一种 grammar、一个 Digest value object、一个 JCS 实现；全部对象只接受该类型并在边界复算。
- **测试**：Python/Node vectors、Unicode/number/key order/list、每个对象逐跳 round-trip；旧 grammar 全拒绝。
- **依赖**：P1-01；先于所有 trust/certificate/storage 工作。

### P0-04　Source/Fact PASS 可伪造

- **证据**：`compiler_core/source_service_v2.py:406-453`；`compiler_core/fact_admission_v1.py:224-345`。
- **当前/触发**：构造合法格式 hash、authority enum、非空 signature ref，register caller attestation，即可动态得到 source PASS、fact PASS。
- **影响**：未核验来源和事实可成为正式前提，能伪造正式结论。
- **根因**：信任被建模为字符串/角色/bool，服务不解析签名、不查 trust store、不读取真实 artifact bytes。
- **修复**：ArtifactResolver + versioned TrustPolicy；Ed25519/批准机制绑定 issuer/key/scope/time/revocation/content；GateOutcome 由服务内部密封生成。
- **测试**：未知/过期/撤销 key、scope 挪用、重放、bit flip、caller 自报 PASS、伪造 ref 均失败。
- **依赖**：P0-03。

### P0-05　规则可伪激活且没有真实 pack

- **证据**：`compiler_core/rule_platform_cn.py:102-201,202-264`。
- **当前/触发**：caller bool 声明 first-party snapshot，再自造三张 role/receipt 字符串，一条 `CandidateRuleV4` 即可 `active`；candidate 不含可执行 RuleV4 语义，也未生成 pack。
- **影响**：治理状态可冒充正式规则激活；无法证明 active 规则就是 evaluator 执行的规则字节。
- **根因**：审批状态机与签名、RuleV4、pack build/activation identity 断开。
- **修复**：promotion 只消费已验证 source/rule bytes 和多方签名，产出内容寻址 signed pack；runtime 只加载该快照。
- **测试**：同人多角色、receipt 重放、candidate/pack 字节替换、少签、撤销、未生成 RuleV4 均阻断。
- **依赖**：P0-03、P0-04、P0-11。

### P0-06　backend/solver 未实际执行

- **证据**：`compiler_core/backend_router_v1.py:52-124,177-255`。
- **当前/触发**：router 只按 caller 提供的 feature bool 选名；`SolverReceipt` 由 caller 构造，所谓验证只做字段等值，没有 provider invocation。
- **影响**：任意 solver result/receipt 可冒充真实证明，形式化结论不可验证。
- **根因**：路由 DTO 被当执行/证明边界。
- **修复**：受控 provider registry 实际执行，receipt 绑定 provider build、input digest、output/proof bytes、limits、exit/status、签名或本地 attestation。
- **测试**：fake receipt、provider 未调用、输出替换、timeout/cancel、不同 backend receipt 挪用均失败。
- **依赖**：P0-03、P1-05、P1-06。

### P0-07　certificate/audit 可由 caller 组装

- **证据**：`compiler_core/certificate_v1.py:80-174,197-313`。
- **当前/触发**：caller 传全 PASS gate map、TypedReceipt、任意摘要即可动态得到 `issued=True`；无 issuer signature/trust store/run material resolution。
- **影响**：正式证书可伪造；AuditBundleV2 不能独立证明证书、receipt、真实运行的一致性。
- **根因**：certificate issuer 接受已裁决状态，而不是从不可变 run artifact 内部重算。
- **修复**：唯一 issuer 从已验证 bundle snapshot 重算全部 gate；签名绑定 build/pack/request/result/receipts；独立 `verify_run` 不信 evaluate 返回状态。
- **测试**：嵌套状态、receipt、bundle、cert 任一 bit flip/替换/重放都失败；零 caller PASS 参数。
- **依赖**：P0-03～P0-06、P0-11～P0-13。

### P0-08　V3 formal 只靠 advisory 布尔值

- **证据**：`compiler_core/application.py:650-659,719-757`；`docs/architecture/module-authority-v4.json:43-48`。
- **当前/触发**：Application 调 advisory `litigation_engineering.generate_certificate`，只取 `certificate.verifiable`，丢弃证书对象，再报告 `certificate_kind=formal`。
- **影响**：API 的 formal 标志没有可交付、可验、可重放证书材料。
- **根因**：旧展示/策略证书被复用为正式接受条件；authority registry 未约束跨类调用。
- **修复**：删除该正式依赖；ApplicationV4 只消费 P0-07 的 issuer/verifier；模块 authority gate 检查生产调用边。
- **测试**：formal result 必须引用可解析证书；缺证书、advisory receipt 或证书丢弃时强制失败。
- **依赖**：P0-01、P0-07。

### P0-09　MCP fail-open 且无验证闭环

- **证据**：`addons/workbuddy_mcp.py:21-26,218-228,341-351,473-483`；`compiler_core/application.py:338-352`。
- **当前/触发**：admission blocked 被包装为 `status=ok`；engine error 为 `status=engine_error`；stdio 仅 literal `status=error` 设置 `isError=true`。没有 `verify_run/read_artifact`，run URI 只生成不解析。
- **影响**：DSH/任意 MCP client 可把未走 formal kernel 或内核失败当成功；响应自身无法证明正式结论。
- **根因**：协议执行状态、法律状态、formal eligibility 混用；WorkBuddy advisory 面被当未来 formal 面。
- **修复**：formal/advisory 独立 profile/进程；formal 只暴露 capabilities/evaluate/verify_run/read_artifact；仅 verified certificate 可交付。
- **测试**：枚举全状态；除 accepted formal + verified certificate 外，DSH formal delivery 全阻断；篡改 `isError`/status/cert/bundle 必失败。
- **依赖**：P0-01、P0-07。

### P0-10　MCP 任意路径读取

- **证据**：`addons/workbuddy_mcp.py:55-60,124-133,208-216,257-265,459-470`；`compiler_core/analysis.py:175-210`。
- **当前/触发**：传绝对路径、`..`、UNC、device/named pipe、超大文件给 `input_path/index_path`，代码直接 `Path.read_text()`。
- **影响**：本机材料泄露、UNC 外连认证 `[中等] (50-80%)`、pipe/device 挂起、OOM；提示注入可操控 DSH 工具参数。
- **根因**：OS path 被当公开 wire contract，无 root、no-follow、file type、size/depth 限制。
- **修复**：formal MCP 禁止路径，只收有界 V4 inline envelope 或服务签发 opaque artifact ref；advisory 本地模式另设固定根和 reparse 检查。
- **测试**：绝对/相对逃逸、UNC、`\\?\`、`\\.\pipe`、junction/symlink、超限/稀疏文件均在读取前拒绝。
- **依赖**：P0-09、P1-15。

### P0-11　pack TOCTOU

- **证据**：`compiler_core/rule_packs.py:200-226,242-268`；`compiler_core/audit_bundle.py:121-142,239-249`。
- **当前/触发**：verify 后重新打开 manifest/rule/source；攻击者在 verify/load/cache 窗口替换内容或链接，再恢复。
- **影响**：result 按字节 B 求值，却声称 pack digest A；正式结论和 replay identity 被破坏。
- **根因**：hash、parse、cache、execute 不基于同一不可变 snapshot。
- **修复**：no-follow 句柄读取同一 bytes；内容寻址 staging 完整复验后原子发布，只从只读 snapshot 求值；跨进程 pack lock。
- **测试**：每个文件 verify/load 间替换、symlink swap、恢复后 cache 场景均零 run/零证书。
- **依赖**：P0-05、P1-10、P1-11。

### P0-12　旧 bundle digest 与新结果混搭

- **证据**：`compiler_core/audit_bundle.py:121-155,448-459`；`compiler_core/application.py:219-286`。
- **当前/触发**：同 run_id 已有 COMPLETE 时仍先重算新 result/graph/events；writer 返回旧 bundle digest，不比较本次内容；run id 不绑 commit/tree/wheel。
- **影响**：API 返回对象不受其声称的 bundle digest 证明；同版本不同 build 可碰撞。
- **根因**：幂等复用只复用 digest；没有 build-complete RunIdentity 和 per-run transaction。
- **修复**：RunIdentityV4 绑定 commit/tree/wheel/config/backend；持锁；已有 COMPLETE 只返回磁盘验证对象，差异报 `RUN_ID_COLLISION`。
- **测试**：固定 run_id 注入不同 result/build，多进程并发；禁止任何新对象+旧 digest 组合。
- **依赖**：P0-03、P1-10。

### P0-13　state 子树 reparse 逃逸

- **证据**：`compiler_core/audit_bundle.py:78-108,139-145,224-249,580-598`；`compiler_core/rendering.py:159-217`；`compiler_core/analysis.py:284-289`。
- **当前/触发**：合法 root 下预置/交换 runs、packs、renders、analysis symlink/junction，写入跟随到仓库/共享/网络目录。
- **影响**：结构事实、pack cache、回放材料被泄露或污染；绕过“不写仓库”。
- **根因**：只检查逻辑 root，不验证每级目录和最终 parent identity。
- **修复**：目录句柄 no-follow 创建；Windows 拒 reparse point；replace 前复核 parent file-id/containment；生产根验证 owner/DACL。
- **测试**：POSIX symlink、Windows junction、检查后交换、四类子树，必须在首个文件写入前失败。
- **依赖**：P1-11、P1-12、P1-13。

### P0-14　wheel 混合权限面

- **证据**：`pyproject.toml:39-46`；`tools/wheel_gate.py:19-84`；动态 wheel RECORD。
- **当前/触发**：安装官方 wheel 即获得 90 core、9 addons、11 pipeline、38 configs、V3/V4/compat、WorkBuddy、实验 LLM 和 candidate assets。
- **影响**：formal deployment 同时暴露 advisory/legacy/network/规则工程旁路；不能证明“正式结论只能经 JC V4”。
- **根因**：setuptools 广泛 include，gate 用 13 项 blacklist 而非 exact allowlist。
- **修复**：V4 formal wheel exact allowlist；advisory/rule-engineering/corpora 独立 distribution/进程；installed import-negative gate。
- **测试**：RECORD byte-exact allowlist；混入任一 V3/W1b/addons/pipeline/candidate 即失败；旧 import 必须失败。
- **依赖**：P0-01、P1-19。

### P0-15　错误发布路径

- **证据**：`compiler_core/version.py:3`；`CHANGELOG.md:3`；`.github/workflows/auto-release.yml:35-75`；远端 release 元数据。
- **当前/触发**：任意 `v*` tag 可建 release，不核 tag=package version/commit，不构建或附 wheel/SBOM/provenance；源码仍 3.0.2，CHANGELOG 仍 Unreleased，而 tag/release 已存在。
- **影响**：错误 commit、错版本或零产物 release 可被公开，符合 P0“错误发布”。远端 v3.0.2 实际 assets=[]。
- **根因**：release 是 GitHub 元数据动作，不是已验构建物 promotion。
- **修复**：tag/version/tree lock；只晋级 CI 同一 wheel digest；附 checksum/SBOM/provenance/signature；保护 tag/CODEOWNERS/双人审批。
- **测试**：错 tag、dirty tree、无 wheel、digest 不同、未签 provenance 必须拒绝；下载 release 资产重验。
- **依赖**：P0-14、P1-20。

### P1-01　JCS 非 RFC 8785

- **证据**：`compiler_core/jcs.py:36-126`；动态 Python/Node 24 对照。
- **当前/触发**：newline、`1e21`、超 IEEE safe integer 产生不同 canonical bytes。
- **影响**：跨语言 DSH/签名服务/审计 verifier 对同一 JSON 得到不同身份。
- **根因**：自实现数字/escape 规则，没有严格 ECMAScript serialization 和 I-JSON 数值域。
- **修复**：采用经验证 RFC 8785 实现或锁定等价规范；拒绝非安全整数/非有限数。
- **测试**：RFC 官方 vectors + Python/Node/Rust 三方 corpus/property test。
- **依赖**：P0-03。

### P1-02　V4 codec/schema 接受集分裂

- **证据**：`compiler_core/contracts_v4.py:130-137,255-265,310-344,411-418`；`schemas/jc-v4.schema.json:11-14,140-150`；`tests/unit/test_contracts_v4.py:147-152`。
- **当前/触发**：字符串被拆 tuple、list 内 float 漏检、开放 object、Schema/Python date 差异、engine 3 被接受。
- **影响**：同一 wire payload 在 CLI/Python/DSH 产生不同接受/身份；未知字段可进入正式对象。
- **根因**：手写模型、schema、validator，多 authority。
- **修复**：封闭 V4 dataclasses/typed unions 为唯一源，确定性生成 Schema/MCP/capabilities；engine major 仅 4。
- **测试**：逐字段正负 round-trip 和 differential fuzz；任一 schema mutation 启动失败。
- **依赖**：P0-01、P0-03。

### P1-03　时间字符串比较反转

- **证据**：`compiler_core/source_service_v2.py:434-453`；`compiler_core/fact_admission_v1.py:283-288`；`compiler_core/legal_spec_ivl.py:328-356`。
- **当前/触发**：effective `.1Z` 与 decision `Z`、expiry `Z` 与 now `.1Z` 直接字典序比较，动态均返回 PASS。
- **影响**：未生效法源或已过期事实可进入正式运行。
- **根因**：校验 RFC3339 格式后未解析为统一 UTC instant。
- **修复**：严格 parser → UTC epoch/nanoseconds；明确闭开区间与 precision policy。
- **测试**：offset、fractional precision、闰秒 policy、边界前后 1 tick property tests。
- **依赖**：P0-04、P1-02。

### P1-04　断开的 SourcePath 可 PASS

- **证据**：`compiler_core/source_service_v2.py:326-382,455-475`。
- **当前/触发**：A→B 与 C→D 两个分量，最后一条 edge 的 D 绑定合法 snapshot，`integrity_outcome` 和 `path_gate` 均 PASS。
- **影响**：证据/法源路径可漏掉中间链却被标完整。
- **根因**：只查 endpoint existence/hash/cycle；terminal 由 edge 顺序决定，无唯一 root/terminal/连通性。
- **修复**：声明 path endpoints；强制单根、单终点、全节点可达、edge 顺序无关。
- **测试**：断图、多根、多终点、孤点、edge permutation、重复边。
- **依赖**：P0-04。

### P1-05　IR 静默丢语义

- **证据**：`compiler_core/legal_spec_ivl.py:68-107,228-308,328-380`。
- **当前/触发**：RuleV4 `authority_rank` 不进 LegalSpec；terms/interpretation/source_locator 不进 IVL；两跳仍 `PASS/lost_fields=[]`，direct oracle 与 IVL 共享同一简化算法而 `aligned`。
- **影响**：法源效力、解释选择、定位等丢失后仍可被误判正式等价。
- **根因**：mapping table 不做 source-target 字段完备证明，oracle 不独立。
- **修复**：版本化语义字段闭包；每字段 preserve/lower/loss obligation；独立 reference evaluator/证明器。
- **测试**：逐字段 mutation；删除/改 authority/source/interpretation 必须被 receipt/checker 检出。
- **依赖**：P0-06、P0-07。

### P1-06　argumentation/priority 错误

- **证据**：`compiler_core/argumentation_v2.py:134-147,257-362`。
- **当前/触发**：self/mutual attack 标签 UNDEC 但 state accepted；priority edge 不参与 defeat；permission DISPUTED 分支构造不可达；fast path 同 claim 的多个 witness 被 dict comprehension 覆盖。
- **影响**：冲突、优先级、许可和证明 witness 可能给出错误/不完整正式结果。
- **根因**：图状态、label、priority、projection 分散实现，mutation coverage 缺失。
- **修复**：冻结 LMM 语义；统一 grounded/defeat/state projection；priority 进入 defeat；list aggregation 保留 witness。
- **测试**：self/mutual/cycle/priority reversal/permission conflict/duplicate claim mutation suite；快慢路等价。
- **依赖**：P1-05。

### P1-07　namespace/domain patch 不生效

- **证据**：`compiler_core/evaluator.py:98-100,679-699`；`compiler_core/evaluator.py:217-234`；`compiler_core/application.py:555-562`。
- **当前/触发**：loader 丢 YAML namespace，LegalRule 无 namespace，Application 不传 domain_id；transformer 把加载规则当 general。
- **影响**：预期的领域自动 patch/规则选择与实际求值不一致。
- **根因**：配置字段在 load model/application 边界丢失。
- **修复**：正式规则全部来自 signed pack typed RuleV4；禁止运行时 advisory patch；domain/config digest 绑定 identity。
- **测试**：不同 namespace/domain 正负向 E2E；字段丢失必须加载失败。
- **依赖**：P0-05、P1-16。

### P1-08　pack/build attestation 弱校验

- **证据**：`compiler_core/rule_packs.py:310-470`，尤其 `430-436`。
- **当前/触发**：build attestation 只查 64 hex；build_commit 只必填不绑 HEAD/tree；`blocker_codes` 在追加 EMPTY_OFFICIAL_PACK 前计算。
- **影响**：空 official 动态得到 `integrity_valid=true`；伪 build 字符串不能证明来源构建。
- **根因**：manifest 形状校验代替签名和 build provenance 验证；issue 计算顺序错误。
- **修复**：签名 attestation 绑定 source tree/generator/config/output；所有 blocker 最后统一裁决；空 official 必 fail。
- **测试**：空包、错 commit、未签/错签 provenance、issue 顺序 mutation。
- **依赖**：P0-05、P0-11、P0-15。

### P1-09　CLI 错标 candidate 为 eligible

- **证据**：`compiler_core/cli.py:245-250`；五个 pack manifests 的 `reasoning_eligible_total: 0`。
- **当前/触发**：legacy rule 只要有 `source_anchor`，lookup 输出就写 `reasoning_eligible`。
- **影响**：操作员/下游可误把 candidate 资产当正式规则。
- **根因**：lookup 临时推断覆盖 pack authority。
- **修复**：状态只来自 verified pack snapshot；candidate 查询字段明确 `candidate_only`。
- **测试**：manifest 0 eligible 时任一 lookup 不得出现 eligible；跨入口一致。
- **依赖**：P0-02、P0-05。

### P1-10　并发和崩溃恢复缺失

- **证据**：`compiler_core/audit_bundle.py:224-249,448-462`；`tests/unit/test_audit_bundle.py:215-231`。
- **当前/触发**：同 pack/run 并发；kill/断电/磁盘满留下固定 `.tmp` 或 incomplete final dir。
- **影响**：合法并发失败；一次崩溃后相同身份永久不可重试，需人工删审计状态。
- **根因**：把“发现残留即拒绝”当锁/恢复；final dir 兼作 staging。
- **修复**：跨进程锁、随机 staging、owner/pid/lease、可验证隔离/恢复、完整目录原子发布。
- **测试**：2/10/100 processes、每写点 kill、同 run 幂等、不同 build collision。
- **依赖**：P0-12、P1-11。

### P1-11　持久性不完整

- **证据**：`compiler_core/audit_bundle.py:239-249,562-577`；`compiler_core/analysis.py:312-325`；`compiler_core/rendering.py:441-454`；`compiler_core/rule_governance.py:164-178`。
- **当前/触发**：file fsync/replace 后掉电；pack `copy2`、staging dir、parent dir 未 flush。
- **影响**：进程已返回成功但 COMPLETE/目录项/pack bytes 丢失，不能 replay。
- **根因**：原子可见性被当持久性；无跨平台 storage abstraction。
- **修复**：POSIX file+dir fsync；Windows FlushFileBuffers/write-through/ReplaceFile 语义；不支持 FS fail closed。
- **测试**：每 fsync/rename 点故障注入，重启后 only-complete-or-absent；NTFS/ext4 矩阵。
- **依赖**：P1-10、P0-13。

### P1-12　Windows DACL fail-open

- **证据**：`compiler_core/audit_bundle.py:78-108,580-585`；`compiler_core/cli.py:313-317`。
- **当前/触发**：state root 继承 Everyone/Users 读写；diagnostic 保持 `acl_verified=false,dangerous_permissions=false`，doctor 忽略 acl_verified。
- **影响**：其他本机主体可读/改结构事实和审计材料；泄露后 checksum 无法补救。
- **根因**：只实现 POSIX chmod，Windows 未实现 owner/DACL/reparse 验证。
- **修复**：owner-only + SYSTEM DACL；检查继承/allow/deny/owner；无法验证即 production fail closed。
- **测试**：Everyone read/write、继承 ACE、owner change、正常轮换；doctor/evaluate 状态一致。
- **依赖**：P0-13。

### P1-13　V3/V4 state 无隔离

- **证据**：`compiler_core/audit_bundle.py:21,68-75,139-145`；`compiler_core/certificate_v1.py:16-18,197-247`。
- **当前/触发**：若直接接 V4，默认仍用 `.../juris-calculus/runs|packs` 和 bundle schema 1.0。
- **影响**：V3/V4 cache、run、digest grammar 混存；V4 无独立 writer/replay，无法执行零兼容策略。
- **根因**：先写 V4 dataclass，未设计 generation-scoped storage。
- **修复**：独立 V4 namespace/storage codec；V4 不发现/迁移 V3；V3 只在冻结环境。
- **测试**：同机 V3/V4 fixtures 双向拒绝；默认路径、retention、backup/replay。
- **依赖**：P0-07、P0-12、P1-10。

### P1-14　MCP manifest/codec 多真源

- **证据**：`addons/workbuddy_mcp.py:40-151,331-347,408-456`；根 `mcp_manifest.json`。
- **当前/触发**：`--manifest` 只浅验工具名/Schema 存在；tools/list 广播自定义 manifest，但入参始终按 DEFAULT；输出不按 outputSchema 验证。
- **影响**：DSH codegen/模型看到的合同与真实 parser/result 分裂。
- **根因**：manifest 可覆写但 parser 不是由同一 authority 生成。
- **修复**：V4 contract 单源生成 schema/manifest/codec；production 禁任意 manifest；启动校验 byte/hash equality。
- **测试**：任一 schema mutation 启动失败；各工具正负 parser/output round-trip。
- **依赖**：P1-02、P0-09。

### P1-15　MCP/JSON/状态无资源预算

- **证据**：`addons/workbuddy_mcp.py:291-355,459-470`；`compiler_core/analysis.py:121-210`；`compiler_core/audit_bundle.py:537-549,631-640`；`compiler_core/contracts.py:18-23,143-156,910-950`。
- **当前/触发**：超长无换行 RPC、深嵌 JSON、巨大 index/events、慢磁盘/solver、stdout 停读、连续唯一 run。
- **影响**：单客户端可 OOM/CPU/磁盘耗尽或阻塞全 MCP；无法取消；残留再触发 P1-10。
- **根因**：只有少量业务项数限制，无传输/解析/执行/存储预算。
- **修复**：byte/depth/object/array/string caps；deadline/cancel；隔离 worker+有界队列；quota/retention/backpressure。
- **测试**：line/depth bomb、巨大 arrays/index、cancel、slow+ping、stdout backpressure、quota/disk-full。
- **依赖**：P0-10、P1-10。

### P1-16　domain config 异常被吞

- **证据**：`compiler_core/domain_config.py:52-65`；`compiler_core/application.py:228-247,555-562`；仓库只有 `domain_config.example.yaml`。
- **当前/触发**：配置缺失/损坏/权限失败被 `except Exception: pass` 吞掉，继续使用可变全局默认。
- **影响**：正式语义配置错误时无声继续，不同线程/run 可串配置。
- **根因**：legacy convenience fallback 进入 formal application；配置不来自 verified pack snapshot。
- **修复**：DomainConfig 是 signed pack 的 immutable bytes；缺失/解析失败 BLOCKED；digest 绑定 run。
- **测试**：missing/corrupt/permission/unknown fields、并发不同 configs、replay 缺 config 全 fail closed。
- **依赖**：P0-05、P1-07。

### P1-17　路径隐私泄露

- **证据**：`compiler_core/audit_bundle.py:601-613`；`compiler_core/audit.py:756-768`；`compiler_core/cli.py:266-291`。
- **当前/触发**：事实/ref 含 UNC、device、`file://`、遗漏 POSIX 根；或调用 capabilities。
- **影响**：bundle/stdout 暴露客户/主机路径；安装后 capabilities 实际输出 site-packages 绝对路径。
- **根因**：跨平台 path 用正则黑名单；逻辑资源与物理路径混用。
- **修复**：V4 ref 使用封闭 URI/ID grammar；公共输出只发逻辑资源名；递归拒绝所有 absolute/UNC/device/file URI。
- **测试**：Windows/POSIX/UNC/device/extended URI matrix，递归覆盖全部字段。
- **依赖**：P0-10、P0-13。

### P1-18　存储错误被误分类

- **证据**：`addons/workbuddy_mcp.py:203-204,486-493`。
- **当前/触发**：EACCES、ENOSPC、I/O error 在 path read/evaluate 时被笼统捕获为 `INVALID_TOOL_INPUT,retryable=false`。
- **影响**：运维无法区分用户错误和基础设施故障；DSH 不会正确重试/熔断。
- **根因**：异常类到稳定协议错误没有显式映射。
- **修复**：按 parse/path/security/storage/engine 分类；storage failure `isError=true`，不得产生 COMPLETE。
- **测试**：权限、磁盘满、只读 FS、断连、坏 JSON 的 code/retryability/status 矩阵。
- **依赖**：P0-09、P1-15。

### P1-19　wheel gate 不能证明 formal-only

- **证据**：`tools/wheel_gate.py:19-84`；动态 gate PASS 与 157-entry RECORD。
- **当前/触发**：混入 compat、V3 schema、WorkBuddy、pipeline、实验 LLM 的 wheel 仍 `status=PASS`。
- **影响**：CI 绿色不能证明生产权限面或 V4 purity。
- **根因**：13 项 blacklist + version/import smoke；无 exact RECORD、旧 import negative、installed formal E2E、双构建。
- **修复**：生成式 exact allowlist；A/B reproducibility；clean install 全状态 E2E；forbidden import/content/license scan。
- **测试**：逐项注入 V3/W1b/addons/pipeline/candidate/advisory，gate 必杀 mutation。
- **依赖**：P0-14。

### P1-20　依赖和发布证据未锁闭

- **证据**：`requirements/core.lock:1-6`；`requirements/dev.lock:1-6`；`requirements/render.lock`、`pipeline.lock`、`documents.lock`；`.github/workflows/ci.yml:34-53`。
- **当前/触发**：只有 core/PyYAML 带 hashes；dev/optional 仅直接 pin，无 transitive hashes；CI pip-audit/SBOM 只扫 core。
- **影响**：测试/构建/可选生产面的传递依赖可漂移，SBOM 不是发布 wheel 完整闭包。
- **根因**：按 profile 手写 direct locks，没有 resolved multi-platform lock 和 artifact promotion。
- **修复**：生成、评审、hash-lock 每个发行 profile 的完整 transitive graph；SBOM/provenance 绑定 wheel 并签名随 release 发布。
- **测试**：offline/hash install、依赖替换、license deny、SBOM 与 RECORD/dependency graph 对账。
- **依赖**：P0-14、P0-15。

## 11. 既有施工方案逐项核验

方案取自 HEAD blob；工作树中的用户删除状态未被恢复。方案是正确方向的施工目标，不是当前完成证明。

| 波次 | 当前核验 | 证据/未满足门禁 | 结论 |
| --- | --- | --- | --- |
| S0 冻结 V4 合同/清册 | 有完整方案、292 文件清册 | digest、开放 Mapping、签名依赖、limits、平台范围未冻结 | **部分实现** |
| S1 合同/JCS/trust/artifact | 有 staged classes/tests | digest 不可组合、JCS 不合规、engine 接受 3、trust 可伪造 | **部分实现但门禁失败** |
| S2 source/fact/signed pack | 有 source/fact/rule-platform 数据类 | 全部无 production consumer；签名/ref 不解析；path/time 错误 | **部分实现但门禁失败** |
| S3 RuleV4/双 IR/argumentation/backend | 有孤立 compiler/graph/router | IR 静默丢字段、argumentation 错、provider 未执行 | **部分实现但门禁失败** |
| S4 ApplicationV4/cert/bundle/storage | 仅 certificate/AuditBundleV2 数据类 | 无 ApplicationV4、writer/replay；caller 可发证；并发/DACL/TOCTOU 未解 | **未形成纵向实现** |
| S5 三入口原子切换/删除旧 authority | 三入口全是 V3 | V3/W1b/compat 源码、schema、tests、docs、wheel 均存在 | **未实现** |
| S6 wheel/CI/release/current docs | CI/锁/双构建有部分正向控制 | mixed wheel gate PASS；全集失败；release 无资产；current docs 冲突 | **部分实现但门禁失败** |
| S7 V4 Kernel RC | 无 V4-only installed E2E/RC artifact | P0/P1 未关闭 | **未开始** |
| S8 真实 `cn-official`/4.0.0 | 目录/空 manifest 存在 | 0 rule、blocked、无 attestation | **未开始；禁止现在编规则** |
| S9 DSH formal profile/plugin | JC/DSH 两仓无集成代码 | JC MCP 不具备 formal contract；DSH 尚未 pin deployment | **未开始** |

方案需修订的点：

1. 明确 RFC 8785 实现/数值域的库与跨语言 verifier，不只写“统一 digest”。
2. `SourcePath` 加单根、单终点、全连通、edge-order-independent 不变量。
3. 时间统一解析为 UTC instant，禁止字符串比较。
4. S4 前加入 provider invocation receipt 与 independent checker 非同源证明。
5. storage 门禁加 Windows DACL/reparse、parent fsync、lease recovery、old COMPLETE collision。
6. formal MCP 只用 tools；DSH 当前 MCP bridge 不消费 Resources/Prompts，`read_artifact` 必须是受控 tool。
7. DSH formal profile 同时需要 delivery guard，不能只靠 skill/prompt 约束“必须调用 JC”。
8. CI 增加 Windows 3.11，或明确产品只支持 Windows 3.12；当前 README/CI/lock 范围要单一。

## 12. 测试与 CI 盲区

### 12.1 现有正向控制

- CI 三矩阵：Ubuntu 3.11/3.12、Windows 3.12；Actions 固定 commit。
- companion spec 固定 commit `a3a015941f75091c87d57aa956e712f1546dd7d4`。
- `core.lock` 使用 hashes；pip-audit、SBOM、build provenance 有 CI step。
- 单文件 atomic temp+fsync+replace、COMPLETE-last、run_id traversal 阻断已有测试。
- 双独立构建在本轮固定 epoch 下逐字节一致。

### 12.2 不能由绿色测试推出的事实

- 远端绿色只对应 `6f4f91a...`，本地 `bfd90f9...` 未有远端 CI。
- 505 个通过用例未触达 ApplicationV4，因为它不存在。
- `test_contracts_v4.py` 明确要求 engine 3.0.2 可接受；compat test 保护了需删除的旧行为。
- application formal success 直接构造 trusted object；source/fact/rule/cert tests 直接构造 caller PASS/receipt。
- MCP focused 8 passed 固化了 4-tool WorkBuddy 协议；helper 不验证 `isError` 的错误分支。
- 无 multi-process/junction/DACL/TOCTOU/power-loss/ENOSPC/size-depth/cancel/backpressure/state-quota tests。
- 无 installed-wheel V4 formal successful vertical slice；现有 wheel gate 只 import smoke。
- 三个整文件 skip 让中文规则、对抗、tri-rail collision 不进入 required gate。

### 12.3 必须新增的 test suites

| Suite | 必须证明 |
| --- | --- |
| `tests/contract_v4` | Python/Schema/MCP/codegen 同一接受集；旧 payload 全拒绝 |
| `tests/trust_security` | key/scope/time/revocation/replay/bit-flip/caller PASS 全阻断 |
| `tests/formal_e2e` | synthetic signed pack 下三入口全状态 + cert + verify + replay |
| `tests/semantic_mutation` | IR 每字段、priority/permission/attack、oracle independence |
| `tests/storage_chaos` | multi-process、kill points、disk-full、fsync、collision/recovery |
| `tests/windows_security` | DACL、owner、junction/reparse、long/device/UNC paths |
| `tests/mcp_protocol` | isError/status/outputSchema、caps、timeout/cancel/backpressure |
| `tests/packaging` | exact RECORD、旧 import negative、双 build、release download verify |
| `tests/dsh_formal` | bypass attempts、tool hiding、verified cert delivery guard |

## 13. 生产 wheel 精确内容审计

### 13.1 实际产物

- 文件：`juris_calculus-3.0.2-py3-none-any.whl`
- 大小：2,656,407 bytes
- SHA-256：`20cdecc1c07e843c79fdd45faea790746d3f9b31b41df47db1c3bf77d5de7ddf`
- A/B 双构建：相同 commit、Python 3.12.5、build 1.5.0、setuptools 83.0.0、wheel 0.47.0、固定 `SOURCE_DATE_EPOCH=1787112437`；二进制相同。
- RECORD：存在；157 entries。

| Prefix | entries | 生产判断 |
| --- | ---: | --- |
| `compiler_core/` | 90 | V3、V4、compat、advisory/实验全部混装 |
| `addons/` | 9 | WorkBuddy + CN/HK/US adapter 混装 |
| `pipeline/` | 11 | rule engineering、外部 LLM、实验模块混装 |
| `configs/` | 38 | legacy/candidate corpora、domain example、tri-rail report 混装 |
| `schemas/` | 3 | `jc-v3` 与 `jc-v4` 同时发布 |
| `.dist-info/` | 6 | metadata/license/RECORD |

现 gate 输出：`status=PASS, forbidden_module_count=0, workbuddy_tools=4, resources=0`。这与 formal-only 目标相反，说明 gate 证明的是“短 blacklist 没命中”，不是“wheel 只有 V4 formal core”。

### 13.2 干净安装结果

- `compiler_core.__file__` 指向隔离 venv site-packages，排除了源码目录误导。
- 版本 3.0.2；`compiler_core.CaseRequest` 来自 `compiler_core.contracts`；包根没有 `CaseRequestV4` export。
- `jc capabilities --json` exit 0，却主动输出绝对 `data_root`，并声称 `formal_reasoning`。
- `jc doctor` exit 3：`cn_official.present=true, reasoning_ready=false`；schema 指向 V3；Windows `acl_verified=false`。
- `jc packs verify cn-official` exit 3：0 rules、`EMPTY_OFFICIAL_PACK`、`MISSING_BUILD_ATTESTATION`、但 `integrity_valid=true`。
- `jc evaluate` exit 3：`PACK_NOT_REASONING_READY`。
- installed MCP smoke exit 0，但 `readiness_claimed=false`、4 tools、0 resources、version 3.0.2。

## 14. `cn-official` 开工前阻断项

现在不应编写正式 `cn-official`。先完成以下全部系统门禁：

1. P0-01～P0-14、P1-01～P1-19 全部关闭，形成 V4 Kernel RC。
2. 唯一 JCS/digest/identity grammar 可跨语言验证。
3. ArtifactResolver、TrustPolicy、key custody、role/scope/revocation/rotation 固化。
4. Source/Fact/Rule/Pack 全链只从真实 bytes + signature 生成，不接 caller PASS。
5. RuleV4/IR/argumentation/backend/checker 的语义 mutation 门禁通过。
6. CertificateV4/AuditBundleV4 独立 verify/replay，storage chaos/DACL 门禁通过。
7. 三入口/installed wheel 完整纵向 E2E；production wheel exact allowlist。
8. 先用 synthetic signed official test pack 证明系统可产出；不得用真实规则补偿系统空链。
9. 指定首个完整中国法领域、第一方法源清单、法源版本/效力/定位方法、双人法律审批与撤销流程。
10. 每条正式规则可回到 source snapshot/locator/approval receipt；候选材料可入库但绝不进入 formal numerator。
11. 真实 pack 与 engine 独立签名/发布/回滚，不把规则包烘焙进 engine wheel。
12. 完成全部领域正向、冲突、例外、失效、缺事实、争议事实、撤销/回滚 E2E 后，才可发布 4.0.0。

## 15. DSH 接入前置阻断及不可绕过边界

### 15.1 当前 DSH 事实

- 官方 master/HEAD：`99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`，tag/release `dsh-v0.1.0-rc.7`，MIT，Node `^22.19.0 || >=24.0.0`，pnpm 11.7.0。
- 官方 README 明示 developer preview 和 compatibility-breaking changes：[README@99f6f02](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/README.md#L5-L12)。
- DSH 是“everything is a plugin”；新行为挂 documented extension point，不改 agent loop：[architecture](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/docs/architecture.md#profiles-and-bundles)。
- out-of-tree bundle 可通过 profile 安装：[bundle README](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/bundle/README.md)。
- MCP client 原生桥接外部 stdio/HTTP tools，并把 `isError` 当失败；Resources/Prompts 暂无 consumer：[MCP client README](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/mcp/mcp-client/README.md)。
- 项目 skills 可放 `.dsh/skills` 或 `.agents/skills`：[skills](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/docs/subsystems/skills.md#local-discovery-priority)。
- DSH sandbox 只治理文件 effect；Windows ACL 为 partial，network/process 不在其 vocabulary：[sandbox](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/docs/subsystems/sandbox.md#modes-and-enforcement)。
- 在该 DSH HEAD 全仓搜索无 `juris-calculus`/`cn-official`/formal legal 集成。

### 15.2 正确接法

```text
通用 web/headless profile
└─ 保持 DSH 即插即用，不加载 JC formal guard

jc-formal profile（pin DSH commit/release）
├─ out-of-tree JC formal bundle/plugin
├─ @deepseek-ai/dsh-mcp-client（failOnStartupError=true）
│  └─ 独立 JC V4 formal MCP process
│     ├─ capabilities
│     ├─ evaluate
│     ├─ verify_run
│     └─ read_artifact
├─ project skill：何时需要 formal，不承担安全强制
└─ delivery guard plugin：没有 verify_run 成功的 certificate，不得输出 formal 标志/正式法律结论
```

不改 `agent-loop`，不把 JC 语义复制进 DSH，不让通用 profile 强制走 JC。由于 DSH MCP 当前只桥接 tools，JC 的 verify/read 必须是 tools；不依赖 MCP Resources。

### 15.3 formal profile 必杀边界测试

1. 不调用 JC、调用 advisory tool、伪造 tool 文本、模型自称“已验证”均不能产生 formal delivery。
2. `evaluate` blocked/error、MCP `isError` 被删除/翻转、status 嵌套篡改，delivery guard 必阻断。
3. certificate/bundle/receipt/run identity 任一替换，`verify_run` 必失败。
4. MCP server 不可达、重连 exhausted、startup 工具同步失败，formal profile fail closed；通用 profile 仍可用。
5. DSH 其他 filesystem/bash/web/MCP tools 不能写入 JC state、注入 trusted artifact 或发布 formal marker。
6. JC MCP 不接受本地 path；DSH sandbox 即使 partial 也不改变 JC 自身安全结论。
7. 同一 session 内先 advisory 后 formal，污染内容不能成为 formal premise；formal result 只引用 JC admission receipts。
8. pin 升级 DSH 时重跑 tool naming、outputSchema、isError、timeout/cancel、session persistence compatibility tests。

### 15.4 开始条件

S8 完成、JC 4.0.0 wheel + signed `cn-official` 可独立 verify/replay、P0/P1 清零后才开始 DSH 化。当前 JC MCP 的 V3/WorkBuddy/任意 path/fail-open 行为是硬阻断，不能先包装成 DSH plugin 再补内核。

## 16. 删除、改造、保留、隔离清单

| 处置 | 文件/模块 | 理由 |
| --- | --- | --- |
| 删除 current runtime | `compiler_core/contracts.py`、`application.py` 的 V3 实现、`legal_ir_v3.py`、`compat_v3_v4.py`、旧 evaluator/adapter compatibility | V4-only 无运行时兼容 |
| 删除 current schema | `schemas/jc-v3.schema.json`、`schemas/w1b/**` | 唯一生成式 V4 schema |
| 删除/改写 tests | `test_v3*`、`test_w1b*`、compat/engine3 acceptance；trusted direct-construction success | 正确语义改为 V4 external E2E，旧行为不保留 |
| 退出 formal wheel | `addons/**`、`pipeline/**`、legacy pack manifests/corpora、rule-engineering tools | 降低权限面；资产可独立 distribution，不得丢弃未核验材料 |
| 退出 formal wheel | authority registry 的 40 advisory modules | advisory 独立包/进程；不得为 certificate 提供 receipt |
| V4 重写 | contracts/JCS/source/fact/rule/IR/argumentation/backend/application/certificate/audit/replay/MCP/storage | 形成唯一纵向链，不能在 V3 上打补丁 |
| 保留并加强 | pinned Actions、`core.lock` hash、supply-chain/provenance 工具、有效语义 fixtures | 正向控制有效，但需扩到完整 wheel/release |
| 历史隔离 | `v3.0.2` tag + 对应 wheel/lock/spec commit + 独立 state/env | 只用于历史重放；不进入 current source/wheel/docs authority |
| 文档重写 | README、CHANGELOG、HANDOFF、baseline、memory、CLI/WorkBuddy/Migration guides、两个 registry | 只保留一套 current V4 合同；历史随 tag/archive |

附录 A 给出每个 tracked 文件的主类；具体迁移不能按目录粗删：candidate/经验/法源材料先外迁并保持 provenance，formal wheel 再删除消费入口。

## 17. 按依赖顺序的修复波次

| 波次 | 完整交付 | 退出门禁 |
| --- | --- | --- |
| W0/S0 | 冻结 V4 object set、Digest、JCS、limits、平台、模块/文件处置、签名依赖 | 无开放 Mapping；codegen golden；292 文件 disposition 完整 |
| W1/S1 | contract/codegen、ArtifactResolver、TrustPolicy、signature/key lifecycle | Python/Schema/MCP 同集；RFC vectors；伪造/撤销/路径攻击全拒 |
| W2/S2 | Source/Fact/RuleV4/signed pack snapshot | caller PASS 不可构造；时间/路径/TOCTOU/pack identity 全门禁 |
| W3/S3 | loss-accounted 双 IR、argumentation、真实 backend invocation、independent checker | semantic mutations 全杀；receipt 只由真实调用生成 |
| W4/S4 | ApplicationV4、状态机、CertificateV4、AuditBundleV4、verify/replay、storage | synthetic signed pack 全状态 E2E；并发/崩溃/DACL/durability 全过 |
| W5/S5 | 包根、CLI、Client、formal MCP 原子切换；删除 V3/W1b/compat authority | 单一 production sink；三入口同构；旧 import/payload 必失败 |
| W6/S6 | exact wheel、全锁、CI、SBOM/provenance/signing/release、current docs | 双构建；installed E2E；exact RECORD；下载 release 资产复验 |
| W7/S7 | V4 Kernel RC 生产演练 | P0/P1=0；容量/SLO/rollback/backup/retention/incident drill |
| W8/S8 | 真实 `cn-official` 完整领域与 4.0.0 | 法源/规则/审批/签名/撤销/全状态 E2E；独立 pack release |
| W9/S9 | pin DSH 的 out-of-tree formal profile/bundle/MCP/skill/delivery guard | bypass suite 全过；通用 profile 不受 JC 约束 |

每波次必须闭环，不把“一个 synthetic rule”“一个 MCP tool”“一个 green unit test”称为完成。失败只回退到上一份已签 V4 artifact，不回退当前 runtime 到 V3。

## 18. 最终 Go / No-Go 结论

### 当前结论：No-Go

不是 Conditional Go。原因不是“还缺一点规则”，而是：

1. 当前公共产品仍是 V3，V4 不生产可达。
2. 当前系统无法通过公共入口产生正式结论。
3. V4 digest/trust/backend/certificate/audit 链可不组合或由 caller 伪造。
4. storage/MCP/pack 存在审计真实性和数据边界 P0。
5. production wheel/release 不具备 V4 formal-only 和 artifact promotion 证明。

### V4 Kernel RC 成立条件

- P0/P1 全关闭并有 regression/mutation/chaos tests。
- 三入口只进 ApplicationV4；V3/W1b/compat 从 current source/wheel/public docs 清零。
- synthetic signed official pack 可在 clean installed wheel 产出、verify、replay；任一材料篡改失败。
- exact wheel、双构建、完整 locks/SBOM/provenance/signature/release download verification 通过。
- 生产 storage、Windows DACL、capacity/SLO/backup/rollback 已现场验证。

### 正式中国法生产 Go 成立条件

在 Kernel RC 之后，真实 `cn-official` 完成第 14 节法律/规则工程门禁；二者是独立签名、独立版本、可独立撤销的 artifacts。DSH 不参与这个判断。

## 19. 未验证事项和外部条件

| 未验证 | 原因/所需条件 |
| --- | --- |
| companion spec 五项 differential tests | 本机无 pinned `legal-math-modeling` checkout；需按 CI commit 获取后复跑两 Python 矩阵 |
| Linux/macOS storage/sandbox | 本轮 Windows；需 ext4/Linux、macOS runner 验证 fsync/symlink/permission |
| Windows DACL/junction 动态攻击 | 不在用户生产目录制造权限/重解析攻击；需隔离 VM/测试账户 |
| multi-process/kill/disk-full/power-loss | 当前无安全故障注入 harness；需专用 chaos runner/VM |
| production trust/key custody | 没有生产 key、HSM/trust store/issuer/revocation policy |
| `cn-official` 法律正确性 | 当前 0 rule；需第一方法源、法律审批人、领域范围和版本策略 |
| 容量/SLO | 未提供 latency/throughput/RSS/state quota/retention 指标和真实负载 |
| GitHub governance | API 不能证明 branch/tag protection、admin bypass、CODEOWNERS 双人审批、release signer |
| release signing/下载复验 | 当前 v3.0.2 无 assets；无签名 wheel 可验 |
| DSH live integration | 当前两仓无集成；需 pin deployment、Node/pnpm 环境和 formal profile 后执行 bypass suite |
| UNC 外连认证实际影响 | 未对真实网络目标触发；静态存在任意 UNC read，影响标为 `[中等] (50-80%)` |

## 20. 实际命令、退出码、产物哈希

以下变量只指向仓库外审计临时目录：

```powershell
$AUDIT_TMP = 'D:\Codex\1.法律工作区\juris-calculus工作区\.audit_tmp_20260819'
$REPO = 'D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus'
$PY311 = 'C:\Users\being\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe'
$PY312 = 'C:\Users\being\AppData\Local\Programs\Python\Python312\python.exe'
$BUILD_PY = "$AUDIT_TMP\venv312_build_bfd90f9\Scripts\python.exe"
$INSTALL_PY = "$AUDIT_TMP\venv312_install_bfd90f9\Scripts\python.exe"
$INSTALL_JC = "$AUDIT_TMP\venv312_install_bfd90f9\Scripts\jc.exe"
$env:PYTHONDONTWRITEBYTECODE = '1'
```

| 操作 | 完整主命令 | 退出/结果 |
| --- | --- | --- |
| Git 基线 | `git status --short --branch`; `git rev-parse HEAD`; `git rev-parse 'HEAD^{tree}'`; `git ls-remote --symref <remote> HEAD refs/heads/main` | 0；HEAD/tree/remote 如第 1 节 |
| 全文件 | `git -c core.quotepath=false ls-tree -r --name-only HEAD` + 单值 classifier | 0；292/292；map hash `3b92...` |
| V4 动态反例 | PowerShell here-string 内联 Python，经 `py -3.12 -B -` 执行 contracts/JCS/IR/argumentation/source/fact vectors | 0；输出见第 7～10 节 |
| Node 对照 | `node -e "console.log(JSON.stringify({s:'\n'})); console.log(JSON.stringify({n:1e21})); console.log(JSON.stringify({n:9007199254740993}))"` | 0；Node v24.16.0 |
| 3.12 全集 | `py -3.12 -B -m pytest tests -q -p no:cacheprovider --basetemp "$AUDIT_TMP\pytest312"` | 1；505 pass / 28 skip / 5 fail |
| 3.11 环境 | `uv venv "$AUDIT_TMP\venv311_bfd90f9" --python $PY311`；`uv pip install --python "$AUDIT_TMP\venv311_bfd90f9\Scripts\python.exe" -r requirements\dev.lock`；`uv pip install --python "$AUDIT_TMP\venv311_bfd90f9\Scripts\python.exe" --require-hashes -r requirements\core.lock` | 0 |
| 3.11 全集 | `& "$AUDIT_TMP\venv311_bfd90f9\Scripts\python.exe" -B -m pytest tests -q -p no:cacheprovider --basetemp "$AUDIT_TMP\pytest311"` | 1；505 pass / 28 skip / 5 fail |
| MCP tests | `py -3.12 -B -m pytest tests\unit\test_mcp_stdio_protocol.py tests\unit\test_mcp_manifest_dispatch.py -q -p no:cacheprovider --basetemp "$AUDIT_TMP\pytest_mcp"` | 0；8 passed |
| MCP selftest | `py -3.12 -B mcp_server.py --test` | 0；4 tools / 0 resources / V3.0.2 / readiness false |
| 首次 A/B build | `py -3.12 -B -m build --wheel --no-isolation --outdir dist` | 两次均 1；全局环境缺 exact setuptools 83.0.0/wheel 0.47.0 |
| 隔离 build env | `uv venv "$AUDIT_TMP\venv312_build_bfd90f9" --python $PY312`；随后分别安装 `requirements\dev.lock` 和 `--require-hashes requirements\core.lock` | 0 |
| 独立源码 | `git archive --format=tar HEAD | tar -xf - -C <src-c>`；同样生成 `<src-d>` | 0；各 292 files |
| A/B wheel | `$env:SOURCE_DATE_EPOCH='1787112437'; & $BUILD_PY -B -m build --wheel --no-isolation --outdir dist`，在 c/d 两快照分别执行 | 两次 0；hash 相同 |
| wheel inspect | `Get-FileHash -Algorithm SHA256 <wheel>` + Python `zipfile` RECORD 统计 | 0；2,656,407 bytes；`20cdecc...7ddf`；157 entries |
| archive wheel gate | 在无 `.git` 的 archive 运行 `python -B tools\wheel_gate.py --no-isolation ...` | 1；`CalledProcessError`，依赖 Git checkout |
| clone wheel gate | 外部 local clone 中同命令 | 0；错误地对 mixed wheel 给 PASS |
| clean install | `uv venv <install-venv>`；`uv pip install --require-hashes -r requirements\core.lock`；`uv pip install --no-deps <wheel>` | 0 |
| installed import/capabilities | `& $INSTALL_PY -B -c <imports>`；`& $INSTALL_JC capabilities --json` | 0；public request=V3；capabilities 泄露绝对 data_root |
| installed doctor | `& $INSTALL_JC doctor --audit-out "$AUDIT_TMP\installed_state_bfd90f9" --json` | 3；blocked |
| installed pack | `& $INSTALL_JC packs verify cn-official --json`；`& $INSTALL_JC packs verify --all --json` | 3；0 official rules；21,481 candidate / 0 eligible |
| installed evaluate | V3 JSON 经 stdin：`... | & $INSTALL_JC evaluate --input - --audit-out "$AUDIT_TMP\installed_eval_state_bfd90f9" --json` | 3；`PACK_NOT_REASONING_READY` |
| installed MCP | `& $INSTALL_PY -B -c "from addons.workbuddy_mcp import run_smoke; raise SystemExit(run_smoke())"` | 0；readiness false |
| supply chain | `& $BUILD_PY -B tools\supply_chain_gate.py --requirements requirements\core.lock --output "$AUDIT_TMP\supply_chain_core.json"` | 0；0 known vulnerabilities |
| SBOM | `& $BUILD_PY -B -m pip_audit --requirement requirements\core.lock --format cyclonedx-json --output "$AUDIT_TMP\sbom_core.cdx.json" --progress-spinner off --strict --disable-pip` | 0；457 bytes；SHA-256 `066277d282792b8647a033e4fd0f95f61130189aed93344a59a60249e7da0b3f` |
| provenance | `& $BUILD_PY -B tools\build_provenance.py --wheel "$AUDIT_TMP\src_build_d_bfd90f9\dist\juris_calculus-3.0.2-py3-none-any.whl" --output "$AUDIT_TMP\build_provenance.json"` | 0；commit/spec/wheel hash 已绑定，但未签/未发布 |
| GitHub current | `Invoke-RestMethod` 调官方 repo/actions/releases API；`git ls-remote` JC/DSH | 0；JC/DSH 状态见第 1、15 节 |
| DSH interface | 外部 `git clone --depth 1 https://github.com/deepseek-ai/deepseek-harness.git`; `rg`/读取官方 docs | 0；HEAD `99f6f02...`；JC 集成搜索 exit 1（无命中） |

动态操作后均执行原仓库 `git status --short`；直到写报告前，始终只有两份用户既有 tracked 删除，没有缓存、构建物或源码改动进入仓库。

## 附录 A：292 个 tracked 文件单值分类

格式：`path<TAB>primary-role`。该清单固定于审计 HEAD `bfd90f9...`，不包含本报告本身。

```text
.gitattributes	other-assets
.github/workflows/auto-release.yml	CI/build/release
.github/workflows/ci.yml	CI/build/release
.gitignore	other-assets
20260815_juris-calculus理论成果全量吸收施工方案.md	docs/baseline/memory
20260819_juris-calculus_V4单主链全量切换与生产投产施工方案.md	docs/baseline/memory
AGENTS.md	docs/baseline/memory
CHANGELOG.md	docs/baseline/memory
CLAUDE.md	docs/baseline/memory
HANDOFF.md	docs/baseline/memory
LICENSE	other-assets
README.md	docs/baseline/memory
addons/__init__.py	production-code
addons/cn/__init__.py	legacy/candidate/advisory
addons/cn/adapter.py	legacy/candidate/advisory
addons/cn/modal_mapping.yaml	legacy/candidate/advisory
addons/federation/__init__.py	legacy/candidate/advisory
addons/hk/__init__.py	legacy/candidate/advisory
addons/hk/adapter.py	legacy/candidate/advisory
addons/us/__init__.py	legacy/candidate/advisory
addons/us/adapter.py	legacy/candidate/advisory
addons/workbuddy_mcp.py	CLI/Client/MCP
compiler_core/__init__.py	production-code
compiler_core/adapter_base.py	legacy/candidate/advisory
compiler_core/adjudication_draft.py	production-code
compiler_core/admission.py	production-code
compiler_core/analysis.py	production-code
compiler_core/application.py	production-code
compiler_core/arbitration_reasoning.py	production-code
compiler_core/argumentation.py	production-code
compiler_core/argumentation_v2.py	production-code
compiler_core/audit.py	production-code
compiler_core/audit_bundle.py	production-code
compiler_core/backend_router_v1.py	production-code
compiler_core/banach_verifier.py	production-code
compiler_core/breakthrough_candidates.py	production-code
compiler_core/breakthrough_verification.py	production-code
compiler_core/burden_of_proof.py	production-code
compiler_core/canonical_serialization.py	production-code
compiler_core/certificate_checker.py	legacy/candidate/advisory
compiler_core/certificate_v1.py	production-code
compiler_core/classifier.py	production-code
compiler_core/cli.py	CLI/Client/MCP
compiler_core/client.py	CLI/Client/MCP
compiler_core/compat_v3_v4.py	legacy/candidate/advisory
compiler_core/completion_status.py	legacy/candidate/advisory
compiler_core/compliance_monitoring.py	production-code
compiler_core/config_paths.py	legacy/candidate/advisory
compiler_core/conflict_of_laws.py	production-code
compiler_core/constraint_validator.py	production-code
compiler_core/contracts.py	production-code
compiler_core/contracts_v4.py	production-code
compiler_core/criminal_complexity.py	production-code
compiler_core/criminal_sentencing.py	production-code
compiler_core/cross_jurisdiction_compare.py	production-code
compiler_core/cross_jurisdiction_router.py	production-code
compiler_core/defeasible_priority.py	production-code
compiler_core/domain_config.py	production-code
compiler_core/evaluator.py	production-code
compiler_core/evidence_chain_validator.py	legacy/candidate/advisory
compiler_core/evidence_checklist.py	production-code
compiler_core/evidence_evaluation.py	production-code
compiler_core/fact_admission_v1.py	production-code
compiler_core/fact_trust_envelope.py	legacy/candidate/advisory
compiler_core/g8_evaluator_patch.py	legacy/candidate/advisory
compiler_core/grounded_smt_verifier.py	production-code
compiler_core/horn_completeness.py	production-code
compiler_core/incremental_grounded.py	production-code
compiler_core/independent_grounded_checker.py	production-code
compiler_core/invariance_metrics.py	production-code
compiler_core/ip_valuation.py	production-code
compiler_core/jcs.py	production-code
compiler_core/kg_recall.py	production-code
compiler_core/legal_ir_v3.py	legacy/candidate/advisory
compiler_core/legal_memory.py	production-code
compiler_core/legal_reasoning.py	production-code
compiler_core/legal_spec_ivl.py	production-code
compiler_core/litigation_engineering.py	production-code
compiler_core/output_firewall.py	production-code
compiler_core/plugin_registry.py	legacy/candidate/advisory
compiler_core/prc_collision_engine.py	legacy/candidate/advisory
compiler_core/proleg_translator.py	legacy/candidate/advisory
compiler_core/proof_trace.py	production-code
compiler_core/proof_trace_visualizer.py	production-code
compiler_core/proof_tree.py	production-code
compiler_core/reasoning_boundary.py	production-code
compiler_core/rendering.py	production-code
compiler_core/resources.py	production-code
compiler_core/result_diff.py	production-code
compiler_core/result_exporter.py	production-code
compiler_core/review_packet.py	production-code
compiler_core/rule_governance.py	production-code
compiler_core/rule_lookup.py	production-code
compiler_core/rule_packs.py	production-code
compiler_core/rule_platform_cn.py	production-code
compiler_core/rule_router.py	legacy/candidate/advisory
compiler_core/smt_sidecar.py	legacy/candidate/advisory
compiler_core/source_anchor.py	legacy/candidate/advisory
compiler_core/source_manifest.py	legacy/candidate/advisory
compiler_core/source_service_v2.py	production-code
compiler_core/spec_shadow_harness.py	legacy/candidate/advisory
compiler_core/step_verifier.py	production-code
compiler_core/stratified_evaluator.py	legacy/candidate/advisory
compiler_core/taint.py	production-code
compiler_core/training.py	production-code
compiler_core/transformer.py	production-code
compiler_core/trust_labels.py	production-code
compiler_core/type_checker.py	legacy/candidate/advisory
compiler_core/types.py	production-code
compiler_core/universal_grounded_smt.py	production-code
compiler_core/validity_state_machine.py	production-code
compiler_core/version.py	production-code
configs/L0_overrides_cn.yaml	config/rule-pack
configs/L0_overrides_hk.yaml	config/rule-pack
configs/__init__.py	config/rule-pack
configs/core_ontology.yaml	config/rule-pack
configs/en_US/L0_overrides_us.yaml	config/rule-pack
configs/en_US/US_Adapter.yaml	config/rule-pack
configs/en_US/rules.yaml	config/rule-pack
configs/hk/blocking_rules.yaml	config/rule-pack
configs/hk/extended_rules.yaml	config/rule-pack
configs/hk/provenance.yaml	config/rule-pack
configs/hk/rules.yaml	config/rule-pack
configs/hk/term_L0_mappings.yaml	config/rule-pack
configs/hk/trilingual_alignment.yaml	config/rule-pack
configs/packs/cn-legacy-corpus/manifest.yaml	legacy/candidate/advisory
configs/packs/cn-official/build/README.md	config/rule-pack
configs/packs/cn-official/manifest.yaml	config/rule-pack
configs/packs/cn-official/release/README.md	config/rule-pack
configs/packs/cn-official/staging/README.md	config/rule-pack
configs/packs/hk-legacy-corpus/manifest.yaml	legacy/candidate/advisory
configs/packs/us-federal-legacy-corpus/manifest.yaml	legacy/candidate/advisory
configs/packs/us-l0-adapter-legacy-corpus/manifest.yaml	legacy/candidate/advisory
configs/perf_patterns.yaml	config/rule-pack
configs/prc_us_alignment/blocking_rules.yaml	config/rule-pack
configs/prc_us_alignment/meta_constraints.yaml	config/rule-pack
configs/prc_us_alignment/spc_rules.yaml	config/rule-pack
configs/prc_us_alignment/term_L0_mappings.yaml	config/rule-pack
configs/prc_us_alignment/term_L0_mappings_batch2.yaml	config/rule-pack
configs/prc_us_alignment/trirail_matrix_report.json	config/rule-pack
configs/render_profiles/neutral.yaml	config/rule-pack
configs/us/rules.yaml	config/rule-pack
configs/us/term_L0_mappings.yaml	config/rule-pack
configs/zh_CN/classifier_rules.yaml	config/rule-pack
configs/zh_CN/criminal_complexity.yaml	config/rule-pack
configs/zh_CN/domain_config.example.yaml	config/rule-pack
configs/zh_CN/ontology_map.yaml	config/rule-pack
configs/zh_CN/router_moe.yaml	config/rule-pack
configs/zh_CN/rules.yaml	config/rule-pack
configs/zh_CN/source_manifest.yaml	config/rule-pack
docs/README.md	docs/baseline/memory
docs/architecture/contract-authority-v4.md	docs/baseline/memory
docs/architecture/module-authority-registry.json	docs/baseline/memory
docs/architecture/module-authority-v4.json	docs/baseline/memory
docs/architecture/runtime-path-inventory.md	docs/baseline/memory
docs/audits/branch-adoption-decision.md	docs/baseline/memory
docs/audits/current-head-baseline.json	docs/baseline/memory
docs/contracts/AUDIT_BUNDLE.md	docs/baseline/memory
docs/contracts/EXTERNAL_PROTOCOL.md	docs/baseline/memory
docs/contracts/FORMAL_RUNTIME_CONFORMANCE.md	docs/baseline/memory
docs/contracts/INPUT_AND_SEMANTIC_BOUNDARY.md	docs/baseline/memory
docs/contracts/RULE_PACKS.md	docs/baseline/memory
docs/contracts/rendering-and-profiles.md	docs/baseline/memory
docs/guides/CLI.md	docs/baseline/memory
docs/guides/MIGRATION_V2_TO_V3.md	docs/baseline/memory
docs/guides/README_CN.md	docs/baseline/memory
docs/guides/WORKBUDDY.md	docs/baseline/memory
docs/operations/governance-training-analysis.md	docs/baseline/memory
mcp_manifest.json	CLI/Client/MCP
mcp_server.py	CLI/Client/MCP
memory.md	docs/baseline/memory
pipeline/__init__.py	legacy/candidate/advisory
pipeline/adversarial_pipeline.py	legacy/candidate/advisory
pipeline/experimental/__init__.py	legacy/candidate/advisory
pipeline/experimental/llm_client.py	legacy/candidate/advisory
pipeline/extract_concepts.py	legacy/candidate/advisory
pipeline/fix_single_premise.py	legacy/candidate/advisory
pipeline/guardian.py	legacy/candidate/advisory
pipeline/llm_client.py	legacy/candidate/advisory
pipeline/pipeline.py	legacy/candidate/advisory
pipeline/prc_us_alignment.py	legacy/candidate/advisory
pipeline/schemas.py	legacy/candidate/advisory
pyproject.toml	CI/build/release
requirements/core.lock	CI/build/release
requirements/dev.lock	CI/build/release
requirements/documents.lock	CI/build/release
requirements/pipeline.lock	CI/build/release
requirements/render.lock	CI/build/release
schemas/__init__.py	Schema/protocol
schemas/jc-v3.schema.json	Schema/protocol
schemas/jc-v4.schema.json	Schema/protocol
schemas/w1b/admission-result.schema.json	Schema/protocol
schemas/w1b/case-request.schema.json	Schema/protocol
schemas/w1b/proof-bundle-ref.schema.json	Schema/protocol
schemas/w1b/rule-admission-request.schema.json	Schema/protocol
tests/fixtures/ci_promotion_candidate.json	fixture/generated
tests/fixtures/ci_requests.jsonl	fixture/generated
tests/fixtures/golden/jcs-vectors.json	fixture/generated
tests/fixtures/legal_ir_v3_sample.yaml	fixture/generated
tests/fixtures/p0_regressions/README.md	fixture/generated
tests/fixtures/p0_regressions/p0_regression_matrix.json	fixture/generated
tests/fixtures/rule_migration_sample.yaml	fixture/generated
tests/fixtures/synthetic_case_index.json	fixture/generated
tests/fixtures/theory_absorption/README.md	fixture/generated
tests/fixtures/theory_absorption/manifest.json	fixture/generated
tests/fixtures/theory_absorption/p01_human_research_receipt.json	fixture/generated
tests/fixtures/theory_absorption/p02_source_snapshot.json	fixture/generated
tests/fixtures/theory_absorption/p03_argumentation.json	fixture/generated
tests/fixtures/theory_absorption/p04_solver_routing.json	fixture/generated
tests/fixtures/theory_absorption/p05_proposal_envelope.json	fixture/generated
tests/fixtures/theory_absorption/p06_temporal_applicability.json	fixture/generated
tests/fixtures/theory_absorption/p07_translation.json	fixture/generated
tests/fixtures/theory_absorption/p08_source_path.json	fixture/generated
tests/fixtures/theory_absorption/p09_fact_admission.json	fixture/generated
tests/run_benchmark_zh.py	tests
tests/stress_test_facts.py	tests
tests/unit/__init__.py	tests
tests/unit/test_adjudication_draft_and_smt.py	tests
tests/unit/test_adversarial.py	tests
tests/unit/test_advisory_governance.py	tests
tests/unit/test_application_service.py	tests
tests/unit/test_argumentation_v2.py	tests
tests/unit/test_audit_bundle.py	tests
tests/unit/test_audit_events.py	tests
tests/unit/test_backend_router_v1.py	tests
tests/unit/test_canonical_serialization.py	tests
tests/unit/test_case_admission.py	tests
tests/unit/test_case_contracts.py	tests
tests/unit/test_certificate_v1.py	tests
tests/unit/test_cli_contract.py	tests
tests/unit/test_cli_evaluate_subprocess.py	tests
tests/unit/test_cli_subprocess.py	tests
tests/unit/test_completion_status.py	tests
tests/unit/test_conflict_of_laws.py	tests
tests/unit/test_constraint_validator.py	tests
tests/unit/test_contracts_v4.py	tests
tests/unit/test_criminal_complexity.py	tests
tests/unit/test_cross_process_determinism.py	tests
tests/unit/test_ddl_modal_gate.py	tests
tests/unit/test_evaluator.py	tests
tests/unit/test_fact_admission.py	tests
tests/unit/test_fact_admission_v1.py	tests
tests/unit/test_fast_path_interceptor.py	tests
tests/unit/test_graph_document.py	tests
tests/unit/test_grounded_g9a.py	tests
tests/unit/test_independent_checker.py	tests
tests/unit/test_legal_spec_ivl.py	tests
tests/unit/test_litigation_certificates.py	tests
tests/unit/test_llm_proposal_boundary.py	tests
tests/unit/test_mcp_manifest_dispatch.py	tests
tests/unit/test_mcp_stdio_protocol.py	tests
tests/unit/test_module_authority_registry.py	tests
tests/unit/test_new_modules.py	tests
tests/unit/test_nonmonotone_regression.py	tests
tests/unit/test_p1_ir_smt.py	tests
tests/unit/test_performance_gate.py	tests
tests/unit/test_phase6_cli.py	tests
tests/unit/test_plugin_registry.py	tests
tests/unit/test_reasoning_boundary_conflict_certificate.py	tests
tests/unit/test_reasoning_boundary_provenance.py	tests
tests/unit/test_reasoning_boundary_renderer_firewall.py	tests
tests/unit/test_reasoning_boundary_result_status.py	tests
tests/unit/test_reasoning_boundary_review_packet.py	tests
tests/unit/test_reasoning_boundary_taint_propagation.py	tests
tests/unit/test_release_engineering.py	tests
tests/unit/test_rendering.py	tests
tests/unit/test_replay.py	tests
tests/unit/test_rule_admission.py	tests
tests/unit/test_rule_pack_manifest.py	tests
tests/unit/test_rule_pack_manifest_builder.py	tests
tests/unit/test_rule_platform_cn.py	tests
tests/unit/test_source_service_v2.py	tests
tests/unit/test_spec_shadow_harness.py	tests
tests/unit/test_supply_chain_gate.py	tests
tests/unit/test_three_entrypoint_parity.py	tests
tests/unit/test_training_export.py	tests
tests/unit/test_trirail_collision.py	tests
tests/unit/test_trirail_runtime.py	tests
tests/unit/test_trust_labels.py	tests
tests/unit/test_us_pack_identity.py	tests
tests/unit/test_v3_entrypoint_boundary.py	tests
tests/unit/test_v3_semantic_baseline.py	tests
tests/unit/test_w1b_contracts.py	tests
tests/unit/test_w9_admission.py	tests
tests/unit/test_zh_rules.py	tests
tools/build_provenance.py	CI/build/release
tools/build_rule_pack_manifests.py	CI/build/release
tools/fast_path_interceptor.py	legacy/candidate/advisory
tools/perf_baseline.py	legacy/candidate/advisory
tools/run_trirail_matrix.py	legacy/candidate/advisory
tools/supply_chain_gate.py	CI/build/release
tools/wheel_gate.py	CI/build/release
```

### [我违规之处]

- 无
