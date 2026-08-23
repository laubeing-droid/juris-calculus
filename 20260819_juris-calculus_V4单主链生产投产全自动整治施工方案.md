# Juris Calculus V4 单主链生产投产全自动整治施工方案

日期：2026-08-19

修订：2026-08-19 CodeGraph 调用图复核、反过度工程校正及 CN legacy corpus 删除决策

问题基线：`20260819_juris-calculus_V4单主链生产投产全量代码审计.md`

问题基线 SHA-256：`9b38e52c0181dbace4758d8c681009a61427baa53b1af2dae9e9c5d20f5e31a3`

起始判定：**No-Go；P0 15 / P1 20 / P2 7 / P3 2。**

本方案目标：让一个持续运行的编码 Agent 在独立工作树内，按照机器任务图自动完成工程整治、测试、证据生成和本地提交；遇到法律审批、生产密钥、远端治理、发布授权等真实外部条件时，生成可签发的请求并停止。外部条件满足后，用同一命令续跑，直至 V4 Kernel RC、真实 `cn-official`、DSH formal profile 全部闭环。

本方案不是完成声明。本任务只编写方案，不修复审计发现的 Bug。

## 0. 已锁定的产品决策

1. 当前公共 API、包根、CLI、Python Client、MCP、Schema、Application、Certificate、AuditBundle、verify、replay 全部只允许 V4。
2. 当前源码和发行物不保留 V3/W1b adapter、parser、fallback、auto-upgrade、双写、双 authority 或“临时兼容”。
3. V3 只由冻结的 tag、wheel、lock、spec、隔离环境重放；V4 不读取、不迁移、不修复 V3 state。
4. 施工顺序固定：**V4 Kernel RC → 真实 `cn-official` → DSH formal profile**。
5. 通用 DSH 保持即插即用，不依赖 JC；只有 formal legal profile 必须通过 JC V4，且交付前必须独立 `verify_run` 成功。
6. candidate、教材、OCR、类案、旧法域、三轨、训练、advisory 资产可继续用于发现和候选生成，但不能进入 formal wheel、formal numerator 或正式证书。
7. 一个从不产出正式结果的内核不算安全完成。Kernel RC 必须用 synthetic signed pack 产出可 verify/replay 的正向结果；法律生产必须再用真实 signed `cn-official` 产出正向结果。
8. 不允许通过免责声明、空 pack、假 receipt、测试直接构造 trusted object 或硬编码 inactive 来保护不可用状态。
9. 物理拓扑固定为：一个 JC source repo、一个 V4 production wheel、一个独立签名的 `cn-official` pack artifact。candidate assets、rule-engineering source、jurisdiction experiments 默认同仓保存，但不得进入 production wheel、默认 runtime registry 或生产部署。不得仅因 LOC、目录大小或“非 formal”新建 repo/distribution/service。
10. “不进入 formal wheel”不等于“必须外迁”。本轮不批准为 JC 非生产源码新建 repo/distribution/service；独立发行建议只能登记为 `POST_RELEASE_RFC`，不得改变本轮一仓一 wheel 拓扑、文件处置或 Z03 结果。
11. 零 import、零 caller、零测试或 Git 有历史均不能单独授权删除。涉及 Horn、attack、exception、permission、priority、checker、witness、translation loss、source/fact admission、certificate、domain scope 或 mutation/differential oracle 的内容，必须先迁到目标模块/required test/artifact并验绿。
12. CodeGraph 用于发现 import/call/instantiate/impact 候选边，源码 AST、动态 import、入口、配置消费和测试再复核；图索引不是 module authority，也不是删除权威。大资产和 CodeGraph 不支持的文件由 Git blob、byte/record inventory 闭合。
13. 复杂度同时报告仓库 tree 变化、同仓移动、artifact 重建、替代实现和全系统真实删除；移动或重建不得计作 whole-system deletion，LOC 不得作为完成门禁。
14. `configs/zh_CN/rules.yaml` 是 V3 `cn-legacy-corpus` 候选语料，不是正式法源或 `cn-official`。用户已决定在 W5 从 current tree 移除，并断开全部 executable/config/CI/test/default-registry consumer；只允许审计、施工方案、项目 memory、冻结 receipt 和 Git 历史 locator继续引用该逻辑路径。删除授权只绑定 SHA-256 `032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44`、13,620,766 bytes、21,144 unique rule IDs；任一值变化必须重新请求授权。不得把这 21,144 条批量复制、改名或自动转换进 `cn-official`。

## 1. “机器自动执行到底”的准确含义

### 1.1 自动化边界

机器可以自动完成：

- 固定 Git 基线、创建独立 branch/worktree、建立任务状态；
- 在任何模块处置前建立并同步 CodeGraph，导出 observed import/call graph，补查动态 import、入口和未入图资产；
- 逐任务编写测试、修改代码、归位、合并或删除旧 authority；
- 执行 unit/contract/property/integration/E2E/security/chaos/packaging gates；
- 从唯一权威对象确定性导出 Schema、ToolSpec 发布物、observed 模块图、文件处置表、SBOM、provenance、checksums 和证据清单；
- 对 changed paths、依赖、任务状态、测试退出码、产物摘要做确定性核验；
- 每个 green task 自动生成一个本地 Git commit；
- 中断后验证已有 receipt 和 commit，再从第一个未完成任务续跑；
- 在已有合法审批、密钥服务和发布授权的条件下构建、签名、晋级不可变 artifact。

机器不能自行替代：

- 中国法规则的法律解释选择、现行有效性确认和正式法律审核；
- 生产私钥/HSM 托管、签发者身份、角色分离、撤销和轮换授权；
- GitHub branch/tag protection、CODEOWNERS 审批、push/tag/release 权限；
- 生产 state provider、DACL、加密、retention、legal hold、备份恢复的现场能力确认；
- DSH 真实部署拓扑和允许安装的 pinned release/commit 决策。

这些不是“待办文字”。执行器必须把它们编码为 `HUMAN_GATE` 或 `EXTERNAL_GATE`：生成带 subject digest 的请求，退出并返回唯一恢复命令。没有合格响应时不得猜测 PASS。

### 1.2 双层执行器

```text
持续编码 Agent
  └─ 读取本方案和审计报告
     └─ 调用唯一 runner：tools/remediate_v4.py
        ├─ tasks.json：DAG、allowed paths、gates、audit IDs
        ├─ 外部 state root：task state、logs、receipts、artifacts
        ├─ Git guard：独立 worktree、scope diff、commit/tree 校验
        ├─ Gate runner：tests/build/install/verify/replay/security
        └─ Human gate verifier：请求、签名响应、role/scope/subject 校验
```

`tools/remediate_v4.py` 负责任务编排和证据核验，不负责“凭空生成正确代码”。编码 Agent 每次只实现 runner 返回的一个 work order；实现完成后由 runner 验收、提交、进入下一任务。

### 1.3 唯一启动与续跑命令

Bootstrap 任务 `B00` 尚未创建 runner 前，编码 Agent按第 24 节启动提示执行。`B00` 完成后，唯一命令为：

```powershell
py -3.12 -B tools/remediate_v4.py run `
  --plan remediation/v4/tasks.json `
  --state-root $env:JC_REMEDIATION_STATE_ROOT `
  --through W9
```

重复执行同一命令必须：已完成任务验证后跳过；未提交任务继续；人工门禁缺失时返回请求；全部完成时返回 0。不得依赖聊天上下文记忆当前进度。

## 2. 开工隔离和 Git 保护

### 2.1 禁止直接在当前工作树施工

当前工作树存在两份用户既有未暂存删除。执行器不得恢复、暂存、提交、覆盖或用它们判断整治结果：

- `20260815_juris-calculus理论成果全量吸收施工方案.md`
- `20260819_juris-calculus_V4单主链全量切换与生产投产施工方案.md`

开工时从包含本方案的 commit 创建独立工作树：

```powershell
$SOURCE_REPO = (git rev-parse --show-toplevel)
$EXEC_WORKTREE = Join-Path (Split-Path $SOURCE_REPO -Parent) 'juris-calculus-v4-remediation'
$EXEC_BRANCH = 'v4-remediation'

git -C $SOURCE_REPO worktree add -b $EXEC_BRANCH $EXEC_WORKTREE HEAD
git -C $EXEC_WORKTREE status --short --branch
```

若 branch 或 worktree 已存在，禁止自动覆盖。执行器应验证其登记的 Git common dir、branch、start commit 和 state receipt；能验证则续跑，不能验证则以 `BASELINE_DRIFT` 停机。

### 2.2 开工快照

`B00` 固定并写入 `run.json`：

- start commit/tree、branch、remote URL、tag、package version；
- 审计报告 bytes digest 和方案 bytes digest；
- tracked path/mode/blob digest 清单；
- Python、Node、Git、OS、filesystem、locale、timezone；
- companion spec commit/availability；
- 当前支持矩阵和外部 state root identity；
- 用户工作树保护项，只记录 path/status，不读取或复制其未提交内容。

后续仓库新增文件是任务产物；旧数量 292 不是永恒常量。每个波次结束重新生成 tracked 清单，并要求每个 path 恰有一个 disposition 和 authority class。

### 2.3 自动 Git 纪律

- 一个任务一个 green commit；跨任务修改禁止暂存。
- runner 在 `begin` 时记录 clean tree；在 `verify` 前检查 changed paths 是任务 allowlist 的子集。
- commit 前执行该任务 gates 和全局 smoke；非零退出不得提交。
- commit message 由 runner 生成，包含 Files、Root cause、New knowledge、Impact、Audit IDs、Validation、Receipt digest。
- 不使用 `git reset --hard`、`git clean`、强制 checkout 或历史改写。
- 失败的未提交工作保留在专用工作树供修复；若放弃，人工确认绝对路径后移除整个专用 worktree，不触碰源工作树。
- 后续回归用新的修复 commit；已签 artifact 不原地替换。
- 默认不 push、tag、merge、release。远端写操作必须由 `HUMAN_GATE-RELEASE` 授权。

## 3. Runner、任务和证据合同

### 3.1 Bootstrap 只新增一个编排入口

`B00` 创建：

```text
tools/remediate_v4.py               # 唯一 orchestration CLI
remediation/v4/tasks.json            # 机器 DAG
remediation/v4/task.schema.json      # task/work-order schema
remediation/v4/receipt.schema.json   # receipt schema
remediation/v4/approval.schema.json  # human/external response schema
remediation/v4/issue-map.json        # 44 项审计问题映射
remediation/v4/file-disposition.json # 当前所有 tracked path 处置
```

编排逻辑保持标准库优先。若拆分内部模块，只允许位于 `tools/remediation/`，不得进入 formal wheel；对外仍只有 `tools/remediate_v4.py` 一个命令。

`tasks.json`、`issue-map.json`、`file-disposition.json`、observed graph 和 receipts 是施工期控制面，不是生产 current authority。Z02 封存后不得再作为 runtime、current docs 或日常 CI 输入；长期架构政策只有人工审核的 `docs/architecture/module-authority.json`。

### 3.2 Task 必填字段

每个 task object 必须具有：

```json
{
  "id": "W1-01",
  "wave": "W1",
  "mode": "AUTO",
  "depends_on": ["W0-04"],
  "audit_ids": ["P0-03", "P1-01"],
  "objective": "one measurable outcome",
  "allowed_paths": ["compiler_core/canonical_serialization.py", "tests/contract/**"],
  "forbidden_paths": ["requirements/*.lock"],
  "preconditions": [],
  "test_first": true,
  "red_commands": [],
  "red_failure_assertions": [],
  "commands": [],
  "expected_exit_codes": [0],
  "required_artifacts": [],
  "completion_assertions": [],
  "rollback": "do not promote; fix in dedicated worktree",
  "commit_type": "refactor"
}
```

禁止用自由文本 `PASS`、文件存在或测试总数代替 `completion_assertions`。完成断言必须由 runner 重新计算。

### 3.3 状态机

```text
PENDING -> READY -> RUNNING -> VERIFYING -> PASSED -> COMMITTED
                    |              |
                    |              +-> FAILED
                    +-> WAITING_HUMAN / WAITING_EXTERNAL / BLOCKED
```

只有 `COMMITTED` 计入依赖完成。状态转换规则：

- `READY`：全部依赖的 receipt、commit 和 tree 复验成功；
- `RUNNING`：工作树基线与 allowlist 已锁定；
- `VERIFYING`：测试、build、artifact 检查已开始；
- `PASSED`：全部命令退出码和 completion assertions 通过；
- `COMMITTED`：commit 只含 allowlist 文件，commit/tree 与 receipt 对应；
- `WAITING_HUMAN`：请求已生成但无合格签名响应；
- `WAITING_EXTERNAL`：所需 VM/HSM/repo/API/provider 不可用；
- `BLOCKED`：发现合同漂移、安全越界、任务图缺陷；
- `FAILED`：实现或 gate 失败，可修复后增加 attempt 继续同 task。

### 3.4 外部状态目录

```text
<state-root>/
  run.json
  inputs/
  requests/
  approvals/
  tasks/<task-id>/<attempt>/
    work-order.json
    commands.jsonl
    stdout/
    stderr/
    artifacts/
    receipt.json
  evidence/
  releases/
```

状态目录必须在 Git 仓库外。日志可含机器路径，不能被打入 wheel、certificate 或公开 release evidence；公开 evidence 只引用允许披露的摘要和逻辑名称。

### 3.5 Receipt 必填字段

每份 task receipt 至少绑定：schema、run/task/attempt、input task receipts、start commit/tree、changed paths、red/green 命令和 exit code、红灯失败断言、stdout/stderr digest、test report digest、artifact digest、audit IDs、completion assertion results、result commit/tree、runner version、前一 receipt digest。

Receipt 内容寻址、append-only，不原地覆盖。子进程使用 argv 数组调用，不用 shell 拼接；只登记允许传入的环境变量名称，不把值写入 receipt。时间、PID、主机只在 observability 区，不进入 task semantic digest。Resume 时 runner 必须重新验证 commit、tree、changed paths 和 artifact digests；单独修改 `run.json` 的状态不能让任务变成完成。Production verifier 必须拒绝 test/synthetic realm 的 issuer、key、receipt 和 artifact。

### 3.6 Human/External gate 合同

请求：

```json
{
  "schema_version": "jc/remediation-gate-request/1.0",
  "gate_id": "H8-LEGAL-APPROVAL",
  "task_id": "W8-04",
  "subject_digest": "sha256:<hex>",
  "required_roles": ["legal_reviewer", "engineering_reviewer"],
  "separation_of_duties": true,
  "scope": "named domain and exact rule digest set",
  "expires_at": "RFC3339 instant",
  "resume_command": "..."
}
```

响应必须绑定 request digest、decision、signer key/role/scope、issued/expiry、signature。Runner 校验签名、trust policy、角色分离、subject 和时效；`REJECT` 使 task BLOCKED，缺失使其 WAITING_HUMAN。测试 key 不能批准 production gate。

### 3.7 Runner 退出码

| Code | 含义 | 自动行为 |
| ---: | --- | --- |
| 0 | 当前目标完成或本次动作 PASS | 继续下一个 READY task |
| 2 | 命令/输入错误 | 修正 invocation；不改代码 |
| 3 | baseline/worktree drift | 停止，核对 Git/state |
| 4 | test/build/gate failure | 留在当前 task，根因修复后重试 |
| 5 | receipt/artifact verification failure | 停止 promotion，重新生成合法证据 |
| 6 | scope/security violation | 硬停；不得自动扩 allowlist |
| 20 | WAITING_HUMAN | 输出请求路径和 resume command |
| 21 | WAITING_EXTERNAL | 输出缺失设施和可验证条件 |
| 22 | release authorization missing | 禁止任何远端写入 |

### 3.8 编码 Agent 闭环

每个 `AUTO` task 执行顺序固定：

1. runner 输出唯一 work order；
2. Agent 读取相关代码、合同和已有测试；
3. 先增加/改写会失败的测试；runner 执行 `red_commands`，只在非零退出且错误类型/断言命中 `red_failure_assertions` 时记录有效红灯；测试未运行、因 import/语法/环境错误失败或意外通过都不得进入实现；
4. 仅修改 allowlist；不做 drive-by refactor；
5. 运行 task commands；读取完整错误栈；修根因；
6. runner 验证 completion assertions、issue map、file disposition、diff；
7. runner 创建 task receipt 和本地 commit；
8. 重新执行 runner，进入下一 task；
9. 同一错误连续三次仍无进展，task 置 BLOCKED 并输出三次差异和最小外部问题。

Release、tag、生产签名、法源 custody confirmation 等非幂等动作重试前，runner 必须按 subject digest/idempotency key 查询现有外部结果；不得盲重放。相同 version 下出现不同 artifact digest 时以 `VERSION_COLLISION` 硬停。

## 4. 全局不变量

### 4.1 唯一 authority

- `compiler_core/contracts.py` 是当前 V4 typed contract 唯一源。
- `compiler_core/mcp.py::TOOL_SPECS` 是四工具名称、输入/输出/error 映射的唯一协议源，并只引用 `contracts.py` 的类型；`schemas/jc-v4.schema.json` 和 `mcp_manifest.json` 是一个小型确定性 emitter 的发布物。runtime 不读取仓库 manifest/path；capabilities 值从实际 wheel、pack、trust、storage、provider 状态动态投影。
- `docs/architecture/module-authority.json` 是人工规定的唯一模块 policy；AST/import graph 只生成 observed graph 并验证 policy，不得自动填写分类、允许边或删除结论。
- `ApplicationV4` 是 formal evaluation 唯一 sink；入口、renderer、advisory、DSH 不得复制法律判断。
- `compiler_core/version.py` 是 package、CLI、MCP、capabilities、RunIdentity 唯一版本源。
- 派生物遵循“一份权威对象 + 一个 checker/serializer”：禁止为 Schema、ToolSpec、module graph、wheel allowlist 或单实现 pack builder 再造通用 generator framework、registry 或 interface。

### 4.2 V4-only

- 当前 source、tests、Schema、wheel、docs 不存在 V3/W1b/compat public authority。
- V3 payload/bundle/import 一律明确失败，不猜测、不转换、不补字段。
- 内部 current modules 使用无代际后缀路径；公开 wire objects 可保留 `V4` 后缀。
- 迁移期的非 green commit 不可进入 production branch、build 或 release。

### 4.3 Trust 和 fail-closed

- 外部只能提交 candidate bytes/typed refs，不能提交 PASS、GateOutcome、active、solver/checker receipt、certificate 或 build identity。
- Digest 统一为 `sha256:<64 lowercase hex>`；JCS 遵循 RFC 8785/I-JSON；禁止 float、NaN、Infinity、unsafe integer。
- 所有 `SignedReceiptV4` 固定绑定 kind、schema、subject digest、run identity、issuer key、role、scope、status、issued/expiry、nonce、evidence refs、payload digest、policy digest、撤销状态和 signature；公共 API 不接收 gate-status map。
- candidate、unknown/disputed、translation loss、checker disagreement、expired/revoked、unsupported semantics、storage unverified 均不得签 formal certificate。
- Backend 的 `UNKNOWN|TIMEOUT|RESOURCE_EXHAUSTED|UNSUPPORTED|UNCHECKED_PROOF` 均是封闭状态，不得折叠成 false、PASS 或普通成功。
- 任一异常不能 silent fallback 到 V3、advisory、默认 domain/config 或协议 success。

### 4.4 隐私、资源和确定性

- formal MCP 不接受 OS path；只接受 bounded inline V4 object 或服务签发的 opaque capability。
- semantic digest 不含时间、PID、绝对路径、随机 staging 名或日志顺序。
- request/JSON/artifact/state 都有 byte、depth、count、deadline、cancel、quota、retention 限制。
- audit bundle 不保存原始案情叙述、密钥/token、无关规则、机器路径；结构事实也受 DACL/encryption/retention 约束。
- 同一 inputs/build/pack/trust 必须得到相同 result/certificate/bundle；不同 build 不得复用 run identity。
- chaos、kill、disk-full、ACL、reparse 和 power-loss 测试只允许使用带 test-realm 哨兵的独立临时 state root；runner 必须拒绝生产 namespace、production key/service identity 或无哨兵目录。

## 5. 目标 formal runtime 图

```text
CLI / JCClient / formal MCP
             |
       strict V4 codec
             |
       ApplicationV4
             |
 ArtifactResolver + TrustPolicy
             |
 Source -> Evidence -> Fact admission
             |
 immutable signed pack snapshot
             |
 RuleV4 -> LegalSpecV4 -> LegalIVLV4
             |
 certified backend invocation
             |
 independent checker + argumentation
             |
 SemanticResultV4 -> CertificateV4
             |
 AuditBundleV4 -> verify -> offline replay
       |
       `-> audited neutral renderer -> presentation artifact
```

目标 core 路径：

| 路径 | 唯一职责 |
| --- | --- |
| `compiler_core/contracts.py` | 全部 V4 models、states、limits、codegen input |
| `compiler_core/canonical_serialization.py` | RFC 8785、DigestV4、canonical bytes |
| `compiler_core/trust.py` | signature/trust/key/revocation verifier |
| `compiler_core/artifact_store.py` | typed resolver、content store、storage capability |
| `compiler_core/source_service.py` | source/evidence/version/path verification |
| `compiler_core/fact_admission.py` | typed fact admission |
| `compiler_core/rule_packs.py` | immutable signed pack runtime、deterministic verify/admission、bounded inspection；不做候选生成或人工 promotion 编排 |
| `compiler_core/legal_ir.py` | RuleV4、LegalSpecV4、LegalIVLV4、loss accounting |
| `compiler_core/backends/` | 已认证的 provider implementations |
| `compiler_core/backend_router.py` | 从 IR 派生 feature 并路由 certified provider |
| `compiler_core/argumentation.py` | attack/priority/permission/grounded semantics |
| `compiler_core/independent_checker.py` | 与 production provider 分离的验证 |
| `compiler_core/certificates.py` | typed receipt verification、formal/conflict certificates |
| `compiler_core/audit.py` | typed deterministic semantic events |
| `compiler_core/audit_bundle.py` | V4 writer/verify/replay |
| `compiler_core/application.py` | 唯一 orchestration/state matrix |
| `compiler_core/rendering.py` | 只消费 verified AuditBundle 的 neutral renderer；同一 production wheel 的 `RUNTIME_OUTPUT`，不可调用 evaluator/Application.evaluate |
| `compiler_core/client.py` | Python facade |
| `compiler_core/cli.py` | CLI adapter |
| `compiler_core/mcp.py` | formal MCP adapter |
| `compiler_core/resources.py` | generated schema/static resource lookup |
| `compiler_core/version.py` | 唯一版本源 |

`analysis`、`training`、人工 governance/promotion report、candidate lookup 和 pipeline 属于同仓 source tools；legacy jurisdiction adapters、TriRail 和 fast-path 属于同仓 experiments；其他 legacy corpus 属于同仓 candidate assets。它们可保留现有路径或经一次性批准在仓内归位，但不得出现第二套 package metadata、release workflow、deployment manifest 或运行时自动发现。`configs/zh_CN/rules.yaml` 是第0节第14项的显式删除例外，不得被“candidate 默认保留”覆盖，也不得为了保存它另建 repo/artifact。禁止仅为目录整洁移动其他大资产。

## 6. 总 DAG

```text
B00 -> B00-CG -> B01 -> B02
  -> W0-01..05
  -> W1-01..06
  -> W2-01..06
  -> W3-01..05
  -> W4-01..07
  -> W5-01 -> H5-02 -> W5-02C -> W5-03 -> W5-CUTOVER -> W5-05..07
  -> W6-01 -> H6-02 -> W6-03..06 -> H6-07 -> W6-08
  -> H7-00 -> W7-01..04 -> optional H7-05
  -> H8-00 -> W8-01..02 -> H8-03..04 -> W8-05..06 -> H8-07
  -> H9-00 -> W9-01..06
  -> Z00-Z03
```

W0-W7 允许使用隔离 test trust root 和 synthetic signed pack；这些 artifact 的 scope 必须是 `test-only`，不能通过任何 production gate。W8、W9 的 HUMAN_GATE 未满足时，runner 正常停在 exit 20，而不是宣告整个计划完成。

## 7. Bootstrap 和 W0：把施工本身变成可验证系统

以下命令中的 `$R` 指外部 remediation state root。所有 pytest 命令使用 `-p no:cacheprovider` 和位于 `$R` 的短 `--basetemp`，避免污染仓库并规避 Windows 路径长度问题。

### B00　Runner 与 schema

- **Mode / depends / audit**：`AUTO / none / 全部问题的执行基础`。
- **Allowed paths**：`tools/remediate_v4.py`、`tools/remediation/**`、`remediation/v4/*.json`、`.gitignore` 中仅新增外部状态误落仓库的保护规则。
- **先写测试**：`tests/unit/test_remediation_runner.py`；覆盖 DAG cycle、未知依赖、allowlist escape、receipt 篡改、commit 不匹配、resume、三类 waiting gate。
- **实现**：task loader、schema validator、state machine、subprocess capture、SHA-256、Git diff/commit guard、request/receipt writer。Runner 不调用网络，不保存凭证，不自行扩大 scope。
- **Gate**：

```powershell
py -3.12 -B -m pytest tests/unit/test_remediation_runner.py -q -p no:cacheprovider --basetemp "$R/tmp/B00"
py -3.12 -B tools/remediate_v4.py lint-plan --plan remediation/v4/tasks.json
```

- **PASS**：DAG 无环；每个 task/schema 有 digest；故意改 receipt、commit、allowed path 时均非零退出；resume 能跳过已验证 commit。
- **Commit**：`build(remediation): add resumable V4 task runner`。

### B00-CG　CodeGraph 全仓索引和双清单基线

- **Mode / depends / audit**：`AUTO / B00 / 全文件处置和调用关系基础`。
- **Allowed paths**：`.gitignore` 仅允许加入 `/.codegraph/`，另允许 `tools/remediate_v4.py`、`tools/remediation/**` 和对应 graph-map unit tests；索引数据库、normalized graph、查询结果和 receipt 全部写入 `$R/evidence/codegraph/$SOURCE_TREE_ID/` 或本机 ignored `.codegraph/`，不跟踪数据库。
- **实现**：runner 将 `git rev-parse 'HEAD^{tree}'` 的 validated lowercase hex 结果记为 `SOURCE_TREE_ID`，并在 B00-CG receipt 返回 normalized graph 的 canonical artifact path；锁定并记录 CodeGraph CLI 版本，执行 clean full index；通过只读 SQLite schema/CLI 导出 Python import/call/instantiate 边、symbol/file 位置、unresolved refs 和 parse errors；用 AST/`rg` 补查函数内 import、`importlib`、`__import__`、plugin discovery、`__main__`、CLI entrypoint 和 package-root export。将 CodeGraph files 与 `git ls-files` 对账；未入图的大 YAML/JSON/Markdown/lock/assets 进入 Git blob、SHA-256、byte/record inventory，不得消失。
- **当前快照证据**：CodeGraph `0.9.7` 在 2026-08-19 基线上收录 228 files（191 Python、37 YAML）、3,029 nodes、7,051 edges、0 unresolved、0 parse error、worktree mismatch null；Git tracked Python/YAML/YML 为 229，唯一未入图文件是 13,620,766-byte 的 `configs/zh_CN/rules.yaml`。B00-CG 必须先以 asset inventory 闭合它，W5-02C再按授权删除并让最终 tracked coverage重算。以上是开工快照，不是永久计数，runner 每次按 source tree 重算。
- **限制门禁**：CodeGraph 的空 callers/impact、同名实例方法解析和 `affected` 输出不得单独作删除结论；每条 deletion-relevant 边必须回到 exact source range/AST 复核。已知动态边至少包括 `plugin_registry.py` 加载 `addons.*` 和 shadow harness 加载 companion spec。
- **Gate**：

```powershell
codegraph --version
codegraph index --force .
codegraph status --json .
py -3.12 -B tools/remediate_v4.py graph-map --check --codegraph .codegraph/codegraph.db --all-tracked
```

- **PASS**：索引与 start tree 绑定；pending changes=0、worktree mismatch=null、parse errors=0、unresolved refs=0；tracked file union=`codegraph-indexed ∪ asset-inventory`，交集/缺失/额外均可解释且无遗漏；normalized graph receipt 可复算。
- **Commit**：只提交 `.gitignore` 和 runner 的 graph-map 支持；不提交 `.codegraph/**` 或机器路径。

### B01　审计问题和 tracked 文件闭合

- **Mode / depends / audit**：`AUTO / B00-CG / P0-01..15, P1-01..20, P2-01..07, P3-01..02`。
- **Allowed paths**：`remediation/v4/issue-map.json`、`remediation/v4/file-disposition.json`、`tools/remediate_v4.py`、`tools/remediation/**` 和对应 audit-map/file-map unit tests。
- **实现**：从审计报告登记 44 个 ID；从当前 Git tree 和 B00-CG observed graph 重新生成 path/mode/blob digest及静态/动态 consumers。每个 tracked path 必有 `KEEP_REWRITE|MERGE_DELETE|MIGRATE_INVARIANTS_THEN_DELETE|RETAIN_NONPACKAGED|MOVE_IN_REPO_SOURCE_TOOL|MOVE_IN_REPO_EXPERIMENT|CANDIDATE_ASSET|TEST_ORACLE|DELETE_CURRENT|GENERATED|HISTORY_ONLY|DOC_UPDATE` 之一，并填写 `semantic_assets`、`target_module`、`target_test`、`target_artifact`、`target_consumer`、最迟 task、删除前置 receipts 和 terminal state。
- **固定 disposition**：`configs/zh_CN/rules.yaml` 与 `configs/packs/cn-legacy-corpus/manifest.yaml` 均为 `DELETE_CURRENT/HISTORY_BOUND`，最迟 task=`W5-02C`，`target_module=null`、`target_artifact=null`，`cn-official`不得登记成迁移目标。前者绑定第0节第14项fingerprint和`v3.0.2:configs/zh_CN/rules.yaml`/Git blob `8f51fdfd1db3e343812e8f35a321418fa854f4f7`；后者绑定SHA-256 `5613b20bc5e3f61655f087b827e946e58cb38e13ff985f4e01779dc4993f41f7`、`v3.0.2:configs/packs/cn-legacy-corpus/manifest.yaml`/Git blob `1b29b412ee97563381f5a9b32e8b8efb9f62e90c`及其对前者的引用。其 source manifest、ontology、domain example必须各自独立分类，不得随目录连删。
- **Terminal state**：删除候选初始一律 `UNREVIEWED`，`--deletions-ready` 按以下互斥分支验证，不得把所有终态强行套用同一 target：
  - `MIGRATED_GREEN`：必须绑定 target module、RED→GREEN required test、result commit/tree；
  - `HISTORY_BOUND`：必须绑定 frozen bytes/hash/locator 与 current negative rejection；`target_module`、`target_artifact`必须为空；内容资产还必须绑定exact-path/fingerprint删除授权，不能用Git历史代替授权；
  - `NO_RELEVANT_SEMANTICS_APPROVED`：必须绑定 symbol-level semantic inventory、CodeGraph+AST+动态 consumer 复核、H5 具名审批 receipt 和删除后的 negative import/path gate；`target_module` 可以为空。
  零 consumer、零 caller 或 Git 可恢复不能把 `UNREVIEWED` 自动改为 terminal；`POST_RELEASE_RFC` 不是 disposition 或 terminal state，不能授权删除。
- **Gate**：

```powershell
py -3.12 -B tools/remediate_v4.py audit-map --audit 20260819_juris-calculus_V4单主链生产投产全量代码审计.md --check
py -3.12 -B tools/remediate_v4.py file-map --check --all-tracked --require-semantic-targets --graph-receipt-task B00-CG
```

- **PASS**：44/44 问题恰好一次登记且至少一个 closure task；current tracked paths missing/extra/duplicate 均 0；新增 path 也必须有 disposition；无待删除 path 仅以 caller=0 为理由；各 terminal branch 的 required/forbidden fields 均满足，迁移目标位于目标 authority、目标测试进入 required manifest，动态 consumers 全部处置。
- **Commit**：`build(remediation): bind audit issues and repository inventory`。

### B02　Companion spec 和外部输入探测

- **Mode / depends / audit**：`EXTERNAL_GATE / B01 / P2-01`。
- **Allowed paths**：只写 `$R/inputs` 和 gate request；不改仓库。
- **实现**：解析现有 pinned `legal-math-modeling` commit；若本机没有 exact checkout，从批准的官方 remote 只读获取到外部目录；核对 commit/tree/license/required files。不能获得时返回 exit 21。
- **PASS**：spec commit/tree receipt 可验证；五项 shadow/differential test ID、fixture digest、oracle入口进入 receipt并能被后续 task 引用；fixture 预期值不得由 JC production implementation 生成；外部 spec 不可用时 exit 21，不得 skip；不再硬编码个人盘符。
- **无 commit**：外部 input receipt 进入 hash chain。

### W0-01　冻结 V4 object set 和状态矩阵

- **Mode / depends / audit**：`AUTO / B02 / P0-01..08, P1-02`。
- **Allowed paths**：`docs/contracts/**`、`tests/fixtures/v4_contract/**`、`remediation/v4/tasks.json`。
- **动作**：登记全部 request/source/evidence/fact/rule/IR/argument/backend/receipt/result/run/certificate/audit/MCP objects；冻结 execution/decision/review/completeness/certificate 的笛卡尔状态矩阵；所有正式对象 `additionalProperties=false`。
- **Gate**：runner 对 fixture 做字段闭包、状态可达性和非法组合枚举；任何 accepted formal 无 certificate、blocked 却 transport success、unknown 却 formal 必失败。
- **Commit**：`docs(contract): freeze V4 object and state matrix`。

### W0-02　冻结 canonicalization、time、numeric、limits 和平台

- **Mode / depends / audit**：`AUTO / W0-01 / P0-03, P1-01..03, P1-15`。
- **Allowed paths**：`docs/contracts/**`、`tests/fixtures/golden/**`、`remediation/v4/tasks.json`。
- **动作**：固定 `sha256:<hex>`、RFC 8785/I-JSON、safe integer、金额最小单位、比例 numerator/denominator、UTC instant 精度/区间；通过 property/DoS 基准提出 byte/depth/count/deadline/quota 限值。限值未被测试支持时不得随意填魔数。
- **Gate**：golden vectors 可由 Python/Node 读取并得到相同 bytes/digest；非法日期、offset、fractional edge、unsafe integer、float 均列为 negative fixtures。
- **Commit**：`docs(contract): freeze canonical identity and resource limits`。

### W0-03　人工 authority policy 和 observed import graph

- **Mode / depends / audit**：`AUTO / W0-01 / P0-08, P0-14, P1-07, P2-04`。
- **Allowed paths**：`docs/architecture/module-authority.json`、observed-graph emitter、authority validator/tests；旧两份 registry 此 task 只标记待删除，不提前删。
- **动作**：人工规定 `FORMAL_CORE|PUBLIC_ADAPTER|RUNTIME_OUTPUT|SOURCE_TOOL|EXPERIMENT_ONLY|CANDIDATE_ASSET|BUILD_ONLY|TEST_ONLY|REMOVE` 及允许入边、wheel/deployment属性。observed graph 只能验证，不得根据现状自动生成 policy 或删除结论。`FORMAL_CORE` 不得导入 source tool、experiment、candidate、network、UI、renderer 或 strategy；`RUNTIME_OUTPUT` 只能读取已独立验证的 bundle；后三类不得进入 production wheel。
- **Gate**：CodeGraph+AST+动态 import 对所有 Python path 100% 分类；每条实际边满足人工 policy；当前违规边形成 machine backlog，不得伪报 PASS；target graph 无第二 application/contract/certificate issuer。故意制造同名方法误边、函数内 import 和动态 plugin edge 时，validator 不得漏报或据此误删。
- **Commit**：`docs(architecture): define V4 authority policy and validate observed graph`。

### W0-04　测试分层和 required gate 清单

- **Mode / depends / audit**：`AUTO / W0-01..03 / P2-02, P2-03`。
- **Allowed paths**：`tests/**` 中只新增目录骨架、marker/config 和 test manifest；不先改生产代码。
- **动作**：建立 `contract/property/integration/differential/formal_e2e/security/storage_chaos/windows_security/mcp_protocol/packaging/dsh_formal`；登记 required tests；禁止 required module-level skip/xfail；把当前保护错误行为的测试列为 `REWRITE_AT_TASK`。自包含 V4 fixtures 和 pinned companion-spec differential 是两套 required 证据：前者保证日常确定性，后者防 same-bug oracle；`spec_shadow_harness.py` 可退出 runtime，但能力必须迁到 `tests/differential/**`。
- **Gate**：test manifest 覆盖全部审计 mutation；pytest collection 中 required skip=0；尚未实现的测试应明确 fail，而不是 skip。
- **Commit**：`test(v4): establish required production gate taxonomy`。

### W0-05　密码依赖、test trust root 和生产门禁

- **Mode / depends / audit**：`HUMAN_GATE + AUTO / W0-02 / P0-04..07, P1-20`。
- **Allowed paths**：decision record、test-only keys/fixtures、dependency proposal；批准响应明确覆盖时，允许改生产/测试/build 的最小 lock 和 `pyproject.toml` dependency metadata。
- **动作**：机器评估成熟 Ed25519 verifier 的 license、Python 3.11/3.12 和 Windows/Linux wheel、API、维护和 hash-lock 可行性；生成依赖变更请求。批准后以单独 task attempt 更新最小 exact hash locks，再提交公钥和 test-only 私钥 fixture；test key 带不可用于 production 的固定 scope。没有批准不得开始 W1-05，也不得临时 vendoring 密码实现。
- **Gate**：repository/wheel/日志 secret scan；test key 签名不能通过 production trust policy；生产私钥字段/样例为零。
- **Commit**：`build(trust): lock approved V4 verifier and isolate test trust`。W6-03 对最终全部 profiles 再做完整解析和对账。

### W0 总门禁

```powershell
py -3.12 -B tools/remediate_v4.py verify-wave W0
```

必须同时证明：44 项 issue map 完整、全 tracked path 有 disposition、target DAG 无环、合同/状态/limits/authority/test manifests 可机器解析、production 密钥为零。否则 W1 不 READY。

## 8. W1：合同、JCS、ArtifactResolver、TrustPolicy

### W1-01　唯一 canonical serialization 和 DigestV4

- **Depends / audit**：`W0-05 / P0-03, P1-01`。
- **Paths**：重写 `compiler_core/canonical_serialization.py`；新增 contract/property tests 和 RFC vectors。`jcs.py` 暂保留但不得被新代码引用，W5 删除。
- **动作**：采用已批准且经向量验证的 RFC 8785 实现；统一 DigestV4；拒绝 float、non-finite、unsafe integer、duplicate key；原始 source bytes 不做隐式 Unicode normalization。
- **Gate**：

```powershell
py -3.12 -B -m pytest tests/contract/test_jcs_v4.py tests/property/test_canonicalization.py -q -p no:cacheprovider --basetemp "$R/tmp/W1-01"
node tests/contract/jcs_node_oracle.mjs tests/fixtures/golden/jcs-v4-vectors.json
```

- **PASS**：Python/Node bytes 和 digest 逐向量一致；旧 `sha256-`、裸 hex、unsafe numeric 全拒绝。
- **Commit**：`fix(identity): unify V4 JCS and digest grammar`。

### W1-02　封闭 V4 contracts

- **Depends / audit**：`W1-01 / P1-02, P2-07`。
- **Paths**：把 `compiler_core/contracts.py` 改写为 V4；contract tests。现 `contracts_v4.py` 只作为迁移输入，W5 删除。
- **动作**：实现 W0 object set、typed unions、递归 limit validation、strict RFC3339、engine major=4、`__version__` public export contract；外部对象不能包含 gate/receipt/certificate/build identity。
- **Gate**：每个 object 正负 round-trip；字符串不得被拆成 refs；nested float、unknown object、非法日期和 V3 version 必失败；mutable Mapping 不能进入内部 context。
- **Commit**：`refactor(contract): make strict V4 models the sole Python contract`。

### W1-03　Schema、ToolSpec、capabilities 确定性发布

- **Depends / audit**：`W1-02 / P1-02, P1-14, P2-04`。
- **Paths**：`contracts.py`、`compiler_core/mcp.py::TOOL_SPECS`、一个小型 emitter、发布物 `schemas/jc-v4.schema.json` 和 `mcp_manifest.json`、differential/check tests。不得建立第二份 model、通用 codegen framework 或 runtime manifest loader。
- **动作**：typed contract 产生完整 `$defs`、limits、state enums；唯一显式 `TOOL_SPECS` 把四 tools 映射到这些类型及稳定 error。emitter 只序列化发布物；installed runtime 使用内置 typed codecs/ToolSpec，不读取仓库 manifest/path。capabilities schema 可派生，值必须从实际 runtime 动态构造。
- **Gate**：

```powershell
py -3.12 -B tools/remediate_v4.py generated --check
py -3.12 -B -m pytest tests/contract/test_python_schema_mcp_differential.py -q -p no:cacheprovider --basetemp "$R/tmp/W1-03"
```

- **PASS**：AST 恰有一个 `TOOL_SPECS`、`DEFAULT_MANIFEST`/dynamic manifest 零命中；同一 corpus 在 Python/JSON Schema/MCP codec 同判；临时生成物与 committed bytes相同；manifest tools 与真实 `tools/list` 相同；任一发布物 mutation 使 build gate 失败，但 installed runtime 不依赖仓库文件。
- **Commit**：`feat(contract): publish V4 schema and MCP manifest from typed contracts and sole ToolSpec`。

### W1-04　ContentRef 和 ArtifactResolver

- **Depends / audit**：`W1-03 / P0-04, P0-10, P1-15, P1-17`。
- **Paths**：仅以下 21 个 exact paths：本方案、`compiler_core/artifact_store.py`、`compiler_core/contracts.py`、`docs/architecture/module-authority.json`、`docs/contracts/V4_CANONICAL_TIME_NUMERIC_LIMITS.md`、`mcp_manifest.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`schemas/jc-v4.schema.json`、`tests/contract/test_contracts.py`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_v4_foundation_contract.py`、`tests/contract/v4-contract-vectors.json`、`tests/fixtures/golden/v4-artifact-page-probe.json`、`tests/fixtures/golden/v4-foundation-contract.json`、`tests/property/test_resolver_properties.py`、`tests/required-v4-tests.json`、`tests/security/test_artifact_resolver.py`、`tests/unit/test_remediation_run.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`。
- **动作**：只按 typed content/capability ref 取受控 bytes；先限制长度/type/scope，再从同一 bytes 复算 digest；same id/same digest 幂等，same id/different digest collision；formal resolver 禁止 path、网络、模糊搜索。`artifact_page_bytes` 仅约束 `ArtifactResolverV4.resolve_handle.length`，不声称限制整件摘要 CPU、驻留内容内存、`resolve_content` 整件返回或 MCP transport。
- **Gate**：绝对/相对逃逸、UNC、device、pipe、symlink/junction ref、oversize、wrong MIME、digest bit flip、scope reuse 全拒绝且零外部读取；有效 handle 在 default/hard page exact limit 返回精确 bytes，`limit+1` 返回 `ARTIFACT_PAGE_LIMIT`。P1-15 的完整生产资源预算保持 RED 到 `W5-CUTOVER`。
- **Commit**：`feat(trust): add bounded content-addressed artifact resolver`。

### W1-05　TrustPolicy、签名、撤销和角色

- **Depends / audit**：`W1-01, W1-04, W0-05 / P0-04..07`。
- **Paths**：仅以下 11 个 exact paths：本方案、`compiler_core/trust.py`、`docs/architecture/module-authority.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/fixtures/golden/v4-test-trust-policy.json`、`tests/required-v4-tests.json`、`tests/security/test_trust_policy.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`。
- **动作**：只以进程内 public-key registry 验证 key id、issuer、role、scope、artifact kind、subject、policy digest、issued/expiry、nonce/replay、revocation；source authenticity、legal approval、engineering approval、pack release、service certificate、build attestation 分 scope；runtime 不读取文件/网络/私钥。W1-05 只关闭同一 verifier 实例内的原子 replay，跨进程/重启后的持久 replay 由 W4-02..03 关闭。
- **Gate**：unknown/expired/revoked/wrong issuer/scope/kind/subject/role/policy/same-person separation violation/replay/bit flip 均失败；test root 对 production policy 失败；focused pytest 必须以 JUnit 绑定全部 trust cases，P0-05/06/07 保持 RED 到各自 closure task。
- **Commit**：`feat(trust): enforce signed scoped V4 trust policy`。

### W1-06　合同/信任综合攻击门禁

- **Depends / audit**：`W1-03..05 / P0-03..04, P1-01..04, P1-14..15, P2-03`。
- **Paths**：仅以下 8 个 exact paths：本方案、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_contracts.py`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_v4_legacy_rejection.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；生产修复回到责任 task，不在本 task 顺手改。
- **Gate**：Hypothesis differential、nested/depth bombs、cross-language JCS、path matrix、signature/revocation mutation；engine 3、V3 upgrade 和 V3 schema generation 三项错误正例改为预期拒绝。P1-03/P1-04 的 source 语义保持 RED 到 `W2-01`，P1-15 的完整生产资源预算保持 RED 到 `W5-CUTOVER`。
- **Commit**：`test(trust): close V4 contract and resolver attack surface`。

## 9. W2：来源、证据、事实、RuleV4 和 immutable pack

### W2-01　SourceSnapshot、time 和 SourcePath

- **Depends / audit**：`W1-06 / P0-04, P1-03, P1-04`。
- **Paths**：仅以下 11 个 exact paths：本方案、`compiler_core/source_service.py`、`docs/architecture/module-authority.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_source_service.py`、`tests/required-v4-tests.json`、`tests/security/test_source_service_attacks.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；不修改 V4 frozen contracts、resolver、trust 或旧 V2 caller-PASS 测试。
- **动作**：真实 raw/normalized bytes digest、authority、jurisdiction、issuer、promulgation/effective/expiry、locator、license/provenance、version graph；时间先解析 UTC instant；path 强制单 root、单 terminal、全节点可达、无环、edge order independent。
- **Gate**：fractional/offset boundary、invalid date、disconnected/multi-root/multi-terminal/orphan/permutation、wrong source bytes/signature 全部负例；合法 version chain 正例。
- **Commit**：`feat(source): verify signed bytes, time, locator, and connected paths`。

### W2-02　Evidence 和 FactAdmissionV4

- **Depends / audit**：`W2-01 / P0-02, P0-04`。
- **Paths**：仅以下 11 个 exact paths：本方案、`compiler_core/fact_admission.py`、`compiler_core/source_service.py`、`docs/architecture/module-authority.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_fact_admission.py`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_source_service.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；`test_required_test_manifest.py` 仅同步 runner report-version contract；`source_service.py` 及其 contract test 仅纠正 W2-01 暴露的 self-digest bundle 表示与 cache-time expiry，不扩展业务范围；不修改 frozen contracts、resolver、trust 或旧 fact admission 实现。
- **动作**：candidate fact 绑定 proposition/value/type；服务解析完整 canonical request，从 request 非回指字段派生 content-addressed `case-request-binding` projection，manifest、attestation 和 legal signature evidence 均绑定该 projection；attestation 先于完整 run 生成且不得悬空伪绑 run，最终 receipt 才绑定由 digest-body bytes 可解析的真实 `RunIdentityV4`；SourceBundle、EvidenceManifest、RunIdentity 均以 canonical digest-body bytes 对齐其 self digest，source cache hit 仍检查签名/策略有效期；服务验证 projection/manifest/attestation membership，并从已解析的 candidate、evidence manifest 和 scoped attestation 派生 source/evidence refs；source、interpretation、fact 三门由服务内部执行；最终 service receipt 由服务内部生成、使用真实签名并绑定完整 request_ref、case scope、nonce/replay policy。
- **Gate**：caller PASS、手造 receipt、伪造签名、同 ID 覆盖、cross-scope reuse、source/evidence mismatch、expired/revoked、UNKNOWN/DISPUTED/USER_ASSUMED 均不能成为正式 premise；同 scope、同内容 retry 幂等返回同一 receipt。
- **Commit**：`feat(fact): make admission evidence-bound and non-forgeable`。

### W2-03　RuleV4 和 signed PackManifestV4

- **Depends / audit**：`W2-01, W1-05 / P0-05, P1-07..09, P1-16`。
- **Paths**：仅以下 10 个 exact paths：本方案、`compiler_core/rule_packs.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_rule_packs.py`、`tests/required-v4-tests.json`、`tests/security/test_pack_attacks.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；不修改 frozen contracts、resolver、trust、source service、artifact store、domain config 或 CLI。
- **动作**：在保留后续切换所需 legacy reader 的同时，新增唯一 V4 `RulePackVerifierV4.verify(pack_ref, now)`；RuleV4/PackManifestV4 只从 canonical digest-body bytes 解析；promotion subject 断开 rule↔receipt 环，法律、工程、service promotion、build attestation、pack release 五类真实 Ed25519 签名逐层绑定且职责分离；pack signature 单向引用 manifest，manifest receipt 闭合集合由 promotion receipts 与唯一 build attestation 组成；verifier 解析真实 SourceSnapshot、typed rule refs、closed domain config、coverage/verification receipts，并精确绑定 engine/build/source-tree/schema/trust identity。`VERIFIED_ACTIVE` 仅由该 verifier 内部签发，API 不接受 caller `active`、`eligible`、`integrity_valid`、`PASS` 或 receipt。
- **Gate**：candidate、development/test key 用于 production、empty、unsigned、wrong exact engine API、missing/corrupt/unknown config、wrong build/tree/schema、未验证 source、locator/structure mismatch、少签/伪签/过期/撤销/wrong scope、同人多角色、promotion replay、manifest/signature byte replacement 均 blocked；空 formal pack 不产生 verified handle；同 pack retry 幂等。W2-03 只建立 verified snapshot 权威；CLI/lookup 转述该状态和 global domain fallback 清除仍分别由 W5-02C/W5-03 与 W4-05 完成，不在本 task 伪报跨入口闭环。
- **Commit**：`feat(pack): verify immutable signed RuleV4 snapshots`。

### W2-04　消除 pack TOCTOU

- **Depends / audit**：`W2-03, W1-04 / P0-05, P0-11, P1-08, P1-10`。
- **Paths**：仅以下 11 个 exact paths：本方案、`compiler_core/artifact_store.py`、`compiler_core/rule_packs.py`、`compiler_core/source_service.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/security/test_pack_toctou.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；`test_rule_packs.py`、`test_source_service.py`、`test_pack_attacks.py`、artifact resolver security/property tests 只作为不修改的回归 oracle；不修改 frozen contracts、trust、domain config、CLI 或 legacy reader。
- **动作**：`ArtifactResolverV4` 继续只接受已登记 immutable bytes，不获得 filesystem/path authority；进入一次 pack verify 时，私有 ContextVar 固定 frozen record/bytes 映射，manifest、RuleV4、SourceSnapshot、config、receipt 和签名均从同一进程内 snapshot 解析，退出或异常后释放；同时复制完整 trust state，并用绑定该 trust snapshot 的 fresh SourceService 完成整图验签，fresh service 固定 live `source_id → snapshot_ref` 唯一性账本但不复用已验证 bytes cache；既有完整 admission 的 exact source 仍重新校验 bytes 与当前 trust，但不把其已消费的同一真实性签名当成新 nonce，live trust 的瞬时 A→B→A 不得影响结果；live SourceService 用一把 admission `RLock` 串行化 public source writer 和 applicability reader，pack 按 `source → trust` 固定锁序提交，验签新消费的 nonce 和本次完整 source admission state 只在整图验证及提交后 trust 复核成功时生效，任何异常完整回滚 live state 与本次新增签名 cache，同一成功 pack 重试仍保持幂等；每个 verifier 用一把进程内 lock 覆盖 snapshot 验证、verified-handle identity cache 与 closure issuance，使并发首次加载只返回同一 handle。runner 恢复 COMPLETED receipt 时重建 exact argv/results/JUnit，并再次核对本 task 的 11-path digest 与专属 assertions；`runner-state-artifact-recovery` 只接受完整验证的 W1-06 recovery chain。W4-02 再实现 durable/cross-process storage abstraction、content-addressed staging、no-follow/file-id/stat、fsync/atomic publish、reparse/symlink 拒绝及 stale recovery；本 task 不伪报这些尚无 filesystem authority 的能力。
- **Gate**：manifest/rule/source/config 在完整验证期间替换并恢复原记录，仍只返回同一已验证 snapshot；并发首次加载返回同一 verifier-issued handle；成功调用提交 nonce 与完整 source admission cache 且同包重试不重复消费，既有合法 source admission 不触发 replay；public source admission 的 source-id 检查/提交串行化，applicability reader 不得观察尚未通过最终 trust 复核的暂存状态，ID 冲突失败撤销本次 nonce，既有或验证中重绑的 `source_id` 不得被覆盖，预先或验证中已消费的其他 nonce 均阻止签发且失败重试不受 cache 污染；live trust key/policy 在验签期变更、A→B→A 或提交临界点变化均不得激活 handle且不得留下部分 live state；晚登记内容在活动 snapshot 内不可见；外部文件替换不能重绑已登记 bytes；删空 commands/reports 或伪造 recovery assertion 的可重哈希 receipt 不得恢复 COMPLETED；零新 artifact/run/certificate；source service contract、source cache key rotation、W2-03 pack attacks 及 W1-04 resolver 合同全部回归，零 skip/xfail。
- **Commit**：`fix(pack): execute only from verified immutable snapshots`。

### W2-05　Synthetic signed pack builder

- **Depends / audit**：`W2-02, W2-04 / P0-02, P0-05, P1-08`。
- **Paths**：仅以下 17 个 exact paths：`.gitignore`、本方案、`compiler_core/rule_packs.py`、`compiler_core/source_service.py`、`compiler_core/trust.py`、`remediation/v4/file-disposition.json`、`remediation/v4/issue-map.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_synthetic_pack.py`、`tests/fixtures/keys/v4-synthetic-trust.json`、`tests/fixtures/packs/synthetic/signed-pack.json`、`tests/required-v4-tests.json`、`tests/security/test_trust_policy.py`、`tools/build_file_disposition.py`、`tools/build_synthetic_pack.py`、`tools/remediate_v4.py`；不建立 builder protocol、registry 或 interface，三个 runtime 修改只收紧既有 pack/source/trust 边界，public API 不变。
- **动作**：外部 pinned test context 独立提供 trust policy、六个互异公钥及 expected runtime identity；pack fixture 只保存 untrusted artifact graph、formal/candidate roots 与后续 case vectors，不能自行提交 trust root 或 expected build identity。helper 从 W0-05 已批准的唯一 test-only master key 以固定 HKDF role domain 派生六个职责分离 key，构建 canonical fixture但不输出任何私钥。formal pack 通过 public `ArtifactResolverV4 → SourceServiceV4 → RulePackVerifierV4.verify` 装载；exception/priority/permission 使用现有 typed relation 字段，temporal 明确区间；missing/disputed 仅作为引用同一 required `fact_key` 的 `ABSENT/DISPUTED → BLOCKED` 后续场景材料，不冒充已准入 formal premise 或 W4-07 正式结果。candidate 的 build/release envelope 必须先经 public trust crypto 验证，但缺少 promotion receipt 仍不可激活。source authenticity 必须不晚于 rule reviews，否则精确 `PACK_REVIEW_TIME`；review→promotion→build→release 的既有时序继续传递闭合。`TrustVerifierV4` 拒绝一个 public key 的多 key-id/principal 别名，阻断职责分离、replay 与 revocation 身份漂白；`SourceServiceV4` 仅在 test environment 接受 `synthetic_test_only` authority tier，且 cached admission/bundle reader 均重检当前 environment，避免虚构真实法源。
- **Gate**：两个独立 Python 进程 build 与已提交 fixture bytes 完全相同；fixture scope 精确为 `test-only`，artifact 两 root 可达闭包无 orphan，decoded artifacts 不含 master/派生私钥，独立 context 六个 public key/principal 均唯一且全部 `production_allowed=false`；test policy 下 public pack verify 成功且 same verifier reverify 返回同一 verifier-issued handle，测试不得导入/直接构造 `VerifiedRulePackV4` 或使用 `object.__new__`；production-allowed keys 仍不能放行 synthetic source tier，cached source 也按当前 environment 重检，production trust 精确拒绝 test release key；同 public key 别名在 verifier 初始化期精确拒绝 `TRUST_KEY_CONFIG`；candidate build/release 经 public crypto 验证后仍精确拒绝 `PACK_PROMOTION_REQUIRED`，source/review/promotion/build/release 任一倒序分别精确拒绝 `PACK_REVIEW_TIME`、`PACK_PROMOTION_TIME`、`PACK_BUILD_TIME`、`PACK_RELEASE_TIME`；实际 wheel 中无 `tools/`、`tests/`、fixture/context 或私钥材料。当前 handle 仅是一次 verify(now) 的 point-in-time proof，不是动态 readiness cache；W4-05 必须在每次请求按 current CanonicalTimeV4 重验，失败 retry 不得吊销既有点时证明。P0-02 的 Application formal result/offline replay 仍保持 RED 到 `W4-07/W8-06`。runner 绑定 exact pytest JUnit、fixture/context digests、17 个 committed path digests 与 attempt receipt chain。
- **Commit**：`test(pack): add reproducible signed synthetic V4 pack`。

### W2-06　Source→Fact→Pack 纵向门禁

- **Depends / audit**：`W2-01..05 / P0-02, P0-04..05, P1-03..04, P1-07..09, P1-16, P2-03`。
- **Paths**：仅以下 12 个 exact paths：本方案、`compiler_core/fact_admission.py`、`compiler_core/source_service.py`、`compiler_core/trust.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/integration/test_trust_chain.py`、`tests/required-v4-tests.json`、`tests/security/test_trust_chain_attacks.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；不修改 signed pack fixture、external trust context、builder、issue map、旧 unit tests、Application、certificate 或 audit bundle。
- **动作**：integration harness 从 W2-05 已提交的 pack/source fixture bytes 与独立 trust context 开始，只把外部 request/evidence/fact canonical bytes 登记到同一 `ArtifactResolverV4`，按 `SourceServiceV4 → FactAdmissionServiceV4 → RulePackVerifierV4` 且 fact 先、pack 后执行，真实覆盖 preadmitted-source/no-replay 衔接；request/run 的 pack ref、admitted fact 的 source/proposition 与 verifier-issued loaded `RuleV4` 的 source/premise 必须逐项相等。`TrustVerifierV4` 提供仅供内部 cache revalidation 的 replay-isolated fresh copy；Source cache hit 必须重读 exact snapshot/raw/normalized/provenance/signature bytes 并重新验签，Fact legal/receipt cache hit 必须分别重新验 legal/service signature，same-service 合法 retry 不重复消费 live nonce，但 key rotation、nonce revocation 与 environment change 立即 fail closed。六个 P2-03 replacement selectors 原名落入 integration suite，旧 wrong-behavior inventory 保留到 W5-CUTOVER；`V4-P2-03-DERIVED-TRUST` 仍保持 RED 到 W5-01。
- **Gate**：从真实 fixture bytes 到 signed fact receipt 与 loaded RuleV4 的 6 个纵向正例全过；source/fact/pack signature bit flip，source/legal/service/release 的 post-cache key rotation 与 nonce revocation，fresh service replay，same-service idempotent retry，test→production 环境切换和 candidate activation attacks 全杀；candidate 可发现但精确 `PACK_PROMOTION_REQUIRED`，上游失败不留下 fact receipt 或 verified pack handle。runner 绑定 exact integration+security+governance JUnit、12 个 committed path digests、attempt receipt chain 与专属 assertions，零 skip/xfail。这里仅证明同一 request/source/trust 下 signed fact receipt 与 verifier-issued RuleV4 的组合链；Fact service 尚不消费 verified pack handle，Application formal result、certificate、bundle 与 offline replay 继续保持 RED 到 W4-05/W4-07/W8-06，不得据此宣称 P0-02 完整关闭。
- **Commit**：`test(admission): close source fact and pack trust chain`。

## 10. W3：无损 IR、argumentation、真实 backend、独立 checker

### W3-01　RuleV4→LegalSpecV4→LegalIVLV4 信息守恒

- **Depends / audit**：`W2-06 / P1-05`。
- **Paths**：仅以下 12 个 exact paths：本方案、`compiler_core/legal_ir.py`、`docs/architecture/module-authority.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_legal_ir.py`、`tests/contract/test_required_test_manifest.py`、`tests/property/test_ir_properties.py`、`tests/required-v4-tests.json`、`tests/semantic_mutation/test_ir_mutation.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`。`compiler_core/legal_spec_ivl.py` 与 `tests/unit/test_legal_spec_ivl.py` 本 task 只作为旧实现/回归输入，不修改、不删除；其 `REWRITE-SHARED-IR-ORACLE` replacement selector 由 `W3-05` 在同一测试文件内声明，旧 oracle 到 W5-CUTOVER 再退出。
- **动作**：新增唯一 `legal_ir.py` lowering authority；每个 `RuleV4` 语义字段必须 `preserve|lower|explicitly_unsupported`，formal 路径不允许 silent loss/default。两跳 translation receipt 从 before/after canonical bytes 与 artifact refs 自动生成，interpretation choice 必须绑定 approval refs；P1-05 mutation 从 `RED_AT_TASK` 转为 `ACTIVE_REQUIRED`。runner 仅执行 `verify-wave W3-01`，随后以外部 JUnit 绑定 contract、property、semantic mutation、旧 IVL unit 与 required-manifest governance 五个 exact pytest 文件。
- **Gate**：逐字段 mutation 覆盖 authority/source locator/terms/interpretation/modality/temporal；删除或变更任一字段必须改变 receipt 或 fail closed。reference oracle 的独立 projection 不调用 production lowering，测试零 skip/xfail；module authority 将 `legal_ir.py` 精确列为 `FORMAL_CORE`，file disposition 可重现。runner 绑定 exact JUnit case identity、12 个 committed path digests、attempt 1→2 receipt chain 与 `w3-01-exact-lossless-ir-reports`、`w3-01-exact-committed-scope` 两个专属 assertions；本 task 只关闭 P1-05 的字段守恒部分，独立 oracle replacement 与 critical survivor 全杀继续留给 `W3-05`。
- **Commit**：`feat(ir): enforce loss-accounted V4 lowering`。

### W3-02　ArgumentationV4

- **Depends / audit**：`W3-01 / P1-06`。
- **Paths**：仅以下 10 个 exact paths：本方案、`compiler_core/argumentation.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_argumentation.py`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/semantic_mutation/test_argumentation_mutation.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`。`compiler_core/argumentation_v2.py`、既有 grounded/V2/spec-shadow tests 仅作不修改回归输入，待 W5 删除或切断；不修改 frozen contracts、module authority、Application、DecisionStatus 或 issue map。
- **动作**：以 B02 pinned companion receipt/intake/differential 为受保护语义边界：active priority 只新增 `preferred/winner → defeated/loser` 的 typed `priority_defeat`，不发明 suppression；exception/rebuttal/undercut 均作为保留类型的有向 Dung edge，只有 exception 生成 exception resolution。新增 canonical graph/evaluation envelope，permission `holds|does_not_hold|disputed` 只观察相关 claim 的全部 IN/OUT/UNDEC labels，不生成也不决定 slice `DecisionStatus`；graph state 从 labels 推导，claim→arguments 保存全部多值 witnesses。移除 caller-controlled 快慢路，统一复用一个 grounded oracle；P1-06 mutation 从 `RED_AT_TASK` 转为 `ACTIVE_REQUIRED`。
- **Gate**：self/mutual/cycle/UNDEC/priority reversal/permission conflict/duplicate claim/disconnected graph/edge collection permutation mutations 全杀；priority endpoint reversal 必须改变结果，但 collection 重排必须 canonical/result 不变；UNDEC 不 accepted，priority cycle 明确 `cycle_blocked`。外部 JUnit 精确绑定新 contract/mutation、既有 grounded/V2、B02 spec-shadow 与 required-manifest governance 六个文件，零 skip/xfail；runner 绑定 exact case identity、10 个 committed path digests、attempt 1→2 receipt chain 与 `w3-02-exact-argumentation-reports`、`w3-02-exact-committed-scope` 两个专属 assertions。P1-06 仍保持 registered，独立 checker/reference replacement 与 critical survivor 全杀继续留给 `W3-04/W3-05`。
- **Commit**：`fix(argument): implement priority permission and complete witness semantics`。

### W3-03　Certified backend invocation

- **Depends / audit**：`W3-01..02 / P0-06`。
- **Paths**：仅以下 21 个 exact paths：本方案、`compiler_core/backend_router.py`、`compiler_core/backends/__init__.py`、`compiler_core/contracts.py`、`compiler_core/legal_ir.py`、`docs/architecture/module-authority.json`、`mcp_manifest.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`schemas/jc-v4.schema.json`、`tests/contract/test_backend_router.py`、`tests/contract/test_contracts.py`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_v4_foundation_contract.py`、`tests/contract/v4-contract-vectors.json`、`tests/fixtures/golden/v4-backend-provider-probe.json`、`tests/fixtures/golden/v4-foundation-contract.json`、`tests/required-v4-tests.json`、`tests/security/test_backend_attacks.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`。未认证 SMT/ASP 留在 build/test 外部面，不进入 production provider registry。
- **动作**：router 只接受当前 `LegalIRCompilerV4` 签发并按 live pack/trust 重验的 compilation，以及 `FactAdmissionServiceV4` 验证的同一 run、同一 `case_scope` fact admission receipts；`decision_time` 只从该 run 的 canonical `CaseRequestV4` 派生，public execute 不接受 caller override。canonical problem 对 clause/modality/effective half-open interval、premise/conclusion、relation、constraint ref/owner/target 使用封闭投影；Horn 仅允许 `CONSTITUTIVE` 结论进入事实 least-fixpoint，deontic 规则只输出 typed applicable norms，实际 fired refs 与显式 false/missing 分离；AAF 先以 admitted/constitutively-derived facts 和有效期确定 arguments/conditional edges，priority 绑定真实条件证据，permission 仅认证 `PERMISSION → PROHIBITION` 且双方 conclusion `fact_key` 与 `permits` 相同的 exception，空 applicable set 返回 canonical empty grounded result；exact 只计算 applicable clause，并保留每个约束的 ref/owner/target。现有 signed synthetic permission fixture 指向 `OBLIGATION` 且无三方同一 `fact_key`，因此 AAF 必须诚实返回 `UNSUPPORTED_SEMANTICS`，不得伪装三 provider 全 completed。每次调用使用可 kill 的 `spawn` 子进程，bounded canonical pipe 回传子进程自行测得的 runtime identity，deadline/cancel 覆盖启动、执行、传输和 decode 后检；invocation/receipt 绑定 canonical problem、limits、seed、provider version、Python binary、provider package/build inputs、exit、result/proof digest，execute/replay 共用 exact signature evidence-shape verifier，replay 从已登记 exact input 重跑并比较语义 bytes。
- **Gate**：compiler/fact bare copy、cross-run/cross-case-scope、caller time/features/fake receipt、未知或错属组件字段、休眠坏 relation、规范结论污染事实闭包、虚假 fired ref、真假冲突、规则有效期 before/start/end/after、AAF 条件 absent/false/true、permission 错 modality/claim、duplicate relation/constraint ref、constraint owner/target 漂移、provider 未调用、wrong signer/version/input/output/proof/runtime identity、oversize/post-deadline pipe、timeout/cancel/crash/unknown 均不能形成 completed execution；真实 timeout/cancel/oversize 后不得残留活子进程。local Windows spawn probe 必须执行每 provider 3 次 warmup + 25 次 measurement；本轮 75/75 completed、最大 `993611800 ns`，据此冻结 solver default `2500 ms`、hard max `10000 ms`。同时冻结当前 foundation/Schema/MCP publication、exact JUnit case identity、21 个 committed result-path digests，并由 `w3-03-exact-backend-reports`、`w3-03-exact-provider-publications`、`w3-03-exact-committed-scope` 三个专属 assertions 重建 receipt。W3-03 的 solver receipt 只证明 provider 确已执行及其结果绑定，不产生 `formal`/`DecisionStatus`；独立 checker/formal admission 属 W3-04，包含 backend invocation 的封闭 run identity 生命周期属 W4-01，P0-06 在两者完成前保持 registered。
- **Commit**：`feat(backend): invoke and attest certified V4 providers`。

### W3-04　Independent checker

- **Depends / audit**：`W3-03 / P0-06, P1-05..06`。P0-07 的 certificate issuer/verifier closure 仍只属于 W4-03..04，本 task 不冒充 certificate closure。
- **Paths**：仅以下 11 个 exact paths：本方案、`compiler_core/independent_checker.py`、`docs/architecture/module-authority.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_independent_checker.py`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/security/test_checker_independence.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`。不修改 production provider、lowering、argumentation、Application、DecisionStatus、certificate、Schema 或 MCP publication。
- **动作**：新增唯一 `IndependentCheckerV4`，caller 只提交 run identity ref 与 solver receipt ref，不能提交 PASS、graph、result、witness 或 checker build。checker 在 resolver 的 immutable snapshot 中沿 receipt→invocation→canonical problem/result/proof refs 读取字节，独立重建 Rule→Spec→IVL 零损投影、signed pack 中的 rule/source 归属、同 run/request/case-scope fact admission、Horn least-fixpoint 与 deontic applicability、typed AAF graph/grounded labels/witness/claim projection/permission/exception/priority cycle、exact integer/rational/Gregorian 结果；不得导入或调用 `backend_router`、`backends`、`legal_ir`、`argumentation`、`FactAdmissionServiceV4` 或 `RulePackVerifierV4` 的 production 算法或内部 PASS。只复用 frozen contracts、canonical bytes、bounded resolver 和 trust crypto，输出 build/profile/input/output/exact witnesses 全绑定且带可信签名的 `CheckerReceiptV4`；checker receipt 不产生 `DecisionStatus` 或 certificate。
- **Gate**：真实 W3-03 Horn execution 可签发并重验 checker receipt；direct Horn/AAF/empty-AAF/exact vectors 的 result 与 proof 必须逐字等于独立重算。任一 production result/proof/translation/fact/pack/run/subject/build/graph/label/claim projection/permission/constraint mutation、少或多 witness、caller PASS、cross-run/cross-result、wrong signer 或 signature evidence 均 fail closed。AST/import 与 monkeypatch same-bug gates 证明 checker 不调用 production lowering/provider/grounded oracle；外部 JUnit 精确绑定新 contract/security、既有 IR/argumentation mutation、legacy checker 与 required-manifest governance 六条 lane，零 skip/xfail。runner 绑定 exact case identity、11 个 committed path digests、attempt 1→2 receipt chain，以及 `w3-04-exact-checker-reports`、`w3-04-exact-independence`、`w3-04-exact-committed-scope` 三个专属 assertions。
- **Commit**：`feat(checker): add independent V4 semantic verification`。

### W3-05　Semantic mutation gate

- **Depends / audit**：`W3-01..04 / P0-06, P1-05..07`。P1-07 在本 task 只覆盖 signed-pack `domain_bindings` 下层投影；runtime/Application closure 仍唯一属于 `W4-05`，其 required selector 保持 `RED_AT_TASK`。
- **Paths**：仅以下 11 个 exact paths：本方案、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/semantic_mutation/critical-v4-mutations.json`、`tests/semantic_mutation/test_argumentation_mutation.py`、`tests/semantic_mutation/test_domain_provider_mutation.py`、`tests/semantic_mutation/test_ir_mutation.py`、`tests/unit/test_semantic_mutation_manifest.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；不修改生产算法，survivor 回 `repair_task` 修复。
- **动作**：冻结只声明要求、不预写 KILLED 结果的六项 critical ledger；IR lowering 与 priority/UNDEC 使用测试侧独立 oracle，witness 要求完整多值 projection，namespace/domain 从 signed config canonical bytes 独立投影，provider gate 以真实 invocation probe 加 independent checker 拒绝 caller fake receipt。修正原任务无 pytest、漏绑 P0-06、glob allowlist 与 P1-07 closure 混淆四项 plan drift。
- **Gate**：IR loss 六个参数 mutation 加其余五项恰好 11 个 critical cases 全过，独立性/ledger 与 required-manifest 合同测试零 skip/xfail；`survivors_allowed=0` 且禁止总体百分比覆盖任一 survivor。runner 递归复验 W3-01..04，绑定 exact JUnit case identity、11 个 committed result-path digests、attempt 1→2 receipt chain，以及 `w3-05-exact-critical-mutation-reports`、`w3-05-zero-critical-survivors`、`w3-05-exact-committed-scope` 三个专属 assertions。
- **Commit**：`test(semantics): enforce critical V4 mutation ledger`。

## 11. W4：RunIdentity、Storage、AuditBundle、Certificate、ApplicationV4

### W4-01　RunIdentityV4 和封闭状态矩阵

- **Depends / audit**：`W3-05 / P0-12, P1-13`。
- **Paths**：仅以下 19 个 exact allowlist paths：本方案、`compiler_core/backend_router.py`、`compiler_core/contracts.py`、`compiler_core/independent_checker.py`、`mcp_manifest.json`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`schemas/jc-v4.schema.json`、`tests/contract/test_backend_router.py`、`tests/contract/test_fact_admission.py`、`tests/contract/test_required_test_manifest.py`、`tests/contract/test_run_identity.py`、`tests/contract/v4-contract-vectors.json`、`tests/integration/test_trust_chain.py`、`tests/required-v4-tests.json`、`tests/security/test_backend_attacks.py`、`tests/security/test_checker_independence.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；不修改 `application.py`、storage 或 audit bundle，不提前施工 W4-02..05。
- **动作**：`RunIdentityV4.build` 是本 task 唯一 production constructor：只接收 canonical `CaseRequestV4`、匹配 kind/digest 的 request content ref 与 exact typed 可信构建/运行材料，并从 request 镜像 source bundle、evidence manifest、fact attestation 与 rule pack refs，调用者不能另行注入这些身份轴。run 绑定 engine version、source commit/tree、build/wheel/package、Schema、ToolSpec、locks、runtime config、algorithm、trust、storage 与 pre-execution `backend_profile_digest`；backend profile 由固定 provider registry/version、直接驱动实际选择的声明式 route table、deadline、seed，以及当前 Python binary/provider package/build inputs canonical 投影。原 `backend_invocation_ref` 会形成 `run → invocation → problem → run` 的 content-addressed 环，故仅保留在 post-run `RuntimeProfileV4`/solver receipt，不进入 pre-execution run；router 执行前核对当前 profile 与 route table，independent checker 从 invocation capability 独立重建同一 profile 并验证 provider eligibility，不导入 router/provider。execution/decision/certificate 继续正交，observability 不入 semantic identity。
- **Gate**：19 个身份轴任一变化均改变 run；同 exact inputs 跨两个 Python 进程相同；错误 request ref、非 typed runtime material、额外 observability 字段和非法状态/输入组合不可构造；provider registry/version、Python/provider bytes、route table/实际选择、deadline、seed 漂移在 provider 执行前失败；即使 monkeypatch router 使错误 profile 或不匹配的 self-consistent provider capability 获得真实 solver receipt，independent checker 仍须拒绝。Schema/ToolSpec 生成物 byte-check、既有 contract/fact/trust/backend/checker 全回归，focused pytest 以单一 JUnit 绑定 exact case identity且零 skip/xfail。P0-12 的 old COMPLETE bundle/new result collision 属于 W4-03 的磁盘 bundle writer/verify，selector 移交 W4-03 并保持 RED；P1-13 的 V3/V4 namespace 隔离仍归 W4-02 并保持 RED，不以本 task 伪报关闭。runner 绑定 `w4-01-exact-run-identity-reports`、`w4-01-complete-identity-state-contract`、`w4-01-exact-committed-scope` 三项专属 assertions；19-path allowlist 中 byte-stable 的 `mcp_manifest.json` 以 publication digest 绑定，其余 18 个实际变更 path 各有 committed result digest。
- **Commit**：`feat(identity): bind complete V4 execution identity`。

### W4-02　V4 storage abstraction

- **Depends / audit**：`W4-01, W2-04 / P0-11..13, P1-10..13`。
- **Paths**：仅以下 14 个 exact allowlist paths：本方案、`compiler_core/artifact_store.py`、`compiler_core/storage.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/storage_chaos/test_generation_isolation.py`、`tests/storage_chaos/test_multiprocess_recovery.py`、`tests/storage_chaos/test_power_loss.py`、`tests/windows_security/test_dacl.py`、`tests/windows_security/test_reparse_escape.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；`artifact_store.py` 仅作 byte-stable W2-04 回归边界，`ArtifactResolverV4` 继续没有 filesystem/path authority，不修改 W4-03 audit bundle。
- **动作**：新增唯一 `V4TransactionStore`，在固定 `jc-v4-state` namespace 内使用跨进程单 writer lock、唯一 staging、PID lease、SHA-256 content-addressed final、collision 检查、orphan quarantine/recovery 和 byte quota；POSIX 使用 exclusive hard-link publish、file fsync、target/staging/parent directory fsync，Windows 使用 no-follow `CreateFileW`、`FlushFileBuffers` 对应的 `os.fsync`、`MoveFileExW(MOVEFILE_WRITE_THROUGH)` 且禁止覆盖；每次操作复核 state-root containment、root/locks/staging/objects/quarantine file id，拒绝 symlink/junction/reparse 与目录身份替换；POSIX owner/mode、Windows owner/DACL 只允许当前 service SID 与 SYSTEM，验证能力不可用时 fail closed 为 `STORAGE_CAPABILITY_BLOCKED`。
- **Gate**：真实 2/10/100 process colliding writers、五个逐写点 `os._exit`、残留恢复、quota/collision、disk-full、read-only、root/subtree symlink/junction swap、plain directory identity swap、Everyone ACE、owner change/验证不可用；重启后 only-complete-or-absent，V3 sibling bytes 不读不写，全部 required selector 转 `ACTIVE_REQUIRED` 且零 skip/xfail。P0-12 的 old COMPLETE bundle/new result collision 仍唯一留给 W4-03 并保持 RED；P0-11 的 W2-04 immutable snapshot selector作为 byte-stable 回归。runner 绑定 `w4-02-exact-storage-reports`、`w4-02-durable-isolated-storage-contract`、`w4-02-exact-committed-scope` 三项专属 assertions；14-path allowlist 中 byte-stable 的 `artifact_store.py` 以冻结 digest 绑定，其余 13 个实际变更 path 各有 committed result digest。
- **Commit**：`feat(storage): add durable isolated V4 transaction store`。

### W4-03　AuditBundleV4 writer、verify、replay

- **Depends / audit**：`W4-02, W3-04 / P0-07, P0-12, P1-10..13`。
- **Allowed paths**：精确 14 项：`20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md`、`compiler_core/artifact_store.py`、`compiler_core/audit_bundle.py`、`compiler_core/independent_checker.py`、`compiler_core/storage.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_audit_bundle.py`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/security/test_audit_bundle_attacks.py`、`tests/storage_chaos/test_audit_bundle_recovery.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；其中 `artifact_store.py`、`independent_checker.py`、`storage.py` 必须 byte-stable，仅以 frozen digest 绑定，实际 changed paths 恰为其余 11 项。
- **固定文件集**：`input.json`、`source-index.json`、`fact-admission.json`、`rule-pack.json`、translation/backend/checker receipts、`events.jsonl`、`graph.json`、`result.json`、`certificate.json`、`manifest.json`、`checksums.sha256`、`COMPLETE`。
- **动作**：先算不含 certificate/full manifest/checksums/COMPLETE 的 core digest，certificate 绑定 core；full manifest 再绑定 certificate 和所有 files；本地 full verify 成功后 COMPLETE-last。已有 COMPLETE 只返回磁盘验证解码对象；差异为 `RUN_ID_COLLISION`。
- **动作**：`verify_run` 必须从 COMPLETE 独立重算 manifest、certificate、receipt DAG、签名/撤销、build 和全部摘要，不信 evaluate 返回的 status；run ref 是 opaque capability。`read_artifact` handle 绑定 run/artifact/scope/expiry/max-bytes，每块返回 offset/length/next/chunk digest/content type，不返回宿主路径。
- **Gate**：少/多/替换/重排/bit flip 任一文件，old digest+new result、提前 COMPLETE、当前代码重放旧 build、V3 bundle、跨 run/过期/越界 handle 均失败；offline replay 只从封存 runtime/pack/trust/config/provider/build 材料执行，禁网、禁当前环境 fallback、禁写原 run。真实 receipt 必须由 byte-stable `IndependentCheckerV4` 从封存 bytes 重算，caller gate/status/digest 不得触发证书签发；两处中断点均只允许 complete-or-absent 并在续写前 quarantine。runner 绑定 `w4-03-exact-audit-reports`、`w4-03-independent-atomic-bundle-contract`、`w4-03-exact-committed-scope` 三项专属 assertions。
- **Commit**：`feat(audit): write verify and replay atomic V4 bundles`。

### W4-04　CertificateV4 issuer/verifier

- **Depends / audit**：`W4-03, W1-05 / P0-07..08`。
- **Paths**：精确 14 项：本方案、`compiler_core/audit_bundle.py`、`compiler_core/certificates.py`、`compiler_core/contracts.py`、`compiler_core/independent_checker.py`、`compiler_core/trust.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_certificates.py`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/security/test_certificate_attacks.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；其中 `contracts.py`、`independent_checker.py`、`trust.py` 必须 byte-stable，仅绑定 frozen digest，实际 changed paths 恰为其余 11 项。
- **动作**：issuer 只接收 AuditBundle 在完成 immutable core 与独立 checker 验证后封装的内部 context；从 bundle core 重算 source/fact/rule/translation/backend/checker/proof receipt DAG、pack/trust/revocation、run/build、status/completeness/taint gates；formal/conflict/none typed union；内部 certificate body 完全确定，对外 Ed25519 service signature 单独分层。`audit_bundle.verify_run` 必须调用同一 certificate verifier，不能只验外层签名或相信 certificate 自报 refs。
- **Gate**：caller gate map、fake/unknown issuer、wrong subject/run/build、receipt missing/extra/replay、bundle mismatch、revoked key 全失败；无公开 gate-map/digest API 可制造 issued certificate；formal/conflict/none 正向链、两种不同合法 signature nonce 下相同内部 certificate digest、W4-03 bundle 回归与 required-manifest governance 全绿。runner 绑定 `w4-04-exact-certificate-reports`、`w4-04-bundle-bound-certificate-contract`、`w4-04-exact-committed-scope` 三项专属 assertions。
- **Commit**：`feat(certificate): issue only bundle-bound verified V4 certificates`。

### W4-05　ApplicationV4 唯一编排

- **Depends / audit**：`W4-04 / P0-01..08, P1-07, P1-16`。
- **Paths**：精确 11 项：本方案、`compiler_core/application.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_application.py`、`tests/contract/test_required_test_manifest.py`、`tests/formal_e2e/test_single_chain.py`、`tests/required-v4-tests.json`、`tests/security/test_application_attacks.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；实际 changed paths 恰为全部 11 项。
- **动作**：严格顺序 resolver→trust→source/evidence→fact→pack→IR→backend→checker→argument→result→audit core→certificate→final bundle；每次请求以 current `CanonicalTimeV4` 调用 pack verifier，旧 handle 只作点时证据而不作 readiness cache；domain/config 只来自 signed pack bytes；所有 early exit 也有 typed result 和 bundle；不调用 advisory certificate/evaluator。P0-01 在本 task 关闭 Application core 内的 V3 兼容面，三个 public entrypoint 的唯一 sink 仍由 `W5-CUTOVER` 关闭，不在这里伪报跨入口完成。
- **Gate**：17 个 application/formal/attack/governance focused cases 全绿且 JUnit case identity 冻结；synthetic pack 全状态矩阵；pack policy/signature 到期或撤销后的当前请求必须重验失败且不得消费旧 handle；signed jurisdiction/governing law 不匹配时 BLOCKED、无 global fallback；missing/review/hypothetical/conflict/unknown/blocked/error 不签 formal；accepted formal 必有可 verify/replay certificate；阶段故障不 fallback。runner 绑定 `w4-05-exact-application-reports`、`w4-05-single-formal-spine-contract`、`w4-05-exact-committed-scope` 三项专属 assertions。
- **Commit**：`feat(application): establish the sole V4 formal spine`。

### W4-06　隐私、error 和资源闭环

- **Depends / audit**：`W4-05 / P1-15, P1-17..18`。
- **Paths**：精确 11 项：本方案、`compiler_core/application.py`、`compiler_core/audit_bundle.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/required-v4-tests.json`、`tests/security/test_privacy_firewall.py`、`tests/security/test_resource_limits.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；实际 changed paths 恰为全部 11 项，不修改 frozen contracts、schema、public CLI/MCP 或 W5 queue/backpressure/retention 实现。
- **动作**：`ApplicationV4Error` 只向边界暴露稳定 `code/stage/retryable/correlation_id`；EACCES/EPERM/EROFS、ENOSPC/EDQUOT、generic I/O、parse/security/engine 分级并递归清除 path/secret/PII；AuditBundle 七个公开 storage 操作统一经 privacy boundary 转译，原异常文本不进入 capability、bundle 或 transport；request byte/depth/admission deadline、solver deadline/cancel、pre-backend cancel、audit quota/bundle size 在各自既有边界 fail closed。P1-15 在本 task 只落实 Application 可拥有的 byte/depth/deadline/cancel/quota 子边界；public queue/backpressure/retention 与完整 production budget selector 仍归 `W5-CUTOVER`，mutation 保持 RED，不提前伪报关闭。
- **Gate**：31 个 application/formal/attack/privacy/resource/governance focused cases 全绿且 JUnit case identity 冻结；EACCES/ENOSPC/EIO、security/engine、cancel、oversize、deep JSON、admission/solver deadline、quota/bundle-size、PII/path/secret canary 全矩阵；失败无 COMPLETE/证书且 exception/capability/verified bundle bytes 无 traceback、绝对路径或 canary。runner 绑定 `w4-06-exact-runtime-reports`、`w4-06-private-fail-closed-contract`、`w4-06-exact-committed-scope` 三项专属 assertions。
- **Commit**：`fix(runtime): enforce bounded private fail-closed execution`。

### W4-07　Synthetic formal vertical slice

- **Depends / audit**：`W4-01..06 / P0-02..13, P1-01..18`。
- **Paths**：精确 15 项：本方案、`compiler_core/application.py`、`compiler_core/audit_bundle.py`、`remediation/v4/file-disposition.json`、`remediation/v4/tasks.json`、`tests/contract/test_required_test_manifest.py`、`tests/fixtures/keys/v4-synthetic-trust.json`、`tests/fixtures/packs/synthetic/signed-pack.json`、`tests/formal_e2e/test_positive_vertical_slice.py`、`tests/formal_e2e/test_public_boundary_inputs.py`、`tests/required-v4-tests.json`、`tests/security/test_vertical_slice_attacks.py`、`tests/storage_chaos/test_vertical_slice_recovery.py`、`tools/build_file_disposition.py`、`tools/remediate_v4.py`；两个既有 fixture 必须 byte-stable，只绑定 digest，实际 changed paths 恰为其余 13 项。测试首次暴露的 shared-verifier 并发 collision 与 replay semantic projection 缺口分别回到 Application/AuditBundle 责任模块作最小修复；不修改 frozen contracts、fixture、CLI/MCP 或 W5 queue/backpressure。
- **动作**：Application 以单一进程内执行锁保护共享 resolver/trust/fact/pack/backend/checker 状态与同 run 幂等 bundle，不在此实现生产队列；offline replay 使用 fresh isolated trust/service/application 从 sealed request 与同一 byte-stable fixture 重新执行，AuditBundle 的 semantic projection 保留 legal outcome、stable request/rule/source/trust identity，只消除新 run 必然重签的 fact/argument/backend/receipt identity，full-wire differences 继续完整报告。从严格外部 V4 canonical JSON 和真实 test artifact bytes 出发，不向 Application 注入 caller `PASS`、verified handle、certificate context 或可信 DTO。
- **Gate**：28 个 positive/public-boundary/tamper/recovery/governance focused cases 全绿且 JUnit case identity 冻结；产出 accepted formal result、完整 receipt DAG certificate、bundle verify 与 distinct-run offline replay；覆盖 missing、disputed、exception、permission、priority、temporal、request/source/rule/pack/fact tamper、backend crash、checker disagreement、revocation、same-run concurrency 及 manifest/COMPLETE 前 kill-recovery。删除或篡改任一材料必须 fail closed；runner 绑定两个 fixture digest、`w4-07-exact-vertical-reports`、`w4-07-public-byte-chain-contract`、`w4-07-exact-committed-scope` 三项专属 assertions。
- **PASS**：这只证明 synthetic test-only Kernel 机制，不证明中国法正确性或 production readiness；P0-02 的 synthetic mutation 转 `ACTIVE_REQUIRED`，真实 pack positive 仍归 `W8-06`，不得提前声称整个 P0-02 关闭。
- **Commit**：`test(e2e): prove V4 kernel formal output and replay`。

## 12. W5：公共入口原子切换，当前 V3 authority 清零

W5 是唯一允许“大而原子”的 cutover wave。W5-CUTOVER 之前的 branch 不可发布；cutover commit 必须同时切包根、CLI、Client、MCP、Schema、版本和旧 authority，不能出现某个入口先上线 V4、另一个仍走 V3 的提交。

### W5-01　入口合同和旧行为负例准备

- **Depends / audit**：`W4-07 / P0-01, P0-09..10, P1-14..18, P2-03`。
- **Paths**：仅 `tests/contract|formal_e2e|mcp_protocol/**` 和 fixtures。
- **动作**：先写三入口 V4 parity、V3 payload/import rejection、MCP 全状态/isError/outputSchema/path rejection、verify/read capability、CLI exit-code、package-root export tests。当前主链下应按预期失败。
- **Commit**：`test(entrypoints): define atomic V4 cutover contract`。

### H5-02　Candidate/advisory 资产归位、零语义审批和投产后 RFC

- **Mode / depends**：`AUTO；内容删除、权利不明或 NO_RELEVANT_SEMANTICS_APPROVED 触发 HUMAN_GATE；POST_RELEASE_RFC 只登记且不阻塞 / W5-01`。
- **默认处置**：每组 `addons/**`、`pipeline/**`、legacy/candidate configs、advisory modules、rule-engineering tools 在 `retain-path-nonpackaged|move-in-repo-source-tool|move-in-repo-experiment|candidate-asset|test-oracle` 中机器提出最小变更，不默认拆仓、发包或移动大资产。每项绑定 CodeGraph/AST consumers、动态入口、`semantic_assets|target_module|target_test|target_artifact|oracle_independence`、owner、license/provenance、retention 和 blob digest。
- **审批请求**：`delete-zero-value` 必须先附 symbol-level semantic inventory、CodeGraph/AST/dynamic consumer 复核和拟执行 negative gates；具名 approver 据此签发或拒绝 `NO_RELEVANT_SEMANTICS_APPROVED`，不得由 runner 自签。独立发行建议只能写成 `POST_RELEASE_RFC`，记录拟议 consumer、version、owner、必要性和成本；本轮不实现、不删源 path、不改变 package/release metadata，也不计入 Z03。
- **硬规则**：H5 只能批准 `NO_RELEVANT_SEMANTICS_APPROVED`、同仓 destination、owner、license 和 retention，不能豁免其他 B01 语义迁移门禁。未签响应不得删除有内容资产或声称无相关语义；也不得因等待而继续把它们装入 formal wheel。runner 只有在审批签名和机器证据均验证后，才接受该 terminal state。
- **用户定向删除**：第0节第14项已经决定删除范围，不需要再次判断其“零价值”，也不得误标 `NO_RELEVANT_SEMANTICS_APPROVED`。H5仍须核验一份由用户/授权主体签发、绑定已批准方案commit、两个exact paths、两个Git blobs/SHA-256、rules bytes/count/unique-ID count的`USER_AUTHORIZED_HISTORY_BOUND` receipt；runner只能生成待签envelope，不能自签。Fingerprint任一漂移立即`WAITING_HUMAN`。该授权不自动覆盖相邻 source manifest、ontology、domain config或其他 candidate asset。

### W5-02C　删除 CN legacy corpus 并断开全部消费者

- **Depends / audit**：`H5-02 / P0-14, P1-09, P2-04, P3-01..02`。
- **Allowed paths**：`configs/zh_CN/rules.yaml`、`configs/packs/cn-legacy-corpus/**`、`configs/perf_patterns.yaml`、`.gitignore`、`.github/workflows/ci.yml`、`.github/workflows/auto-release.yml`、`addons/cn/__init__.py`、`addons/cn/adapter.py`、`addons/workbuddy_mcp.py`、`compiler_core/cli.py`、`compiler_core/config_paths.py`、`compiler_core/prc_collision_engine.py`、`pipeline/fix_single_premise.py`、`tools/build_rule_pack_manifests.py`、`tools/run_trirail_matrix.py`、`tools/remediate_v4.py`、`tools/remediation/**`、`remediation/v4/**`、`tests/run_benchmark_zh.py`、`tests/stress_test_facts.py`、`tests/unit/test_adversarial.py`、`tests/unit/test_cli_contract.py`、`tests/unit/test_cli_evaluate_subprocess.py`、`tests/unit/test_cli_subprocess.py`、`tests/unit/test_plugin_registry.py`、`tests/unit/test_release_engineering.py`、`tests/unit/test_rule_pack_manifest.py`、`tests/unit/test_rule_pack_manifest_builder.py`、`tests/unit/test_trirail_collision.py`、`tests/unit/test_trirail_runtime.py`、`tests/unit/test_zh_rules.py`、新增 `tests/unit/test_remediation_legacy_cn_corpus.py`、`tests/packaging/test_legacy_cn_corpus_absent.py` 与 `tests/mcp_protocol/test_legacy_cn_corpus_absent.py`。不得把任何外部state/cache加入可写allowlist；不得顺带删除 `configs/zh_CN/source_manifest.yaml`、ontology、domain config或其他法域资产；实际 diff 出现未列路径即任务失败并返回plan drift。
- **冻结身份**：从同一已打开 bytes 计算 SHA-256、size和 YAML 解析结果，必须恰为第0节第14项 fingerprint并确认21,144个ID唯一；`v3.0.2^{commit}`必须为`aa0e038daf066bfc0baa4d27ee54adef12c3ae16`，rules Git blob为`8f51fdfd1db3e343812e8f35a321418fa854f4f7`，manifest Git blob为`1b29b412ee97563381f5a9b32e8b8efb9f62e90c`。`git show v3.0.2:<path>`必须在删除current files后仍可复算两份冻结指纹；receipt只保存摘要和locator，不复制13.6 MB内容、不新建归档repo或candidate artifact。完整V3环境与历史重放只由W5-07负责。
- **State/cache只读预检**：只扫描用户已登记或显式配置的state roots；V4 namespace发现`cn-legacy-corpus`或content digest `1c43bcc41579820c283eaf3a02ede928b61121aed5a089314a865e204189384d`即阻断，V3 run/cache命中只登记并保持原样，不迁移、不删除。不得声称覆盖未知用户路径。删除current file后，V4 verify/replay不得发现、加载、清理或回退这些V3 cache；历史材料缺失必须明确失败。
- **CodeGraph consumer baseline**：在B00-CG冻结的exact tree上，`PRCCollisionEngine.run→_run_cn_track`；`audit_pack|lookup_rules|export_corpus_pack|collect_baseline→RulePackRegistry.load_corpus_pack`；CLI `packs verify`和bundled-manifest test→`verify_all`；`test_adversarial→config_paths.rules_path`。同名`run|__init__`的扩散边不得当真实消费者。W5-02C逐边给出`DELETE|REWRITE_FIXTURE|RETAIN_GENERIC_FAIL_CLOSED`处置，并用AST、字符串、manifest/workflow和poison-canary补齐CodeGraph未索引的13.6 MB YAML及动态plugin/path边。
- **断开消费者**：
  1. 删除 CLI `rules`/`rules.lookup`、`cn_legacy_corpus` capability/resource 和对应公开测试，不以空列表、missing-file fallback或新名字保留；W5-02C后、W5-CUTOVER前，旧MCP `jc_lookup_rule(pack_id=cn-legacy-corpus)`必须稳定返回`PACK_NOT_INSTALLED`并设置协议`isError=true`，不得fallback；
  2. 删除 `config_paths.rules_path` 这条V3通用解析入口；仍有价值的非CN测试必须改用显式fixture或已验证pack，不得再由 jurisdiction字符串拼出该路径；
  3. CN addon移除 `rules_path` 默认值和registry绑定；保留的L0/modal/guardrail实验不得读取规则语料；
  4. `PRCCollisionEngine` 删除 CN Track 3 文件路径、loader、evaluator、inventory和fallback，只能明确标为CBL+SPC candidate experiment；TriRail同步删除 `PRC_CN` digest/输出和该语料依赖，不得把“两轨”伪称CN全量规则；
  5. 删除 `cn-legacy-corpus` manifest与旧manifest builder中的CN定义；`RulePackRegistry`、pack list/verify、capabilities和tests均不得再发现该pack ID；
  6. 删除 `pipeline/fix_single_premise.py` 原地覆写器以及 `.gitignore` 中 `rules.yaml.bak.*|rules_augmented.yaml|rules_pre_inject.yaml` 再生入口；
  7. 删除或独立重写直接加载该文件的旧benchmark、永久skip测试、stress/CLI/pack/TriRail测试；`test_zh_rules.py`在skip生效前就import-time加载，必须删除或先消除导入，不能以“已skip”证明安全；任何保留场景必须使用独立V4 fixture和synthetic signed pack，expected result不得由该legacy corpus生成；保留并加强“正式包失败不得回退legacy”的负向测试；
  8. 删除 auto-release 对该YAML的解析门禁；主CI在collection/build前运行retired-asset源码、manifest和registry负向门禁；`configs/perf_patterns.yaml`不得再用21,144条旧语料解释性能预算；W6 positive wheel gate负责证明最终distribution不含它；
  9. `compiler_core/plugin_registry.py`、`rule_packs.py`、`client.py`、`audit_bundle.py`、`rule_lookup.py`、`rule_governance.py`、`training.py`和`tools/perf_baseline.py`的通用实现不因本语料连坐删除，B01逐一标`RETAIN_GENERIC_FAIL_CLOSED`；它们不得硬编码该path/ID，也不得在默认发现、doctor、capabilities、pack list/verify或无参调用中触达。显式传入retired ID统一`PACK_NOT_INSTALLED`且不得fallback；若negative test证明现实现不能满足，必须plan-drift回H5扩allowlist，不能在本task顺手改未列路径；
  10. 上述消费者全绿后最后删除 `configs/zh_CN/rules.yaml`。`cn-official` 不得引用其path/hash/rule IDs作为source receipt，也不得批量复制、转换或promotion。
- **Gate**：

```powershell
py -3.12 -B tools/remediate_v4.py legacy-cn-corpus --check-removed --expected-sha256 032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44 --expected-bytes 13620766 --expected-rules 21144
py -3.12 -B tools/remediate_v4.py file-map --check --path configs/zh_CN/rules.yaml --expect-terminal HISTORY_BOUND
py -3.12 -B -m pytest --collect-only -q -p no:cacheprovider
py -3.12 -B -m pytest tests/contract tests/differential tests/packaging tests/mcp_protocol -q -p no:cacheprovider --basetemp "$R/tmp/W5-02C"
```

- **PASS**：物理文件和tracked path均不存在；当前pack registry、`packs list|verify`、doctor和CLI capabilities均无`cn-legacy-corpus`/path，CLI、Client、audit、lookup、governance、training、perf与旧MCP exact pack lookup稳定fail-closed；source/AST/YAML/workflow/test scan 对exact path、pack ID、digest、constructed path、default registration和file-open consumer均为0，允许命中仅限人工policy分类为`HISTORY_ONLY|DOC_UPDATE`的审计、方案、memory、冻结locator及具名negative gate；CN addon/CBL+SPC experiment不再触达该语料。安装态poison-canary分别在文件不存在、同名非法文件存在及`JURIS_CONFIG_DIR`指向注入目录三种状态运行doctor/capabilities/pack list/verify/formal evaluate/Client/MCP/CN experiment，文件访问计数均为0且能力与结果相同；正式包缺失/损坏始终fail-closed，PRC无静默`cn_rules=0`降级。`git show v3.0.2:<rules-path|manifest-path>`可复算冻结指纹，V4对已登记V3 cache既不发现也不改写；完整历史重放由W5-07单点验收。W6负责最终ZIP/RECORD等式；对路径、manifest、pack ID、旧builder CN spec、CLI/MCP command、CI load或任一consumer做回植mutation，gate必须失败。
- **Commit**：`refactor(corpus)!: remove CN legacy rules and every current consumer`，body记录exact fingerprint、历史locator、consumer closure和不进入`cn-official`的边界。

### W5-03　资产归位和 consumer 断边

- **Depends / audit**：`W5-02C / P0-14, P1-09, P2-04, P3-01..02`。
- **Paths**：按批准的 file-disposition；仅同仓归位；import/call/dynamic-consumer tests。
- **动作**：除W5-02C明确删除的CN legacy corpus外，其他candidate corpora默认同仓保留现有 path，或仅在真实 namespace 冲突时一次性仓内移动；保持 blob/source/license/review status/consumer，不强制搬动其他大文件。analysis、training、governance reports 和剩余candidate lookup先切断包根/CLI/MCP/contracts现有公共入边，再保留为同仓source tools；pipeline保留不依赖已删语料的离线source-tool入口，确认formal入边为零且不新增；legacy adapters、裁剪后的实验和fast-path作为同仓experiments。本轮所有非生产面不得出现第二 `pyproject.toml`、release workflow 或 deployment manifest；输出默认分页/摘要。
- **CodeGraph 已知断边**：W5 必须同时删除包根 analysis exports、CLI analyze/training/rules-audit/内联 candidate lookup、旧 MCP advisory tools，以及 `contracts.py` 对 analysis/governance/training schema 的反向拼接；W5-02C另以源码/字符串/manifest补查CN legacy corpus动态消费者；`rendering` 不在此删除，继续作为 `RUNTIME_OUTPUT`。
- **Gate**：CodeGraph sync 后 normalized observed graph 与 source tree一致；每个删除 path 对应 terminal-state branch 的 required receipts 已绿；独立 oracle 不导入 production provider；shadow differential仍 required；blob digest+byte count+业务 record count守恒，line count只作观测；formal AST无 source-tool/experiment/candidate 入边；不因 source anchor误报 eligible。同仓归位或 artifact 重建不能替代语义迁移完成。
- **Commit**：`refactor(boundary): isolate non-production sources from V4 runtime`。

### W5-CUTOVER　一次性切换全部 current authority

- **Depends / audit**：`W5-03 / P0-01, P0-08..10, P0-14, P1-13..18, P2-03..04, P2-07, P3-02`。
- **删除前置状态**：本 commit 所有删除项必须已处于 `MIGRATED_GREEN|HISTORY_BOUND|NO_RELEVANT_SEMANTICS_APPROVED`，并绑定该 terminal branch 要求的 exact receipts；不得包含 `UNREVIEWED`。
- **Allowed paths**：包根、`cli.py`、`client.py`、新增 `mcp.py`、`mcp_server.py`、`version.py`、`rendering.py`、neutral render profile、rendering/entrypoint tests、generated Schema/manifest/resources、所有需删除的 V3/W1b/compat/suffixed staged files/tests/docs、authority/file-disposition；不得改锁和 release workflow。
- **同一 commit 必做**：
  1. 包根只导出 `JCClient`、V4 contracts、typed errors、verify/replay results、`__version__`；
  2. 三入口的 formal evaluate 操作只调用同一 V4 parser 和 `ApplicationV4.evaluate`；CLI/Client 的 verify/replay 与 MCP 的 `jc_verify_run` 调用唯一 AuditBundle verifier/replayer，read 调用同一 bounded artifact reader；CLI/Client render 只调用 verified-bundle renderer；
  3. MCP 只有 `jc_capabilities|jc_evaluate|jc_verify_run|jc_read_artifact`，零 resources，禁 path/dynamic manifest/advisory；`rules.lookup|jc_lookup_rule|data_root|candidate resource` 必须同时从CLI capabilities、MCP `tools/list`和派生manifest消失。切换部署强制终止并重启旧MCP process/session，旧工具清单失效，禁止以`listChanged=false`继续复用旧会话；
  4. version 切为 `4.0.0rc1` 或 runner 计算的下一未发布 RC，所有 runtime identity 同源；
  5. 删除 `compat_v3_v4.py`；`legal_ir_v3.py` 先迁 typed IR/source/type-check不变量。V3/W1b Schema、tests、fixtures仅在有效语义已绑定 V4 target test、V3 payload负向拒绝已绿、历史 bytes/hash/locator 已封存后删除；companion-spec differential fixtures不属于 V3 compatibility，不得随删；
  6. 按 `contracts_v4→contracts`、`source_service_v2→source_service`、`fact_admission_v1→fact_admission`、`legal_spec_ivl→legal_ir`、`argumentation_v2→argumentation`、`backend_router_v1→backend_router/backends`、`certificate_v1→certificates`、`independent_grounded_checker→independent_checker` 显式映射后删除 parallel path；`independent_checker.py` 不得合入 production provider、argumentation 或 application；
  7. 删除 current V2→V3/WorkBuddy migration authority；历史仅由 tag/旧 artifact 保存；
  8. `mcp_manifest.json` 和 Schema 由小型 emitter 重建；禁止手工补兼容字段、`DEFAULT_MANIFEST` 或 runtime dynamic manifest；
  9. 将 `rendering.py` 和 neutral profile 改为 V4 verified-bundle-only，移除旧 `SemanticResult`、`output_firewall`、evaluator 和 `Application.evaluate` 入边；CodeGraph 全量 sync/reindex后，公共 V4 入口只剩 formal runtime和该 renderer，旧 analysis/training/governance/lookup 调用边为零。
- **Gate**：

```powershell
py -3.12 -B tools/remediate_v4.py generated --check
py -3.12 -B tools/remediate_v4.py authority --check --single-formal-sink
py -3.12 -B tools/remediate_v4.py file-map --check --deletions-ready --require-target-receipts
py -3.12 -B -m pytest tests/contract tests/formal_e2e tests/mcp_protocol -q -p no:cacheprovider --basetemp "$R/tmp/W5-CUTOVER"
py -3.12 -B -m pytest tests/differential -q -p no:cacheprovider --basetemp "$R/tmp/W5-DIFF"
py -3.12 -B tools/remediate_v4.py forbidden-imports --check v3,w1b,compat,workbuddy
```

- **PASS**：三入口同一个 canonical request 得到相同 run/certificate/bundle digests；旧 payload/import 明确失败；四工具集合在唯一`TOOL_SPECS`、`tools/list`和派生manifest逐字节同构，旧lookup/resource与旧session均不可用；MCP blocked/engine/storage error 均 `isError=true`；合法 review/missing/conflict 为非 formal 成功。
- **Commit**：`feat(v4)!: atomically cut all public runtime surfaces to V4`，body 明确 breaking change 和 V3 historical replay 边界。

### W5-05　全仓 current authority 复扫

- **Depends / audit**：`W5-CUTOVER / P0-01, P0-08, P0-14, P2-04, P3-02`。
- **Paths**：只修 authority/docs/tests/file-disposition 漏项；任何语义回归回责任 task。
- **Gate**：所有 tracked path disposition 重新闭合；`rg`/AST/installed-source tests 对 V3/W1b/compat/current WorkBuddy authority 零命中，允许命中仅审计报告、changelog breaking note 和历史 artifact locator；formal core 对 advisory 入边为零。
- **Commit**：`chore(v4): close current-source authority after cutover`。

### W5-06　三入口与错误矩阵

- **Depends / audit**：`W5-05 / P0-01, P0-09..10, P1-14..18`。
- **Gate**：源码树 CLI/Client/MCP 对 formal、hypothetical、review、missing、conflict、unknown、admission blocked、resource exhausted、cancelled、engine/storage error 全矩阵；每态核对 process exit、MCP `isError`、typed status、certificate presence、bundle/verify behavior。
- **Commit**：`test(entrypoints): enforce canonical V4 parity and fail-closed errors`。

### W5-07　V3 历史重放隔离说明

- **Depends**：`W5-06`。
- **Paths**：current operations doc 中只提供 frozen artifact locator、hash、隔离环境要求；不得新增 V3 code。
- **动作**：文档绑定 `v3.0.2` commit、冻结wheel、locks、spec/environment、pack manifest及全部resource blobs，给出无current tree、无网络的隔离重放命令和缺件错误。已登记V3 run/cache只读保留，不迁移、不删除；V4不得用current repo、其他pack、`cn-official`或任何V3 cache补缺。
- **Gate**：按文档在隔离环境完成一次历史重放并核对receipt；V4 process不发现、加载、清理或回退V3 state；历史说明不被current schema/docs index当authority；没有自动迁移命令，任一冻结材料缺失时明确失败。
- **Commit**：`docs(history): isolate V3 replay from current runtime`。

## 13. W6：单一 V4 production wheel、全锁、CI、供应链和发布

### W6-01　精确 package/wheel allowlist

- **Depends / audit**：`W5-07 / P0-14, P1-19, P2-06`。
- **Paths**：`pyproject.toml`、唯一薄 `tools/wheel_gate.py`、packaging tests；runner/CI 只调用该 gate，不另写实现。
- **动作**：expected wheel file set 直接由人工 `module-authority.json` 中可发布 class 加明示的 V4 schema、neutral render profile、license/notice/metadata计算，不提交第二份 allowlist。包含 V4 runtime、formal adapters、verified-bundle renderer、deterministic pack verify/admission；排除 addons、pipeline/source tools、candidate/legacy configs、experiments、tests、V3/W1b/compat、机器报告；engine wheel 不含 `cn-official` bytes。删除当前 `FORBIDDEN` blacklist及保护它的测试，不建归档，Git历史足够。
- **Gate**：从无 `.git` 的两个 clean archive 分别 build；wheel ZIP entry names 无重复，normalized ZIP names、normalized RECORD names 与 expected set 三者集合严格相等，任一 missing/extra/duplicate/path traversal 均失败；`configs/zh_CN/rules.yaml`、`configs/packs/cn-legacy-corpus/manifest.yaml`、pack ID/content digest、旧builder CN spec及default registration在current executable/config/registry/build inputs与ZIP/RECORD/METADATA/SBOM/provenance中均为0，具名`HISTORY_ONLY|DOC_UPDATE` locator不计作运行输入；所有 removed public imports 在 clean install 失败；AST 无 `FORBIDDEN` 常量/引用；向clean archive回植语料、manifest、旧builder spec、default registration或向wheel注入任一新文件均必须失败。
- **Commit**：`build(package): make the engine wheel V4 formal-only`。

### H6-02　锁文件和新依赖批准

- **Mode / depends**：`HUMAN_GATE / W6-01`。
- **原因**：项目规则禁止未授权修改 lock；请求列出签名/Schema/property/build/test/runtime 依赖、版本、transitive graph、license、平台 wheel、hash 和替代方案。
- **响应**：批准 exact profiles/versions 或拒绝；生产 runtime 只保留必要依赖，test/build/source-tool 分离。已知处置目标：Jinja2/render extra和render lock为全生态真删除；`pydantic|python-docx|pdfplumber`若 pipeline 保留则进入同仓 source-tool profile，只算 JC production distribution移除；Hypothesis 保留 test-only 供 property tests。

### W6-03　完整 hash locks 和供应链

- **Depends / audit**：`H6-02 / P1-20`。
- **Paths**：`requirements/*.lock`、supply-chain tooling/tests；只按批准内容改。
- **动作**：production/build/test/source-tool/release 及实际发布 optional profiles 的完整 transitive graph 全 pin+hash；禁止 release 内浮动升级；lock digests 进入 provenance/run identity。依赖变更分报 `jc_direct_removed|moved_to_source_tool|ecosystem_removed`，禁止用笼统“-N deps”。
- **Gate**：Windows/Linux clean/offline `--require-hashes` install；替换 dependency file/hash/license deny/vulnerability blocker 均失败；SBOM graph 与 lock 对账；stable wheel METADATA/SBOM/engine locks不含 Jinja2、pipeline三依赖和Hypothesis，source-tool lock承接 pipeline实际依赖，test lock保留Hypothesis，全目标清单中Jinja2为零。
- **Commit**：`build(deps): hash-lock every released and build profile`。

### W6-04　双构建和 clean installed-wheel E2E

- **Depends / audit**：`W6-03 / P0-14, P1-19, P2-06`。
- **Paths**：packaging tests/runner gates；生产修复回责任 task。
- **动作**：固定 builder、epoch、locks；两个独立 source archive build；新 venv 只装 hashed runtime deps + wheel + approved synthetic pack；运行 import/capabilities/doctor/CLI/Client/MCP/evaluate/verify/replay。
- **PASS**：wheel bytes 相同；RECORD exact；installed code path 位于 venv；accepted formal synthetic E2E 成功；V3、analysis、training、governance reports、candidate lookup、pipeline、legacy experiments和candidate imports全失败；`compiler_core.rendering` import及 verified-bundle render lifecycle成功；capabilities无绝对路径且 `legal_production_ready=false`。
- **Commit**：`test(package): prove reproducible installed V4 lifecycle`。

### W6-05　CI required matrix

- **Depends / audit**：`W6-04 / P2-01..03`。
- **Paths**：`.github/workflows/ci.yml`、test config、runner CI verifier。
- **Jobs**：generated diff/authority/purity/secrets；ruff/type；unit/contract/property/mutation；integration/formal E2E/security；Ubuntu 3.11/3.12；Windows 3.11/3.12；storage/chaos platform subsets；locks/audit/license；A/B build；installed wheel；SBOM/provenance；performance；docs/current paths。
- **Gate**：required test skip/xfail=0；collection前的retired-asset source/manifest/registry gate与build后的installed-wheel gate均required；companion spec exact commit；full output/exit reports retained；相同 MCP unit 不伪装成 installed lifecycle。
- **Commit**：`ci(v4): require semantic security packaging and platform gates`。

### W6-06　SBOM、provenance、checksums 和 attestation

- **Depends / audit**：`W6-04 / P0-15, P1-08, P1-20`。
- **Paths**：`tools/build_provenance.py`、supply-chain tooling、provenance tests。
- **动作**：subject 是 exact wheel；绑定 clean commit/tree、spec commit、builder、locks、Schema、ToolSpec、authority registry、test policy/trust public material；SBOM 覆盖 wheel files+runtime deps；signature/attestation 与法律 pack签名分 scope。
- **Gate**：dirty tree、错 spec/schema/tool/lock/wheel、unsigned provenance、SBOM/RECORD mismatch 均失败。
- **Commit**：`build(attestation): bind release evidence to the tested wheel`。

### H6-07　GitHub governance 和发布签发者

- **Mode / depends**：`EXTERNAL_GATE + HUMAN_GATE / W6-06`。
- **请求**：现场读取 branch/tag protection、required checks、admin bypass、CODEOWNERS、tag/release signing、artifact retention；指定 release signer 和双人审批。仅 API 无权限时返回 exit 21，不猜测已保护。

### W6-08　Artifact promotion workflow 和 current docs

- **Depends / audit**：`H6-07 / P0-15, P2-04, P2-07, P3-02`。
- **Paths**：`.github/workflows/auto-release.yml`、README、CHANGELOG、HANDOFF、AGENTS、memory、current docs、唯一 registry、SECURITY/CODEOWNERS/NOTICE（按治理响应）。
- **动作**：CI build once；tag job只晋级同一 digest，不重建；强制 tag=package=METADATA=CLI=MCP=RunIdentity；release 附 wheel/checksums/SBOM/provenance/attestation/schema/tool digests。Docs 只陈述已完成 V4 current state，历史随 tag。
- **Gate**：wrong tag/commit/METADATA/digest/no asset/no signature/stale path/V3 current claim 均失败；docs 中命令实际执行；release workflow dry-run 不写远端。
- **Commit**：`build(release): promote one attested V4 artifact and align current docs`。

## 14. W7：V4 Kernel RC 生产演练

### H7-00　目标 state provider、平台和 SLO 输入

- **Mode / depends**：`EXTERNAL_GATE + HUMAN_GATE / W6-08`。
- **请求**：Windows/NTFS 与 Linux/ext4 隔离环境、service identity、DACL/permissions、at-rest encryption、quota、retention/legal hold、backup/restore、capacity；性能测试先产基线，再由负责人批准 latency/throughput/RSS/artifact budgets。
- **缺失行为**：可继续开发，不得把 RC 晋级为 production-ready。

### W7-01　生产 storage capability 验收

- **Depends / audit**：`H7-00 / P0-13, P1-10..13, P1-17`。
- **动作**：在目标身份和文件系统动态验证 owner/DACL/reparse/no-follow/durability/encryption/quota/retention/backup/restore；StorageCapability digest 写入 readiness/run identity。
- **Gate**：Everyone ACE、junction swap、power-loss/fault injection、disk full、backup tamper、restore 不一致；任何 capability 无法证明时 formal startup blocked。
- **Commit**：测试/运维代码变更单独 commit；现场报告只进外部 evidence store。

### W7-02　容量和性能预算

- **Depends**：`W7-01`。
- **动作**：approved fixed corpus 和 synthetic pack；测 p50/p95/p99、throughput、RSS、request/result/bundle/events、queue/backpressure、quota/retention growth；不记录事实文本。
- **Gate**：超预算、无界增长、cancel无效、slow request阻塞 health probe 均失败；预算批准响应绑定报告 digest。
- **Commit**：`test(performance): enforce approved V4 production budgets`。

### W7-03　灾难、撤销和回退演练

- **Depends**：`W7-02`。
- **动作**：engine/pack/trust key/service key revocation；kill/restart、corrupt artifact、backup/restore、incident stop；回退只到上一份已签 V4 artifact，没有上一份时停止 formal service，绝不启用 V3。
- **安全边界**：所有破坏性演练在与目标 provider 能力等价、但物理隔离且带 test-realm 哨兵的 state root 进行；生产 root 只做只读 capability/backup/restore 验证，runner 对生产路径执行 fault injection 必须 exit 6。
- **Gate**：撤销即时使 readiness false；旧 cert verification按政策返回明确状态；恢复后 bytes/digests一致；不可恢复则 fail closed。
- **Commit**：`test(operations): prove V4 revocation recovery and no-V3 rollback`。

### W7-04　Kernel RC evidence verifier

- **Depends / audit**：`W7-01..03 / P0-01..15, P1-01..20, P2-01..07, P3-01..02`。
- **动作**：runner 从原始 receipts 重新计算 issue closure、file disposition、full gates、A/B wheel、installed E2E、storage/perf/ops；生成 `kernel-rc-evidence.json` 和签名请求。不得手填 PASS。
- **PASS**：P0/P1=0；P2/P3全部 closed/explicitly external with gate；synthetic formal output/verify/replay成功；`kernel_ready=true`、`legal_production_ready=false`。
- **Commit**：`chore(release): assemble verifiable V4 Kernel RC evidence`。

### H7-05　RC 远端晋级

- **Mode**：`HUMAN_GATE / W7-04`。
- **响应**：授权 exact commit/tree/wheel/evidence digests 的 push/tag/release。Runner 只在签发范围内操作，并下载已发布资产重新验签验 hash。未授权时本地 RC 已完成，但不声称公开发布。

## 15. W8：真实 `cn-official` 和 4.0.0

### H8-00　领域、法源、角色和密钥开工门禁

- **Depends**：`W7-04` 的已签 Kernel RC evidence。`H7-05` 只是可选的远端 RC 晋级，不是编制真实 pack 的前提。
- **请求必须指定**：首个完整领域；适用法域和截止日期；第一方法源清单、取得方式、locator、许可/再分发；现行/失效/过渡版本策略；source custodian、两名独立法律 reviewer、独立工程 reviewer、release approver；production trust/key custody/revocation；覆盖和抽样标准。签发的`FORMAL_SOURCE_INVENTORY`必须列出唯一允许进入正式source/candidate/coverage/build闭包的exact sources/digests，并明确排除legacy语料path、SHA-256、Git blob、pack ID及其派生物。
- **禁止默认**：不自动继承旧方案的领域，不把教材/OCR/类案/legacy manifest 当正式法源，不让同一身份兼任全部审批。缺少该exact inventory或发现允许源的provenance向legacy语料回指时，W8保持`WAITING_HUMAN`。

### W8-01　第一方法源不可变摄取

- **Depends / audit**：`H8-00 / P0-02, P0-04`。
- **位置**：pack 工程使用本仓独立 worktree、同仓不打包的 pack-engineering source、受控 source store 和 artifact pipeline；本轮不得新建第二代码 repo。engine wheel 只保留 contract/verifier，不嵌入原始法律包；最终产物作为独立签名 `cn-official` artifact 发布。若既有治理强制独立 repo，W8 返回 `WAITING_EXTERNAL` 并另立后续工程；该后续工程不得冒充本任务完成或计入本次 Z03。
- **动作**：在批准的受控 source store 保存或解析原始 bytes，记录 raw digest、规范化 profile/digest、authority、公布/生效/失效、canonical locator、版本图、provenance/license 和 source authenticity receipt。若许可不允许再分发，engine/pack/repo 只保存 digest、locator、custody ref 和审批 receipt，不复制原文 bytes。
- **Legacy 隔离**：source intake、candidate generation、RuleV4、review queue和pack provenance均拒绝 `configs/zh_CN/rules.yaml` 的path、digest、pack ID、批量rule-ID映射、复制或自动转换。可以从批准第一方法源独立形成相同法律命题，偶然文本/ID相同本身既不证明依赖也不能充当来源证明；每条正式候选必须拥有与legacy corpus无数据流、派生或provenance依赖的source/reviewer receipts。
- **Gate**：bytes/locator/version/time/signature/takedown mutation；从`FORMAL_SOURCE_INVENTORY`到规范化source、candidate、review、coverage、pack的依赖闭包逐节点可追且与legacy path/hash/blob/pack/派生物集合不相交；source inventory 100% 有状态，未知许可可作为 candidate 存档但不能进入 official pack。

### W8-02　RuleV4 candidate 生成

- **Depends**：`W8-01`。
- **动作**：机器从 source 生成 typed candidate；每条绑定 source/locator/interpretation，覆盖 premise/conclusion/modality/exception/permission/priority/temporal/numeric；生成 source-to-rule coverage 和 omission register。
- **硬边界**：输出状态只能 candidate；LLM/OCR/教材可提议，不可签 approval 或 active。
- **Gate**：coverage denominator只由H8-00批准的第一方法源中明确in-scope的规范单元组成，每个单元必须对应candidate或具理由的omission；不得以legacy 21,144条、其rule IDs、生成candidate数或candidate-only资产充当分母或覆盖证明。

### H8-03　法律审核 receipts

- **Mode / depends**：`HUMAN_GATE / W8-02`。
- **请求**：按 exact source/rule digest 或固定 batch Merkle root，要求两名不同法律 reviewer 各自提供 approve/reject/needs-change、解释选择、效力、范围、例外和理由并签名。被拒条目回到 W8-02 形成新 digest，不能原地改已批 rule；规则任一字节变化使两份旧审批同时失效。

### H8-04　工程审核和角色分离

- **Mode / depends**：`HUMAN_GATE / H8-03`。
- **请求**：工程 reviewer 对类型、可执行性、source binding、tests、coverage、loss、性能签 receipt；runner 验证其与两名法律 reviewer、source custodian、release approver不是同一 signer，subject sets 完全一致。

### W8-05　Deterministic official pack build

- **Depends**：`H8-04`。
- **动作**：从批准的 immutable materials build；manifest 绑定全部 rule/source/config/receipt/schema/trust/compiler/coverage digests；两次 clean build bytes相同；调用 production pack signer/HSM 只签 exact digest。
- **Gate**：少签、错 scope、same-role、source/rule/config替换、build drift、empty pack、未覆盖 blocker、撤销 key 全失败；manifest/provenance依赖图必须完整收敛到`FORMAL_SOURCE_INVENTORY`及批准receipts，加入legacy path/hash/blob/pack ID、旧rule-ID映射或任一legacy派生节点的mutation必杀；engine wheel不重建。

### W8-06　真实领域全状态和法律质量门禁

- **Depends**：`W8-05`。
- **动作**：installed Kernel RC + signed pack；正向 formal、missing、disputed、exception、conflict、priority、permission、temporal boundary、失效/过渡、撤销/rollback；每个结论可追到 source locator和两类 approval receipts。
- **Gate**：semantic mutations全杀；人工抽样验证法律/解释质量，但不代替机器 hash/signature；candidate-only 不进入 denominator；至少一个真实正式结果可 verify/replay。

### H8-07　`cn-official` release 和 4.0.0 晋级

- **Mode / depends**：`HUMAN_GATE / W8-06`。
- **响应**：pack release approver 和 engine release approver 分别签 exact artifacts；runner核对 readiness、certificate、audit、SBOM、provenance绑定同一 engine/pack/trust digests。
- **动作**：发布独立 pack artifact。随后在唯一 `4.0.0` version commit 上重新构建 engine stable wheel；因为 METADATA/version 已改变，RC wheel 不能改名、重标或原样“晋级”为 stable。对该 `4.0.0` wheel digest 重新运行 W6-04～W7-04 全套门禁，再 tag，并只发布这份已测试 digest；下载重验。完成后 `legal_production_ready=true`。任一门禁缺失保持 RC 和 false，不靠免责声明晋级。

## 16. W9：DSH formal profile，不改 general DSH

### H9-00　DSH pin 和部署拓扑

- **Mode / depends**：`HUMAN_GATE / H8-07`。
- **请求**：批准 exact DSH commit/release、Node/pnpm lock、OS、out-of-tree bundle/profile 位置、JC MCP transport/process identity、允许工具、部署/更新/回滚策略。生产 JC formal service 必须使用与 DSH 不同的 effective OS/service identity，并通过认证 transport/broker 访问；容器只有在不同宿主 identity/user namespace 且 JC state volume 对 DSH effective identity 无写权限时才等价。若 DSH 与 JC 使用同一 effective SID/UID/service principal，或任一路径、volume、broker 使 DSH 可写 JC state，formal production 必须 BLOCKED。不得自动跟随 master。

### W9-01　Out-of-tree formal bundle/profile

- **Depends / audit**：`H9-00 / P2-05`。
- **位置**：DSH 外部集成 repo，不改 DSH agent loop，不复制 JC semantics。
- **动作**：新增 `jc-formal` profile/bundle，通用 profile不加载；profile startup先验证 JC capabilities的 engine/wheel/tree/schema/tool/pack/trust/storage digests。
- **Gate**：JC缺失、非V4、digest未批准、pack/trust/storage非ready时 formal profile拒绝激活，general profile仍正常。

### W9-02　MCP client fail-closed 配置

- **Depends**：`W9-01`。
- **动作**：只接四个 tools；`failOnStartupError=true`；定义启动、工具同步、timeout/cancel、crash/reconnect、retry/idempotency；不依赖 MCP Resources/Prompts。formal profile 使用私有、认证且绑定批准 artifact digest 的 MCP session，不从模型可见的全局同名 tool registry 选择 server；每次启动/重连先重新比较 capabilities。开发环境可用受控 stdio；生产采用 H9-00 批准的独立服务身份和认证 transport，DSH 进程对 JC state root 无文件权限。
- **Gate**：server unavailable、tool list/schema drift、`isError`翻转、输出超限、session重连均不能绕过 formal guard。

### W9-03　Project skill 仅负责触发说明

- **Depends**：`W9-02`。
- **动作**：skill说明何时用户需要formal、如何构造V4请求、如何呈现非formal状态；skill不是安全边界，删除skill也不能绕过delivery guard。
- **Gate**：prompt injection要求跳过JC或伪造验证时，结构化guard仍阻断。

### W9-04　Delivery guard plugin

- **Depends**：`W9-02`。
- **动作**：只有当前session中的 `jc_verify_run` 对exact run/certificate/bundle返回verified，guard才允许formal marker/正式法律结论交付；正式交付必须是 JC certificate 绑定、经 `jc_read_artifact` 复验取得的 exact artifact bytes。模型改写、拼接、摘要或包装后的文本自动失去 formal 身份，只能明确标为非正式派生内容。自然语言“已验证”、advisory tool文本、模型自报、历史session receipt均无效。
- **Gate**：certificate/bundle/receipt/run identity任一替换，artifact 改一个字节或跨 session 重放，evaluate blocked/error、MCP `isError`删除/翻转、其他工具写state、advisory污染premise全部阻断。

### W9-05　Bypass、隔离和升级兼容测试

- **Depends**：`W9-03..04`。
- **Paths**：`tests/dsh_formal/**` 在集成repo。
- **Gate**：不调用JC、工具隐藏/改名、fake tool output、server crash/reconnect exhausted、cancel、tool schema drift、session污染、filesystem/bash/web/MCP写JC state、同 effective SID/UID/service principal、共享可写 path/volume/broker、未认证 transport、V3 payload、pack/key revocation；general profile仍可用但没有formal capability。

### W9-06　DSH integration evidence

- **Depends**：`W9-05`。
- **动作**：生成并签 `dsh-formal-evidence.json`，绑定 DSH/JC commits、locks、profile/plugin、ToolSpec、engine/pack/trust、bypass reports；升级DSH pin必须全量重跑，不用“兼容应当没问题”。
- **完成**：formal DSH只消费JC证书而不拥有JC语义；general DSH保持即插即用。

## 17. 44 项审计问题闭环矩阵

Runner 的 `issue-map --check` 必须验证下表。一个 task green 不等于问题关闭；只有列出的 closure proof 全部有可复验 receipt 才关闭。

### 17.1 P0

| ID | Closure tasks | 机器完成证明 |
| --- | --- | --- |
| P0-01 | W4-05, W5-CUTOVER, W5-06 | 三入口同一 ApplicationV4；旧入口/import/payload 失败；AST single sink |
| P0-02 | W2-02, W2-05, W4-07, W8-06 | synthetic 与真实 pack 各有至少一个 public positive formal+verify+replay |
| P0-03 | W1-01..03 | 单一 Digest/JCS；全对象逐跳可组合；旧 grammar 拒绝 |
| P0-04 | W1-04..06, W2-01..02 | caller PASS 不可构造；bytes/signature/scope/revocation attacks 全拒 |
| P0-05 | W2-03..05, W8-05 | active 由 signed immutable pack 推导；candidate 无法激活 |
| P0-06 | W3-03..04 | provider 实际调用；fake receipt/wrong proof 不通过 checker |
| P0-07 | W4-03..04 | certificate 从 verified bundle 重算、签名；caller/bundle tamper 失败 |
| P0-08 | W4-05, W5-CUTOVER | advisory certificate 入边为零；formal result保留 typed certificate artifact |
| P0-09 | W5-01, W5-CUTOVER, W5-06, W9-04..05 | blocked/error `isError=true`；verify/read闭环；delivery guard bypass suite |
| P0-10 | W1-04, W5-CUTOVER, W9-05 | formal MCP wire 无 path；UNC/device/reparse 输入读取前拒绝 |
| P0-11 | W2-04, W4-02 | hash/parse/execute同 snapshot；TOCTOU/symlink swap mutation 全杀 |
| P0-12 | W4-01..03 | build-complete run identity；COMPLETE只返回磁盘验证对象；collision失败 |
| P0-13 | W4-02, W7-01, H9-00 | no-follow/reparse/DACL；独立service identity；state escape失败 |
| P0-14 | W5-02C..03, W5-CUTOVER, W6-01..04 | CN legacy corpus及全部consumer归零；formal import graph和wheel exact allowlist；禁止模块/语料注入mutation全杀 |
| P0-15 | W6-06..08, H7-05, H8-07 | version/tag/METADATA/artifact/attestation一致；download reverify；RC不重标stable |

### 17.2 P1

| ID | Closure tasks | 机器完成证明 |
| --- | --- | --- |
| P1-01 | W1-01, W1-06 | RFC 8785/I-JSON跨语言vectors/property全过 |
| P1-02 | W1-02..03, W1-06 | Python/Schema/MCP同接受集；封闭objects；engine只收4 |
| P1-03 | W0-02, W2-01 | UTC instant比较；fraction/offset/boundary tests |
| P1-04 | W2-01 | 单root/terminal/connected/order-independent SourcePath |
| P1-05 | W3-01, W3-04..05 | 字段守恒；独立oracle；critical field mutations全杀 |
| P1-06 | W3-02, W3-04..05 | priority/permission/UNDEC/witness/reference parity正确 |
| P1-07 | W2-03, W4-05 | typed domain/config来自signed pack；runtime advisory patch为零 |
| P1-08 | W2-03..05, W6-06 | signed build attestation；空/错commit/issue-order失败 |
| P1-09 | W2-03, W5-02C..03 | eligibility只来自verified snapshot；CN legacy candidate current-tree删除，其他candidate输出明确 |
| P1-10 | W2-04, W4-02..03, W7-03 | locks/unique staging/lease/recovery；并发/kill全过 |
| P1-11 | W4-02..03, W7-01 | file+dir durability；fault injection后complete-or-absent |
| P1-12 | W4-02, W7-01 | Windows owner/DACL/reparse现场fail-closed |
| P1-13 | W4-01..03, W5-CUTOVER | V4 namespace/writer/replay；V3/V4双向拒绝 |
| P1-14 | W1-03, W5-CUTOVER, W5-06 | 唯一`TOOL_SPECS`与runtime codec一致；派生manifest与真实`tools/list` canonical bytes/hash一致 |
| P1-15 | W0-02, W1-04, W4-06, W5-CUTOVER | byte/depth/deadline/cancel/queue/quota/retention门禁 |
| P1-16 | W2-03, W4-05 | config缺失/损坏/权限/unknown字段全部BLOCKED；无global fallback |
| P1-17 | W1-04, W4-06, W5-CUTOVER, W7-01 | 封闭ref grammar；所有公共/bundle输出path canary为零 |
| P1-18 | W4-06, W5-06 | parse/security/storage/engine稳定error和retryability矩阵 |
| P1-19 | W6-01, W6-04 | exact RECORD、双build、clean install、forbidden imports |
| P1-20 | H6-02, W6-03, W6-05..08 | 全transitive hash locks；完整SBOM/provenance/promotion |

### 17.3 P2/P3

| ID | Closure tasks | 完成证明 |
| --- | --- | --- |
| P2-01 | B02, W6-05 | companion spec不再依赖个人路径；exact commit两Python矩阵全过 |
| P2-02 | W0-04, W6-05 | required suites存在且required skip/xfail=0 |
| P2-03 | W1-06, W2-06, W4-07, W5-01 | caller trusted/PASS/engine3/compat正例全部改为负例 |
| P2-04 | W0-03, W5-05, W6-08 | 一个module registry和一套current docs；stale claims为零 |
| P2-05 | H9-00, W9-05..06 | DSH pin和兼容/bypass tests，每次升级重跑 |
| P2-06 | W6-01, W6-04 | 无`.git` archive build/gate成功，provenance显式输入身份 |
| P2-07 | W1-02, W5-CUTOVER | 包根`__version__`与唯一版本源一致 |
| P3-01 | W5-02C..03 | 删除21,144条legacy默认lookup；剩余pack输出有摘要/分页/上限，不默认展开全部IDs |
| P3-02 | W5-CUTOVER, W5-07, W6-08 | 历史指南退出current authority，Git artifact可定位 |

## 18. Required test、命令和证据矩阵

### 18.1 本地每任务公共前后门

```powershell
git diff --check
py -3.12 -B tools/remediate_v4.py authority --check
py -3.12 -B tools/remediate_v4.py file-map --check --all-tracked
py -3.12 -B tools/remediate_v4.py issue-map --check
```

Runner 记录每条命令、exit code、stdout/stderr digest。只截取日志片段不足以证明通过。

### 18.2 Suite

| Suite | 标准命令 | Required evidence |
| --- | --- | --- |
| unit | `py -3.12 -B -m pytest tests/unit -q ...` | 纯模型/状态/算法；0 required skip |
| contract | `py -3.12 -B -m pytest tests/contract -q ...` | Python/Schema/CLI/Client/MCP differential |
| property | `py -3.12 -B -m pytest tests/property -q ...` | nested/Unicode/limits/time/graph/IR properties |
| integration | `py -3.12 -B -m pytest tests/integration -q ...` | artifact→certificate chain |
| formal E2E | `py -3.12 -B -m pytest tests/formal_e2e -q ...` | public positive + all semantic states + verify/replay |
| security | `py -3.12 -B -m pytest tests/security -q ...` | signature/path/ref/PII/secret/revocation |
| storage chaos | `py -3.12 -B -m pytest tests/storage_chaos -q ...` | process/kill/disk/fsync/collision/recovery |
| Windows security | `py -3.12 -B -m pytest tests/windows_security -q ...` | DACL/owner/junction/device/UNC；Windows required |
| MCP protocol | `py -3.12 -B -m pytest tests/mcp_protocol -q ...` | `isError`/schema/caps/cancel/backpressure |
| semantic mutation | `py -3.12 -B -m pytest tests/semantic_mutation -q ...` | 每个critical mutation独立被杀 |
| packaging | `py -3.12 -B -m pytest tests/packaging -q ...` | exact wheel/A-B build/clean install/negative imports |
| DSH formal | DSH pinned lock下运行其正式profile test命令 | delivery guard/bypass/general isolation |

所有 `...` 由 runner 展开成 `$R/tmp/<task>` 的 `--basetemp`、`-p no:cacheprovider`、JUnit JSON/XML output path，不依赖 shell alias。

### 18.3 Python/OS/构建矩阵

- Ubuntu：Python 3.11、3.12；contract、full、determinism、storage/security 子集、build/install。
- Windows：Python 3.11、3.12；contract、full、DACL/junction/device/long path、build/install。
- Node：H9批准版本；JCS oracle、DSH profile/bypass。
- 两个完全独立 archive 使用同 builder/locks/epoch；wheel bytes 必须一致。
- 每个发布对象在新 venv/container中从 wheel安装，不允许源码目录遮蔽 import。
- macOS 若继续宣称支持则增加等价 required runner；未验证前从支持矩阵删除，不保留模糊声明。

### 18.4 Positive result 最低条件

任何“系统完成”报告至少引用：

1. strict external `CaseRequestV4` bytes digest；
2.真实 resolver/source/fact/pack receipts；
3. provider invocation 和 independent checker receipts；
4. accepted formal result digest；
5. signed certificate digest；
6. completed AuditBundleV4 digest；
7. independent verify PASS；
8. offline replay exact match；
9. CLI/Client/MCP parity；
10. installed-wheel artifact digest。

单元测试、文件存在、MCP tools/list、wheel import、空 pack integrity 或 caller构造对象都不能替代这十项。

## 19. 全仓文件处置合同

### 19.1 原 90 个 `compiler_core/*.py`

以下五组恰好覆盖审计快照的 90 个 core files，是 B01 的初始处置输入，不代替最终 per-path receipt。CodeGraph 已用于发现真实调用边；每个删除相关结论仍须回读 exact source/AST、动态 import、入口和测试。Runner 按新 Git tree 更新路径，但不得让旧文件因新增模块而失去 disposition。

**KEEP_REWRITE（12）**：`__init__`、`application`、`audit`、`audit_bundle`、`canonical_serialization`、`cli`、`client`、`contracts`、`rendering`、`resources`、`rule_packs`、`version`。`rendering` 是被 CLI/Client 调用、只读 verified bundle 的 `RUNTIME_OUTPUT`，进入同一 production wheel；不得到达 evaluator。

**MERGE_DELETE（9）**：`argumentation`、`argumentation_v2`、`backend_router_v1`、`certificate_v1`、`evaluator`、`fact_admission_v1`、`independent_grounded_checker`、`legal_spec_ivl`、`source_service_v2`。正确逻辑进入第5节无后缀目标模块；其中 `independent_grounded_checker→independent_checker`，旧path在W5删除。

**MIGRATE_INVARIANTS_THEN_DELETE（29）**：`admission`、`certificate_checker`、`completion_status`、`config_paths`、`constraint_validator`、`contracts_v4`、`defeasible_priority`、`domain_config`、`evidence_chain_validator`、`fact_trust_envelope`、`g8_evaluator_patch`、`horn_completeness`、`jcs`、`legal_ir_v3`、`litigation_engineering`、`output_firewall`、`proof_trace`、`reasoning_boundary`、`rule_governance`、`rule_router`、`source_anchor`、`source_manifest`、`stratified_evaluator`、`taint`、`transformer`、`trust_labels`、`type_checker`、`types`、`validity_state_machine`。删除前必须有对应 V4 invariant target 和 RED→GREEN required test。`domain_config` 的吞异常/global fallback不得迁移；`g8/horn` 迁 completeness/TRUNCATED/witness；`legal_ir_v3` 迁 typed IR/source/type checks；`litigation_engineering` 先把 certificate label witness和 accepted必须可独立复验迁入 `certificates.py`，其策略内容归 source tool；`rule_governance` 把 deterministic verify/admission迁入 runtime、人工报告归 source tool；`transformer` 不迁 runtime auto-patch，只迁 signed rule domain/scope 显式校验和负向测试。

**NONPRODUCTION_SOURCE（38）**：`adapter_base`、`adjudication_draft`、`analysis`、`arbitration_reasoning`、`banach_verifier`、`breakthrough_candidates`、`breakthrough_verification`、`burden_of_proof`、`classifier`、`compliance_monitoring`、`conflict_of_laws`、`criminal_complexity`、`criminal_sentencing`、`cross_jurisdiction_compare`、`cross_jurisdiction_router`、`evidence_checklist`、`evidence_evaluation`、`grounded_smt_verifier`、`incremental_grounded`、`invariance_metrics`、`ip_valuation`、`kg_recall`、`legal_memory`、`legal_reasoning`、`plugin_registry`、`prc_collision_engine`、`proof_trace_visualizer`、`proof_tree`、`result_diff`、`result_exporter`、`review_packet`、`rule_lookup`、`rule_platform_cn`、`smt_sidecar`、`spec_shadow_harness`、`step_verifier`、`training`、`universal_grounded_smt`。这不是“统一外迁”或“零 caller 即删”：`analysis/training/rule_lookup` 先断公共入边后进入同仓 source tool或删除重复实现；`breakthrough_verification/grounded_smt_verifier/invariance_metrics/spec_shadow_harness/universal_grounded_smt` 固定为 TEST_ORACLE/semantic mutation/differential目标；`adapter_base/plugin_registry/prc_collision_engine/proof_tree` 与 addons/TriRail 作为动态连通实验分量处置；领域 toy code 必须先映射到 `cn-official` typed rules/fixtures、DSH advisory consumer或证明无相关语义，才可删除。

**DELETE_CURRENT（2）**：`compat_v3_v4`、`proleg_translator`。历史由 Git 和 V3 artifact 保存，不提供 current runtime 替代；仍须有 V3 payload负向拒绝和历史 locator。

CodeGraph 在本基线确认的高风险边必须进入 B01 receipt：`render_run←CLI/JCClient`；`analyze_strategy|analyze_similar_cases←CLI/WorkBuddy MCP`；`audit_pack←CLI`；`export_corpus_pack←CLI`；`lookup_rules←WorkBuddy MCP`；`litigation_engineering.generate_certificate←application._evaluate_once`；函数内 `transformer.auto_patch←FixpointEvaluator.__init__`；`spec_shadow_harness` 动态加载 companion spec；`plugin_registry` 动态加载 addons。CodeGraph 的同名方法误连或空 callers 不能覆盖源码事实。

新增 formal modules：`trust.py`、`artifact_store.py`、`source_service.py`、`fact_admission.py`、`legal_ir.py`、`backend_router.py`、`certificates.py`、`mcp.py`、`backends/**`。它们必须进入 authority和wheel exact allowlist。

### 19.2 其他目录

| 路径 | 处置 | 机器证明 |
| --- | --- | --- |
| `addons/workbuddy_mcp.py` | 协议壳有用部分迁 `compiler_core/mcp.py` 后删除 | 旧import失败，formal MCP四工具E2E |
| `addons/cn|hk|us|federation/**` | 同仓 `EXPERIMENT_ONLY`；CN adapter在W5-02C移除legacy rules/default registry绑定，其余可保留或必要时仓内归位，不建 distribution | 动态 plugin、blob/license/consumer守恒；CN无rules path；formal wheel无addons |
| `pipeline/**` | 同仓 `SOURCE_TOOL`；保留离线入口，确认 formal 入边为零；W5-02C删除`fix_single_premise.py`原地覆写器，不建 distribution | 离线入口和tests有处置；不存在legacy rules再生路径；formal import/network/RECORD/SBOM均无pipeline |
| `configs/zh_CN/rules.yaml`、`configs/packs/cn-legacy-corpus/**` | W5-02C按`DELETE_CURRENT/HISTORY_BOUND`从current tree删除，不另建archive/artifact，不进入`cn-official`；因冻结tag/Git blob继续保存bytes，复杂度分账记`relocated_or_rebuilt.history_bound_current_tree_removal`，不记whole-system真删 | exact hash/bytes/21,144 unique IDs和Git locator冻结；文件、pack ID、全部current consumers为0；回植mutation失败 |
| 其他 legacy/candidate configs/packs | 同仓 `CANDIDATE_ASSET`；默认保留现有路径，不为整洁搬大文件 | blob SHA-256、byte/record/provenance/license/status对账；formal registry不发现 |
| `configs/packs/cn-official/**` | 空模拟目录退出runtime；同仓 build-only pack source产生独立签名 artifact | engine wheel无pack，active pack有签名/digest |
| formal ontology/domain/config | 进入signed pack并绑定run | missing/corrupt config blocked |
| neutral render profile | 随 `compiler_core.rendering` 进入同一 production wheel | 只消费 verified bundle；result digest不依赖renderer |
| `schemas/jc-v3*`,`schemas/w1b/**` | W5-CUTOVER删除 | source/wheel/installed negative gate |
| `schemas/jc-v4.schema.json` | 小型 emitter 发布物 | emitter diff=0和differential PASS |
| `mcp_manifest.json` | 小型 emitter 发布物；runtime不读取仓库文件 | ToolSpec/runtime tools-list/committed bytes一致 |
| `mcp_server.py` | V4 formal thin launcher | installed stdio/dev及production transport lifecycle |
| `tools/build_rule_pack_manifests.py`及专属test | V3 builder删除；synthetic仅保留一个test helper，W8按正式pack合同重新实现同仓build-only工具 | 旧path/import为0；两次archive build pack bytes相同；builder commit/digest进入provenance |
| `tools/build_provenance.py` | W6重写 | exact source/spec/wheel/schema/tool/lock/trust binding |
| `tools/wheel_gate.py` | 唯一薄 positive-set gate；由module authority可发布class推导expected set | RECORD集合等式、无`FORBIDDEN` blacklist、no-git archive PASS、任意注入FAIL |
| `tools/supply_chain_gate.py` | 全wheel/locks/license/SBOM | zero unhandled blocker |
| perf tool | installed V4 + signed pack | approved budget report |
| tri-rail/fast-path tools | 同仓 `EXPERIMENT_ONLY`，不建 package/release/deployment；W5-02C删除TriRail的`PRC_CN` corpus digest/consumer并把PRC实验限为CBL+SPC | formal distribution/import graph无它们；legacy corpus path/pack/digest为0；与addons分别按真实图处置 |
| V3/W1b tests/fixtures | 语义迁V4 tests后删除 | information-conservation manifest + negative imports |
| skipped/root test scripts | 改为required pytest或退出coverage叙事 | CI collection/skip gate |
| `requirements/*.lock` | H6批准后全transitive hash | clean/offline require-hashes |
| workflows | W6重写 | required jobs + build-once promote-same-digest |
| README/HANDOFF/AGENTS/memory/CHANGELOG/docs | W6重写current state | path/command/version/authority validator |
| `pyproject.toml` | exact formal distribution/entrypoints/version metadata | METADATA/RECORD/allowlist |
| LICENSE/NOTICE/SECURITY/CODEOWNERS | 保留MIT并补完整治理/notice | wheel/SBOM/remote evidence |
| `.codegraph/**` | 本机 ignored 可重建索引，不提交、不入wheel | version/status、normalized graph receipt、tracked coverage对账 |
| `remediation/v4/**`、`tools/remediate_v4.py` | 施工期 BUILD_ONLY；Z02封存后转 HISTORY_ONLY | final archive digest、receipt chain、runtime/current-authority negative gate |

### 19.3 删除门禁

删除一个 path 前 runner 必须先证明：CodeGraph 已与 exact tree 同步；import/call/instantiate候选边经源码AST、动态 import、入口和测试复核；consumer graph无未处置消费者；删除项非用户未提交内容且位于 task allowlist。随后 `--deletions-ready` 按 B01 的三种互斥终态分支验证：只有 `MIGRATED_GREEN` 要求 target module/commit和RED→GREEN target test；`HISTORY_BOUND` 要求 frozen bytes/hash/locator、current negative rejection且target module为空；`NO_RELEVANT_SEMANTICS_APPROVED` 要求 symbol inventory、动态consumer复核、H5具名审批和negative import/path gate。独立 oracle 还必须不调用 production implementation，内容资产必须完成 blob/byte/record/metadata/consumer 守恒。consumer=0、callers=[]、impact=0、文件有Git历史或普通H5签字均不能单独授权删除。少一项 exit 6。

### 19.4 复杂度和依赖三本账

Runner 对 start/final tree 输出：独立总账 `repo_tree{added,deleted,net}`，以及处置分账 `relocated_or_rebuilt{source,destination_receipt,subtype}`、`true_deleted{code,tests,assets,docs}`。以 `git diff --numstat` 逐 path 和 disposition 对账，Python 与 YAML/JSON资产分开；baseline 删除 path 必须在两类处置分账间恰好归类一次且交集为0，modified-in-place numstat 只计入 `repo_tree`，不得从两类 path 行数反推 `repo_tree.deleted`；替代实现新增量必须扣除。`HISTORY_BOUND`内容若仍由冻结tag/Git blob保留，必须记入`relocated_or_rebuilt`的`history_bound_current_tree_removal`子类并以tag/blob receipt为destination，不能记`true_deleted`或whole-system净减。LOC只用于解释，不作为 PASS。依赖同时输出 `jc_direct_removed|moved_to_source_tool|ecosystem_removed`；移动、重建的代码或依赖不得计为 whole-system 删除。

## 20. Version、artifact 和 readiness

### 20.1 身份等式

```text
source version
= wheel METADATA version
= package __version__
= CLI capabilities version
= MCP serverInfo.version
= RunIdentityV4 engine_version
= release tag version
```

运行身份还必须绑定 source commit/tree、wheel、Schema、ToolSpec、locks、pack、trust policy、algorithm/backend、storage policy digests。

### 20.2 RC 不是 stable artifact

`4.0.0rcN` 与 `4.0.0` 的 METADATA、wheel filename和runtime identity不同。W8不得把RC wheel改名或重打tag。稳定版必须在唯一`4.0.0` commit重新build，并对该exact digest重跑双build、clean install、全测试、SBOM、provenance、attestation、storage/ops、真实pack E2E，然后tag/release同一digest。

### 20.3 Health/readiness

- `health=true`只表示进程可服务探针。
- `kernel_ready=true`要求approved V4 build、Schema/ToolSpec、synthetic mechanism gates、state/limits/locks都通过。
- `legal_production_ready=true`还要求active signed `cn-official`、有效trust/keys、真实法律领域E2E和未撤销状态。
- DSH formal profile readiness还要求JC service独立身份/transport和delivery guard。
- readiness每次动态重算，不是manifest bool；pack/key/storage撤销立即改变。

## 21. Z00-Z03 最终收口

### Z00　全问题和全文件复算

`issue-map --check` 必须 44/44 closed；CodeGraph 对 final tree重新 full index，pending/mismatch/error/unresolved为0，normalized graph与AST/dynamic-import supplement对账；`file-map --check --all-tracked` 对最终tree missing/extra/duplicate为0；authority graph无禁边；required skip/critical mutation survivor为0。W5-02C `HISTORY_BOUND` receipt必须复验，CN legacy corpus物理/tracked path、pack ID和current consumers均为0。输出 19.4 的仓库、迁移/替代、真实删除及依赖三本账，禁止把移动或 artifact 重建写成系统净减。

### Z01　全部 artifact 独立复验

从已发布位置或最终本地staging重新下载/读取：stable wheel、pack、checksums、SBOM、provenance、attestations、Schema、ToolSpec、Kernel/Legal/DSH evidence。验证签名、digest、subject和撤销，再在clean环境跑一个真实formal+verify+replay和DSH guard。

### Z02　Git和外部状态终检

- remediation branch所有task receipts对应可达commits；工作树/暂存区clean；
- 每个commit只含任务allowlist；无用户源工作树内容；
- 原源工作树两份删除仍原样存在且未被提交；
- 无私钥、token、原始客户材料、绝对路径进入Git/wheel/release；
- remote writes与HUMAN_GATE授权精确一致；
- 冻结 tasks、issue-map、final file-disposition、normalized CodeGraph、全部 receipt chain 和 semantic migration mapping，生成 canonical archive manifest/digest并存入批准证据位置。封存后这些施工台账转 `HISTORY_ONLY`，不得要求未来日常维护旧迁移图；`module-authority.json` 仍是 current policy。

### Z03　唯一完成输出

Runner exit 0并输出一个`final-remediation-result.json`，只引用原始receipt/report/artifact digests，顶层状态由verifier重算。至少包含：start/final commit/tree、44项closure、final tracked disposition、semantic migration closure、CodeGraph/施工台账 archive digest、W5-02C legacy corpus identity/consumer-closure/history locator receipt、test/CI runs、stable wheel、official pack、engine/pack/trust/storage identity、formal run/certificate/bundle/verify/replay、DSH bypass evidence、known limitations、revocation/rollback handles，以及 `repo_tree|relocated_or_rebuilt|true_deleted`、`jc_direct_removed|moved_to_source_tool|ecosystem_removed` 分栏。migration ledger不是第二 current authority；13.6 MB legacy blob只从current tree移除且仍由冻结tag/Git blob保存，必须记为`relocated_or_rebuilt.history_bound_current_tree_removal`并绑定Git locator，`true_deleted.assets`对该path为0，不得写成whole-system净减。

## 22. 硬停止条件

出现任一项，runner exit 6或对应waiting code，禁止自动降级：

- 第二个contract/schema/ToolSpec/module registry/application/certificate issuer authority；
- formal consumer仍import V3/W1b/compat/advisory/candidate/旧evaluator；
- external payload能构造PASS、active、receipt、certificate或build identity；
- Python/Schema/MCP接受集不同、开放formal Mapping、旧digest grammar仍可入；
- translation loss、checker disagreement、UNDEC/candidate/unknown/taint能签formal；
- pack hash/parse/execute不在同一snapshot；
- run identity未绑定build，或返回旧digest+新对象；
- symlink/junction/DACL/durability/并发/kill/disk测试产生污染或不可恢复状态；
- MCP path、错误成功、资源无界、无verify闭环；
- wheel出现allowlist外文件、candidate、网络/规则工程、V3/compat；
- required test skip、critical mutation survivor、installed E2E/replay失败；
- tag/version/METADATA/wheel/provenance不同，或tag job重建artifact；
- production key/approval/release permission缺失却准备晋级；
- `cn-official`空/blocked/未签/未完整审核却准备legal-ready；
- DSH和JC同effective SID/UID/service principal，或任一路径/volume/broker使DSH可写JC state，或transport未认证；
- candidate资产无provenance/license/consumer对账就被删除或晋级。
- `configs/zh_CN/rules.yaml` fingerprint未先冻结、`USER_AUTHORIZED_HISTORY_BOUND` receipt缺失/签名或scope无效、发生漂移仍继续、文件/backup/manifest/pack ID/current consumer仍存在，或`cn-official`的formal inventory、source/candidate/coverage/review/build/provenance闭包依赖其path、digest、Git blob、pack ID、旧rule-ID映射或派生物；独立第一方法源建模中偶然出现相同命题/文本/ID本身不构成违规，但不得充当来源证明；
- CodeGraph缺失、未与exact tree同步、tracked code/asset coverage有缺口，或仅凭`callers=[]|impact=0|import=0`批准删除；
- 因LOC、目录大小或“非formal”创建无真实独立消费者的repo/distribution/service；
- source tools、experiments或candidate assets出现第二package/release/deployment metadata，或被production wheel/default registry/formal run自动发现；
- 为派生 Schema/ToolSpec/module graph/wheel set或单实现builder新增第二generator framework、registry、interface；
- 移动、重建的代码/依赖被计为whole-system deletion，或LOC成为PASS门禁。

## 23. 自动执行中的合理停机与恢复

| 状态 | 对用户输出 | 恢复 |
| --- | --- | --- |
| Test/implementation failed | task ID、完整命令、exit、错误摘要、attempt差异 | Agent在同task修根因后重跑唯一命令 |
| Plan drift | 新path/依赖/问题与当前DAG冲突 | 更新本方案/tasks.json并单独审批，不静默扩scope |
| WAITING_HUMAN | request path/digest、required roles、deadline | 放入已签approval，执行request中的resume command |
| WAITING_EXTERNAL | 缺失VM/HSM/remote/provider及验证条件 | 提供设施后同命令续跑 |
| Release unauthorized | exact commit/artifact digests和拟执行remote action | 签HUMAN_GATE-RELEASE后续跑 |
| All complete | final result、artifact digests、commit/status | 不再执行；后续变更创建新run |

Runner不得在状态未变化时反复生成新请求；相同subject复用同一request digest。审批过期或subject变化时必须生成新请求。

## 24. 可复制给编码 Agent 的唯一开工提示词

```text
你负责完整实施 Juris Calculus V4 单主链生产投产整治，不是做审计或写第二份计划。

唯一施工合同：
仓库根目录/20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md

问题基线：
仓库根目录/20260819_juris-calculus_V4单主链生产投产全量代码审计.md

启动后必须：
1. 完整读取两份文件、仓库 AGENTS.md 和 memory.md。
2. 不在用户当前脏工作树施工；按方案创建独立 v4-remediation branch/worktree，保护两份既有未暂存删除。
3. 先完成 B00 和 B00-CG：创建唯一 runner、machine DAG并对exact tree建立CodeGraph；函数/import/impact用图定位后回读源码，动态import和未入图大资产另行闭合。CodeGraph未通过不得进入B01处置。
4. 每次只改 task allowed_paths；先写失败测试，再修根因；gate全绿后由runner生成receipt和本地commit。
5. 不保留V3/W1b/compat/fallback；不以文件存在、空pack、caller PASS、单测数量或免责声明宣告完成。
6. 自动持续执行，不因任务困难、上下文压缩或普通失败停下；从外部state receipts恢复。
7. 只有runner返回WAITING_HUMAN/WAITING_EXTERNAL/RELEASE_UNAUTHORIZED时才停，并只报告request path、digest、所需角色/设施和唯一resume command。不得替代法律审批、生产密钥或发布授权。
8. 顺序严格为V4 Kernel RC、真实cn-official、DSH formal profile；通用DSH不得被JC强制。
9. 每完成一个task检查Git diff/status；不push、不tag、不release，除非exact HUMAN_GATE授权。
10. 最终只有Z03 verifier exit 0、44项闭合、全tracked disposition、stable wheel+official pack+formal verify/replay+DSH bypass evidence齐全时，才能报告全部完成。
11. 保持一个JC source repo和一只production wheel；非生产源码同仓隔离但不另发包；只有`cn-official`是独立签名pack artifact。零caller不等于可删，移动或重建不等于系统净减。
12. W5-02C必须按已授权fingerprint删除`configs/zh_CN/rules.yaml`和`cn-legacy-corpus` manifest，断开CLI、addon、config resolver、collision/TriRail、builder、pipeline、benchmark/test、CI、pack registry及wheel消费者；只能在历史证据中保留路径文字，禁止批量迁入`cn-official`。

现在从B00开始，随后必须完成B00-CG，持续执行到第一个真实外部门禁或Z03完成。
```

## 25. 本方案自身验收

方案交付时必须验证：

- W0-W9、B00、B00-CG、B01-B02、H5/H6/H7/H8/H9、Z00-Z03均有依赖和退出门禁；
- P0 15、P1 20、P2 7、P3 2全部映射；
- 原90个core modules五组数量合计90且不重复；其他目录每类有处置；
- CodeGraph覆盖全部可解析code/config，未入图资产由Git blob/byte/record inventory闭合；删除结论有源码/AST/动态入口复核；
- 所有删除候选terminal state非`UNREVIEWED`；shadow differential在最终required manifest；
- `configs/zh_CN/rules.yaml` exact fingerprint已以`HISTORY_BOUND`冻结后删除，`cn-legacy-corpus`及全部current consumer为0，回植mutation失败，`cn-official`无legacy来源绑定；
- module authority为人工政策、observed graph只验证；migration ledger已封存并退出current authority；
- source repo数量为1、production engine wheel数量为1；非生产源码无独立package/release/deployment metadata，`cn-official`作为独立签名pack artifact发布；
- 复杂度和依赖三本账分栏，移动或重建未计作whole-system deletion；
- 工程自动化和人工签发边界明确；
- 续跑、失败、commit、artifact、release和rollback不依赖口头状态；
- DSH general/formal边界及独立service identity明确；
- Stable 4.0.0重新build/test，不重标RC；
- 本次修订只提交本方案和项目memory；不立即删除legacy corpus或修改消费者，`.codegraph/**`、`.planning/**`均不提交，两份用户原有删除不纳入提交。

### [我违规之处]

- 无
