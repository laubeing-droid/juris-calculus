# Juris Calculus V4 生产运行闭环彻底整治施工方案

> **已归档：** 本文仅保留历史规划与施工上下文，不描述当前运行状态。当前信息见[状态页](remediation/v4/STATUS.md)与[文档索引](docs/README.md)。

日期：2026-08-24  
施工仓库：`D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation`  
本机生产状态：`D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-production-state`  
整治状态：`D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state`

## 0. 结论、纠错与方案效力

当前状态不是完整生产运行，只是：

```text
EFS state ready
+ local PIPL pack built
+ MCP tools/capabilities published
+ invalid request fails closed
- production ApplicationV4 composition
- case artifact intake
- valid evaluate/verify/read chain
- installed-wheel runtime
- real formal-profile consumer
- independent W9/Z verification
```

`LOCAL_PRODUCTION_ACTIVE`、W9 全完成、Z00-Z03 全完成等既有声明，由本方案统一降级为：

```text
PACK_READY + MCP_SHELL_READY + PRODUCTION_RUNTIME_MISSING
```

本方案是 2026-08-19 全自动整治方案的生产运行 plan-drift correction。此前已经有效闭合的 V4 kernel、规则包构建、EFS state 和本地授权不返工；H9/W9/Z 中把 capabilities、文件存在、空参数拒绝和重复 verifier 当生产完成的部分全部追加标记为 `INVALIDATED_BY_RUNTIME_GAP`。既有 receipt 只读保留，不删除、不改写、不伪造新摘要。

本轮不是 MVP、演示环境或“最小生产”。完成范围包括：公共案件输入、生产运行时装配、正式规则包消费、CLI/Python/MCP 三入口、证书和审计读取、正式 bridge 消费、installed wheel、EFS state、密钥最小权限、备份、升级、回滚、恢复、运行观测和独立最终验收。

## 1. Phase 1：前置假设与非目标

核心假设：当前 Windows 主机是唯一生产目标，当前用户已授权在指定 EFS 目录内运行本地生产，现有六条 PIPL 规则以 `LOCAL_AUTOMATED_OWNER` 身份直接投入观察生产。  
明确排除：不 push、不创建远程 tag/GitHub Release、不部署远程服务、不启用整盘 BitLocker、不虚构外部 DSH、法律 reviewer 或第二服务身份。  
最简但完整的实现：一个 installed wheel、一个生产 composition root、一个四工具 stdio MCP、一个正式 bridge、一个 EFS state root、一个生命周期工具；不增加第二法律执行主链。

### 1.1 无人值守一次跑完合同

- 唯一施工命令：`python -B tools\remediate_v4.py run --through Z10-03`。
- W10 与 Z10 全部为 `AUTO`，从代码修复、测试、迁移、EFS、种子导入、自动 owner 签发、激活、备份、恢复演练到任务计划注册一次连续执行。
- 当前授权已经覆盖本机生产目标、目录级 EFS、本地自动 owner、六条法律语义的机器生产验收和本地激活；不得再创建 `HUMAN_GATE`、reviewer、第二签发人、逐项 approval 或“是否继续”提示。
- 执行器对可修复的软件和环境错误自动诊断、修复并重试；不把报错转交用户处理。
- 终态只有两种：`exit_code=0 + LOCAL_PRODUCTION_ACTIVE`；或不可继续的真实机器故障对应非零退出与精确失败 receipt。后者不是授权门禁，再次运行同一命令必须从 receipt 续跑。
- 明确排除且仅排除：整盘 BitLocker、push、远程发布、外部 reviewer/DSH。它们不得影响本机生产闭环。

## 2. 完成定义

只有同时满足以下条件，才允许写 `LOCAL_PRODUCTION_ACTIVE`：

1. profile 设置真实 `JC_RUNTIME_FACTORY` 和 runtime config，且从 production venv 的 installed wheel 启动；不得依赖 repo cwd 或 `PYTHONPATH`。
2. 启动时完整读取、解码并验证 `cn-official-local-4.0.0` 的全部 artifacts；`RulePackVerifierV4.verify(pack_ref, current_time)` 返回 verifier-issued handle。
3. `ApplicationV4` 的 resolver、trust、source、fact、pack、IR、backend、checker、audit、certificate、signer、clock 全部由同一 production composition root 装配。
4. CLI、Python Client、stdio MCP 使用同一个 `CaseInputBundleV4` 合同；新案件的 source/evidence/fact artifacts 可实际摄取。
5. 案件 artifacts 只存在于单次 evaluation 的隔离 resolver overlay；不得永久混入规则包 resolver，不得跨案件残留。
6. 有效 PIPL 案件可完成 `jc_evaluate -> jc_verify_run -> jc_read_artifact`，返回正式证书的原始 bytes。
7. 六条 PIPL 规则逐条至少一个命中用例，且 review、missing、hypothetical、conflict、blocked、resource/cancel/error 边界均有真实运行门禁。
8. `jc-formal` bridge 实际读取 active profile、拉起 stdio server、比较 tools/capabilities pins、执行三步链并通过 delivery guard。
9. 生产运行从已构建 wheel 安装；wheel、lock、schema、ToolSpec、pack、trust、runtime config 和 storage digests 全部进入 `RunIdentityV4`。
10. service runtime 只读取 service signing key，不读取可派生 legal/build/release 角色的 master seed。
11. 当前 UTC 用于每次 evaluate、verify、read；不得使用 pack build 时冻结的 `verification_time` 代替运行时间。
12. W9 和 Z 各任务有独立目标、独立 command、独立 assertion、独立 report；Z 不得再次调用 W9 空壳 gate。
13. 安装、升级、回滚、备份、恢复演练成功；生产状态仍处于 EFS AES-256，未产生非 EFS 私钥或案件副本。
14. 整治 worktree clean，最终 runner exit 0，最终结果绑定实际 commit/tree/wheel/pack/run/certificate/bundle/verify/read digests。

以下项目不能再作为完成证据：

- 77/77、文件存在、schema 存在、manifest 存在；
- `jc_capabilities` 成功；
- 空 `{}` 调用 `jc_evaluate` 后 `isError=true`；
- pack_ref 出现在 capabilities；
- test-only synthetic vertical slice；
- report 自己写 `production_allowed=true`；
- 多个 task 复用同一 verifier，只改变 `task_id`。

## 3. 当前缺口和根因

| 编号 | 当前事实 | 根因 | 必须落地的修复 |
|---|---|---|---|
| R-P0-01 | profile 无 `JC_RUNTIME_FACTORY` | W9 只生成 capabilities manifest | installed production factory |
| R-P0-02 | `runtime_client()` 返回空 `JCClient()` | 未装配 Application/audit/context/output issuer | 完整 composition root |
| R-P0-03 | 新案件只有 refs，artifact 不可达 | resolver 仅进程内，入口只收裸 request | `CaseInputBundleV4` |
| R-P0-04 | pack_ref 只是 metadata | W9 未调用 pack loader/verifier | immutable pack import + current-time verify |
| R-P0-05 | evaluate 正向路径未测 | gate 只测空参数错误 | real PIPL positive chain |
| R-P0-06 | verify/read 未通过生产 MCP | 无 audit store/output handles | production MCP output issuer |
| R-P1-01 | profile 从 repo source 启动 | cwd/PYTHONPATH 指向 worktree | production venv + installed wheel |
| R-P1-02 | DSH adapter 只在 tests | W9-I00 明确不宣称部署 | 正式 `jc-formal` bridge |
| R-P1-03 | H9/W9/Z 重复自证 | route 按任务组调用同一函数 | task-specific verifier |
| R-P1-04 | trust verification_time 固定 | 复用了 build verification context | current UTC clock |
| R-P1-05 | runtime 若读 root seed 即拥有全部角色 | builder 从 master seed 派生六类 key | 独立 service key 文件 |
| R-P1-06 | engine 是 `4.0.0rc1`、pack 是 `4.0.0` | stable promotion 提前 | 全链通过后统一 4.0.0 |
| R-P1-07 | production-policy 写 daily backup 但无执行器 | policy 只是 JSON | lifecycle backup/verify/restore |
| R-P2-01 | 六条规则只覆盖 PIPL 13-18 | 当前授权范围和构建输入如此 | 明确 limited-domain，不冒充全中国法 |

## 4. 目标生产拓扑

```text
jc-formal / jc CLI / Python JCClient
              |
              v
       CaseInputBundleV4
  request + bounded case artifacts
              |
              v
   per-evaluation resolver overlay
              |
              +--------------------------+
              |                          |
              v                          v
 global verified pack artifacts   derived RunIdentityV4
              |                          |
              +------------+-------------+
                           v
                    ApplicationV4
 resolver -> trust -> source -> evidence/fact -> pack reverify
 -> IR -> backend -> independent checker -> result
 -> audit bundle -> certificate
                           |
            +--------------+---------------+
            |              |               |
            v              v               v
      run handle    certificate handle   result handles
            |              |               |
            +------ verify/read ------------+
                           |
                           v
              EFS jc-v4-state + audit bundles
```

权威边界：

- `ApplicationV4` 是唯一法律判断 sink。
- `production_runtime.py` 只负责装配、材料加载、每案上下文和 handle 签发，不复制法律规则。
- `formal_bridge.py` 只负责 MCP session、pin、调用顺序和 delivery guard，不解释法律语义。
- `tools/local_production.py` 只负责安装、验证、升级、回滚、备份和状态，不成为第二 runtime。
- `remediate_v4.py` 只负责施工 DAG 和 receipt，不进入日常生产调用图。

## 5. 公共案件输入合同

### 5.1 新增 `CaseArtifactV4`

字段固定为：

```text
artifact_id
content_ref
artifact_kind
media_type
scope
content_base64
```

约束：

- `content_ref.digest` 必须等于 decoded bytes 的 SHA-256；
- base64 必须 strict decode；
- `artifact_id`、ref、kind、media_type、scope 五项不允许重绑定；
- 不接收路径、URI 下载指令、UNC、device path、symlink 或任意宿主文件读取参数；
- 单 artifact、总 bundle、artifact 数量均由 `ResourceLimitsV4` 和 hard limits 双重限制；
- `content_base64` 使用字段级长度预算，不能通过放宽所有普通字符串上限实现；
- pack artifacts 与 case artifacts 引用相同但 metadata/bytes 不同，立即 `ARTIFACT_*_COLLISION`。

### 5.2 新增 `CaseInputBundleV4`

字段固定为：

```text
schema_version = jc/case-input-bundle/1.0
bundle_id
request: CaseRequestV4
artifacts: tuple[CaseArtifactV4, ...]
bundle_digest
```

`bundle_digest` 对排除自身的 canonical body 计算。bundle 必须包含 request 所有非 pack 引用的传递闭包：source bundle、source snapshot/structure/authenticity/provenance、evidence manifest、evidence item/document/custody、fact candidate/proposition/value/attestation、proposal 及其必要 receipt。pack 引用必须精确等于 active pack；调用者不能提交或覆盖 pack artifacts。

### 5.3 三入口统一

- `JCClient.evaluate()` 接受 `CaseInputBundleV4`，不再把裸 `CaseRequestV4` 当可独立执行的生产输入。
- `jc evaluate --input <bundle.json>` 读取同一 bundle。
- `MCPEvaluateInputV4` 改为唯一字段 `case_bundle`。
- 当前无人签发、运行时明确拒绝的 `request_handle` 从 4.0 正式合同移除；不保留不可达分支。
- MCP 工具数量仍为四个，不增加 upload/resource/path 工具。

## 6. 每案隔离 resolver

`ArtifactResolverV4` 增加 context-scoped overlay：

1. 启动时全局 resolver 只注册 production pack 和 trust 需要的公开 artifacts。
2. 每次 evaluate 先对 `CaseInputBundleV4` 做完整边界校验，建立 immutable overlay map。
3. overlay 与全局 pack map 合并为当前 ContextVar snapshot；不写 `_by_id/_by_ref` 全局表。
4. request bytes 和运行时派生的 RunIdentityV4 也进入本次 overlay。
5. `ApplicationV4.evaluate()` 的整个调用必须位于该 context manager 内。
6. 正常返回、异常、取消都在 `finally` 退出 overlay。
7. audit bundle 已封存运行所需 bytes，后续 verify/read 从 `AuditBundleStoreV4` 读取，不依赖残留 overlay。
8. 并发测试证明两个案件相同 artifact_id/不同 digest 不串扰；同一案件内部冲突仍拒绝。

不得采用：

- 把案件 artifacts 永久 `register_bytes()` 到全局 resolver；
- 每次案件重启整个 Python 进程来掩盖隔离问题；
- 把案件文件路径交给 MCP server 读取；
- 用清空 dict 的方式做脆弱的事后清理。

## 7. Production pack loader

新增 `compiler_core/production_pack.py`，只承担以下职责：

1. strict JSON 读取 `jc/local-production-pack/1.0` 和 `jc/local-production-trust/1.0`；
2. exact top-level fields、scope、production_allowed、signing_mode 校验；
3. 逐条 strict base64 decode 和 content_ref digest 校验；
4. artifact_id/ref/metadata/bytes collision 校验；
5. 构造 `TrustPolicyV4`、`TrustKeyV4` 和 `TrustVerifierV4(target_environment="production")`；
6. 构造 `SourceServiceV4`、`RulePackVerifierV4`；
7. 用当前 UTC 执行 `verify(pack_ref, now)`；
8. 校验 formal_rule_ids 与 verified manifest/rules 精确一致；
9. 校验 runtime identity 与 installed wheel/build/schema/tool/lock pins 精确一致；
10. 返回 typed、不可变的 loaded materials；不返回可修改 dict。

loader 不导入 `tools/build_local_production_pack.py`。builder 是 build-only；生产 loader 使用 `compiler_core` 内正式合同重新验证其输出。

## 8. Production runtime composition root

新增 `compiler_core/production_runtime.py`，并导出 `create_client() -> JCClient`。唯一外部输入是 `JC_RUNTIME_CONFIG` 指向的 EFS runtime config。

### 8.1 runtime config

`jc/production-runtime-config/1.0` 固定字段：

```text
release_id
state_root
pack_path
trust_path
service_key_path
runtime_manifest_path
engine_source_commit
engine_source_tree
engine_build_digest
wheel_digest
package_digest
schema_digest
tool_spec_digest
lock_digest
runtime_config_digest
algorithm_profile_digest
backend_profile_digest
storage_capability_ref
quota_bytes
max_case_bundle_bytes
max_case_artifact_bytes
max_case_artifacts
artifact_handle_ttl_seconds
service_issuer
case_scope_policy
```

config 位于 EFS release 目录，canonical JSON，安装后只读。运行时必须确认 config 自身 digest、所有引用文件 digest、state root 的绝对路径和 production root 前缀；拒绝环境变量覆盖单个安全字段。

### 8.2 composition 顺序

```text
load config
-> verify EFS/state/layout/material pins
-> load service private key only
-> load and verify pack/trust at current UTC
-> open V4TransactionStore
-> construct AuditTrustMaterialV4/AuditBundleStoreV4
-> construct SourceServiceV4/FactAdmissionServiceV4
-> construct LegalIRCompilerV4/BackendRouterV4
-> construct IndependentCheckerV4/CertificateIssuerV4
-> construct ApplicationV4
-> construct per-case prepare callback
-> construct MCP output-handle factory
-> construct replay executor
-> construct JCClient with capabilities
```

任何一步失败都阻止 server 完成 initialize，不允许退化为空 `JCClient()`。

### 8.3 current time

运行 clock 由 `datetime.now(timezone.utc)` 转为 canonical UTC，禁止：

- 使用 trust context 的 build `verification_time`；
- 使用 request 的 decision_time 代替签名校验当前时间；
- 缓存启动时刻给全部后续请求；
- 接受调用者传入 now。

### 8.4 service signer

- `identity/root.json` 只供 pack/build 生命周期工具使用。
- installer 从现有 master seed 按已冻结 HKDF profile 派生一次 service key，写入 `identity/service-runtime.json`。
- runtime 只读取 service key；文件位于 EFS 且 ACL 仅当前生产用户可读。
- runtime 不加载 source/legal/engineering/build/release 私钥。
- service key id、issuer、公钥必须与 trust context 中 service profile 精确一致。
- key rotation 生成新 release/config/profile，旧 audit bundle 仍由历史 trust materials 验证。

### 8.5 RunIdentityV4

每次请求由运行时构造，不接受 caller 字段。request_ref、source/evidence/fact/pack refs 来自 bundle；engine/build/wheel/package/schema/tool/lock/config/algorithm/trust/storage/backend 来自安装时 pins。生成后将 canonical digest body 置入本次 overlay，再交给 Application。

### 8.6 MCP output handles

成功或非错误业务结果写入 audit bundle后：

1. 从 store 生成 run capability；
2. 立即 `verify_run`，确认证书和 bundle 可读；
3. 为 `certificate.json`、`manifest.json`、`result.json` 和请求的其他正式 artifact 签发 bounded handle；
4. expiry 使用当前 UTC + config TTL；
5. `MCPEvaluateOutputV4.run_handle` 必须是可供 `jc_verify_run` 使用的 signed artifact handle；
6. handle 不包含 OS path；read 必须分页并执行 offset/length/max_bytes/expiry/scope/run binding。

## 9. 正式 bridge，而不是测试假 DSH

新增 `compiler_core/formal_bridge.py`，在 `pyproject.toml` 注册：

```toml
jc-formal = "compiler_core.formal_bridge:main"
```

本工作区没有真实外部 DSH runtime，因此当前交付名称和声明固定为“本机正式 bridge / DSH-compatible formal consumer”，不得写“外部 DSH 已部署”。bridge 必须是真实消费者，不是 test helper：

1. 从 `deployment/profile-registry.json` 解析唯一 active production profile；
2. 使用 profile 固定 venv python、module、cwd、environment；
3. 拉起 stdio MCP；
4. initialize、tools/list；
5. 调 `jc_capabilities` 并比较 engine/wheel/schema/tool/pack/trust/storage pins；
6. 调 `jc_evaluate(case_bundle)`；
7. 业务状态只有 `accepted_formal_result/formal_verified` 才进入 delivery；
8. 调 `jc_verify_run(run_handle)`；
9. 分页调 `jc_read_artifact(certificate_handle)` 到 EOF；
10. 比较 handle、verification、run identity、certificate ref、chunk digest 和完整 bytes digest；
11. 只在全部一致时输出 `JC_FORMAL_VERIFIED` 和正式 bytes；
12. server crash、timeout、cancel、工具漂移、capability 漂移、reconnect、isError、分页异常全部 fail closed；
13. stderr 只输出稳定错误码，不输出私钥、案件内容、绝对内部路径或 traceback。

现有 `tests/dsh_formal/jc_formal_adapter.py` 的 guard 逻辑迁移到正式 typed 实现；测试文件改为导入 production module，不保留第二套手写协议语义。

## 10. Installed-wheel 生产部署布局

```text
juris-calculus-v4-production-state/
  identity/
    root.json                         # build-only master; runtime 不读取
    service-runtime.json              # runtime 唯一私钥
  packs/
    cn-official-local-4.0.0.json
  trust/
    cn-official-local.json
  deployment/
    releases/
      <release_id>/
        venv/
        artifacts/
          juris_calculus-4.0.0-py3-none-any.whl
          checksums.json
          sbom.json
          provenance.json
        config/
          runtime-config.json
          runtime-manifest.json
          formal-profile.json
        evidence/
          install-report.json
          positive-chain.json
          recovery-report.json
    current.json
    previous.json
    profile-registry.json
  jc-v4-state/
  backups/
  operations/
    events.jsonl
```

`release_id` 绑定 commit/tree/wheel/pack/config digest，不用时间戳代替身份。`current.json` 和 `previous.json` 采用同目录临时文件、fsync、`os.replace` 原子切换；禁止目录 junction/symlink/reparse pointer。

profile 必须满足：

```text
command = <release>/venv/Scripts/python.exe
args = [-B, -m, mcp_server]
cwd = <release>
JC_RUNTIME_FACTORY = compiler_core.production_runtime
JC_RUNTIME_CONFIG = <release>/config/runtime-config.json
JC_RUNTIME_MANIFEST = <release>/config/runtime-manifest.json
PYTHONPATH absent
repo path absent
```

## 11. 唯一生命周期工具

新增 `tools/local_production.py`，只提供以下子命令：

```text
prepare     构建 wheel、release layout、service key、config/profile，不激活
verify      对指定 release 跑 installed-wheel positive/negative/recovery 门禁
activate    原子更新 current/profile registry
status      读取并复验当前 release，不写状态
backup      生成 EFS 内一致性备份并复验
restore     在独立恢复目录复验，不覆盖当前 state
rollback    切换到 previous 已验证 release
revoke      生成新 trust release，不原地修改 active materials
```

工具不承担法律求值，不复制 Application，不读取客户端私人目录。日常案件入口仍是 `jc-formal`、`jc` 或 Python API。

## 12. Phase 2：方案裁剪与 exact path 变更矩阵

### 12.1 新增生产代码

| exact path | 责任 |
|---|---|
| `compiler_core/production_pack.py` | production pack/trust strict loader |
| `compiler_core/production_runtime.py` | composition root、每案 prepare、RunIdentity、handle issuer |
| `compiler_core/formal_bridge.py` | 真实 stdio consumer 和 delivery guard |
| `tools/local_production.py` | prepare/verify/activate/status/backup/restore/rollback/revoke |

### 12.2 修改现有生产代码

| exact path | 修改 |
|---|---|
| `compiler_core/contracts.py` | `CaseArtifactV4`、`CaseInputBundleV4`、MCP evaluate input、resource limits |
| `compiler_core/artifact_store.py` | per-evaluation immutable overlay |
| `compiler_core/client.py` | bundle evaluation context manager、production handle/replay 接线 |
| `compiler_core/cli.py` | evaluate 读取 bundle，三入口一致 |
| `compiler_core/mcp.py` | 新 input schema、startup factory error、业务 isError 映射 |
| `compiler_core/version.py` | 最终全链通过后 `4.0.0` |
| `compiler_core/__init__.py` | 必要 public exports，不导出私钥/内部 loader |
| `mcp_server.py` | factory 初始化失败即进程非零，不回退空 server |
| `pyproject.toml` | `jc-formal` entry point、wheel exact package set |
| `schemas/jc-v4.schema.json` | 由 typed emitter 重生成 |
| `mcp_manifest.json` | 由 ToolSpec emitter 重生成 |

### 12.3 控制面和文档

| exact path | 修改 |
|---|---|
| `remediation/v4/tasks.json` | 新增 W10/Z10 corrective DAG |
| `remediation/v4/task.schema.json` | 如需允许 W10/Z10 assertions 字段则同步 |
| `remediation/v4/file-disposition.json` | 新文件和修改文件逐项登记 |
| `remediation/v4/issue-map.json` | 注册 R-P0/R-P1/R-P2 并绑定 closure tasks |
| `tools/remediate_v4.py` | 删除重复 W9/Z route，接新 task-specific gate |
| `tools/remediate_v4_verify.py` | 各 gate 的只读复验函数 |
| `.agents/skills/jc-formal/SKILL.md` | 从 test-local 改为 active production bridge 触发说明 |
| `README.md` | 真实 installed runtime、bundle input、jc-formal 命令 |
| `CHANGELOG.md` | 4.0.0 local production runtime closure |
| `20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md` | 加本 plan-drift correction 链接，不重写历史 |

### 12.4 新增/修改测试

| exact path | 目标 |
|---|---|
| `tests/contract/test_case_input_bundle.py` | bundle typed contract/canonical/schema |
| `tests/security/test_case_bundle_attacks.py` | base64/digest/closure/collision/limits/path attacks |
| `tests/security/test_artifact_resolver.py` | overlay 隔离、并发、异常清理 |
| `tests/integration/test_production_pack_loader.py` | 真实 local pack loader/current time/identity drift |
| `tests/integration/test_production_runtime.py` | 完整 composition 和 handles |
| `tests/formal_e2e/test_local_production_chain.py` | 六规则和状态矩阵 |
| `tests/mcp_protocol/test_production_stdio.py` | subprocess 四工具正向链和失败链 |
| `tests/dsh_formal/test_production_bridge.py` | active registry、pin、delivery、bypass |
| `tests/packaging/test_installed_production_runtime.py` | venv wheel、无 PYTHONPATH/repo import |
| `tests/storage_chaos/test_production_runtime_recovery.py` | crash/restore/rollback/old handle |
| `tests/formal_e2e/test_installed_production.py` | 从 capabilities smoke 升级为 full chain |
| `tests/formal_e2e/test_three_entrypoint_error_matrix.py` | 三入口改用 CaseInputBundleV4 |
| `tests/contract/test_python_schema_mcp_differential.py` | 新合同与 publication 一致 |
| `tests/dsh_formal/jc_formal_adapter.py` | 删除生产逻辑，最多保留薄测试 fixture 或整文件删除 |
| `tests/dsh_formal/jc-formal-profile.json` | test-only profile 保留并与 production profile 明确分区 |

### 12.5 tracked fixtures

```text
tests/fixtures/production/pipl/case-bundles/
  article-13-positive.json
  article-14-positive.json
  article-15-positive.json
  article-16-positive.json
  article-17-positive.json
  article-18-positive.json
  missing-required-fact.json
  disputed-review.json
  user-assumed-hypothetical.json
  conflict-certificate.json
```

tracked fixtures 只使用 test-only trust，不包含 production seed、production service key 或真实客户事实。真正 production acceptance 由 `tools/local_production.py verify` 在 EFS state 内生成等价无个人信息 smoke bundles，并用 local production identity 签名。

## 13. W10 corrective DAG

旧 H9/W9/Z task ID 和 receipt 不复用。新增 W10/Z10，避免 runner 因旧 receipt 显示 complete 而跳过真实施工。

```text
H8-07
  -> W10-00 correction/invalidation
  -> W10-01 case bundle contract
  -> W10-02 resolver isolation
  -> W10-03 pack/trust/key/time loader
  -> W10-04 production composition
  -> W10-05 CLI/Client/MCP publications
  -> W10-06 formal bridge
  -> W10-07 installed release prepare
  -> W10-08 real PIPL production E2E
  -> W10-09 operations/recovery/security
  -> W10-10 task-specific gate closure
  -> Z10-00 full repo/task recompute
  -> Z10-01 independent artifact/run reverify
  -> Z10-02 installed state/Git/ops final
  -> Z10-03 sole final result
```

所有 W10 任务为 AUTO。现有用户对本机 Windows、EFS、本地生产、不 push/不远程发布的授权已经明确；不再创建 reviewer、remote release、GitHub governance 或“是否继续”的门禁。

### W10-00　纠正旧生产完成声明

**Depends**：`H8-07`。  
**允许路径**：施工方案、`remediation/v4/**`、`tools/remediate_v4*.py`、外部 state 的 supersession evidence。  
**动作**：

1. 读取当前 H9/W9/Z receipts 和 `final-remediation-result.json`；
2. 生成 append-only `runtime-gap-supersession.json`，绑定旧 receipt digests、当前 commit/tree 和本方案 digest；
3. 将旧完成状态解释为 `INVALIDATED_BY_RUNTIME_GAP`，不编辑旧文件；
4. tasks.json 新增 W10/Z10；
5. issue-map 注册 R-P0-01..06、R-P1-01..07、R-P2-01；
6. runner 的 resume 逻辑必须优先识别 supersession，禁止旧 Z03 让 Goal 自动 complete；
7. 删除 `cmd_w9_local_deployment_gate` 和 `cmd_final_local_gate` 对多任务的共享路由，保留历史代码只会继续制造误判，因此直接替换。

**Gate**：

- 旧 receipt bytes/digests 不变；
- supersession 能从旧 final result 反查到全部被失效证据；
- `run --through Z10-03` 从 W10-00 开始，不跳到 complete；
- 不生成未来 task 的假 PASS report。

**提交**：`fix(remediation): invalidate shell-only production completion`。

### W10-01　冻结案件 bundle 和资源合同

**Depends**：`W10-00`。  
**允许路径**：`compiler_core/contracts.py`、schema/manifest publications、contract/schema tests、fixtures、任务/文件地图。  
**动作**：实现 `CaseArtifactV4`、`CaseInputBundleV4`；删除 MCP `request_handle`；为 bundle 数量、bytes 和字段级 base64 设定 hard/default limits；同步 typed registry、schema emitter、contract vectors 和 ToolSpec。

**Gate**：

- Python codec、JSON Schema、MCP input schema 三者 acceptance differential 为 0；
- canonical roundtrip bytes 完全一致；
- unknown fields、duplicate refs、digest mismatch、invalid base64、oversize、路径字段、pack override 全拒绝；
- MCP 仍精确四 tools；
- `git diff --check` 通过。

**提交**：`feat(runtime): add complete bounded case input bundle`。

### W10-02　每案 resolver 隔离

**Depends**：`W10-01`。  
**允许路径**：`compiler_core/artifact_store.py`、`compiler_core/client.py` 的 prepare contract、resolver/security tests。  
**动作**：实现 immutable overlay context；bundle closure 校验；request/run 临时注册；异常、取消、并发退出清理；pack/case namespace collision 防护。

**Gate**：

- sequential 100 cases 后全局 resolver 记录数不增长；
- 两线程相同 artifact_id/不同 bytes 各自得到正确结果；
- evaluate 抛异常后下一案件无残留；
- case 无法覆盖 pack ref；
- overlay 内 TOCTOU mutation tests 全杀；
- 不增加事后 dict 清空或全局 process restart 机制。

**提交**：`feat(runtime): isolate case artifacts per evaluation`。

### W10-03　生产 pack、trust、key 和 current-time loader

**Depends**：`W10-02`。  
**允许路径**：`compiler_core/production_pack.py`、`tools/local_production.py` 初始 key/config 部分、pack/trust/security tests。  
**动作**：实现 strict loader；把 builder 的验证逻辑迁为 production authority；创建 service-runtime key；current UTC 校验；installed identity pins；runtime 不读取 root seed。

**Gate**：

- 当前生产 pack 六条规则由正式 loader verify 成功；
- pack/trust/artifact/signature/config 任一 bit flip 失败；
- 把 verification_time 固定到 activation time 的 mutant 被 current-time test 杀死；
- service key 与 trust public key 匹配；
- runtime 测试监控文件访问，证明未打开 `identity/root.json`；
- expired/revoked/wrong-environment key 失败；
- loader 不导入 `tools.*` 或 tests。

**提交**：`feat(runtime): load and verify local production pack`。

### W10-04　完整 production composition root

**Depends**：`W10-03`。  
**允许路径**：`compiler_core/production_runtime.py`、Application 相关 integration/formal/security tests、runtime config fixture。  
**动作**：按第 8 节装配全部 V4 components；打开 EFS transaction/audit store；逐请求构造 RunIdentity；实现 receipt signer、replay executor、MCP handles、capabilities；factory 任一材料缺失时启动失败。

**Gate**：

- 直接 `create_client()` 返回配置完整的 `JCClient`；
- 一个 valid bundle 得到 formal result、certificate、bundle、run handle、artifact handles；
- `verify_run` 为 VERIFIED，offline replay semantic MATCH；
- certificate 分页 read 后 SHA-256 与 handle content_ref 一致；
- runtime config、wheel、pack、trust、storage pins 进入 RunIdentity；
- 空 factory、空 store、空 output factory、固定时间 mutant 全杀；
- 真实业务异常映射稳定 error code，stdout 无 traceback/path/private canary。

**提交**：`feat(runtime): compose the full V4 production application`。

### W10-05　三入口和发布物统一

**Depends**：`W10-04`。  
**允许路径**：Client/CLI/MCP/server、schema/manifest、entrypoint tests、docs。  
**动作**：三入口改用 CaseInputBundle；MCP server factory 启动失败 exit nonzero；修正业务 `isError` 状态矩阵；重生成 schema/manifest；更新 CLI help/README。

**Gate**：

- 同一 bundle 经 Python、CLI、stdio MCP 的 semantic result/certificate kind/run identity 一致；
- accepted/review/missing/hypothetical/conflict/blocked/cancel/resource/error 映射一致；
- MCP initialize 只有 factory 成功后才能返回；
- 无 `PYTHONPATH` 的 installed environment 正向运行；
- generated publication bytes 与 emitter 精确一致；
- legacy V3 或裸 CaseRequest 输入精确拒绝。

**提交**：`feat(entrypoints): run complete case bundles through V4`。

### W10-06　正式 bridge 和 active profile registry

**Depends**：`W10-05`。  
**允许路径**：`compiler_core/formal_bridge.py`、`pyproject.toml`、`.agents/skills/jc-formal/**`、DSH/formal tests、docs。  
**动作**：迁移 typed guard；实现真实 subprocess session；profile registry；pin/reconnect/page delivery；注册 `jc-formal`；test adapter 删除重复逻辑。

**Gate**：

- `jc-formal --input <bundle>` 实际拉起 production factory；
- tools/capabilities 任一 pin 漂移拒绝；
- evaluate 未 formal、verify 未 VERIFIED、read bytes 不一致全部拒绝 delivery；
- reconnect generation 必须重新 initialize/capabilities；
- general `jc` 不自动加载 formal profile；
- bridge 无规则、IR、backend 或法律判断复制；
- wheel exact-set 包含 bridge，不包含 tests/tools/private key。

**提交**：`feat(bridge): deliver verified formal artifacts from stdio`。

### W10-07　构建和准备 installed production release

**Depends**：`W10-06`。  
**允许路径**：lifecycle tool、wheel/packaging tests、pyproject/locks/docs、production state release 目录。  
**动作**：双构建 wheel；创建 release venv；从 exact hash lock 安装；生成 runtime config/manifest/profile；写 install evidence；不激活前先 verify。

**Gate**：

- 两次 clean build wheel bytes 一致；
- wheel METADATA/RECORD/LICENSE/exact set 合法；
- venv 无 editable install；
- 启动环境无 `PYTHONPATH`、repo cwd 和 repo import；
- capabilities wheel/package/schema/tool/lock digest 与 release files 一致；
- release 目录、key、config、state 的 EFS/ACL 检查通过；
- prepared release 失败不改变 current/previous/profile registry。

**提交**：`feat(deployment): prepare immutable local production release`。

### W10-08　真实 PIPL 生产 E2E 和激活

**Depends**：`W10-07`。  
**允许路径**：PIPL fixtures/tests、lifecycle verify/activate、production EFS evidence。  
**动作**：在 prepared installed release 上生成无个人信息 production smoke bundles；逐条命中 PIPL 13-18；跑状态矩阵；跑 bridge 正向链；验证完毕后原子 activate。

**Gate**：

- 第 13、14、15、16、17、18 条各一个 `accepted_formal_result`；
- missing fact -> `missing_required_fact`；
- disputed -> `review_only_result`；
- user assumed -> `hypothetical_result`；
- incompatible branches -> `conflict_certificate`；
- wrong pack/source/fact signature -> blocked/error；
- 每个 accepted run 都有 formal certificate、audit bundle、VERIFIED、semantic replay MATCH、完整 certificate read；
- bridge 只交付 accepted/formal/verified 的 exact bytes；
- current profile 指向 prepared release，previous 保留旧 shell-only deployment 但标不可回滚为生产 runtime；
- 生成 `positive-chain.json`，绑定 6 个 run digests 和全部 artifact refs。

**提交**：`test(production): prove the six-rule local formal chain`。

### W10-09　运行维护、备份、恢复、升级和回滚

**Depends**：`W10-08`。  
**允许路径**：lifecycle tool、storage chaos/performance/security tests、production operations evidence、docs。  
**动作**：实现 status/backup/restore/rollback/revoke；创建本机每日 EFS backup task；执行 crash/power-loss/partial install/rollback/restore 演练；记录资源预算。

**Gate**：

- `status` 只读复验 current release 和最近 positive chain；
- backup 在 EFS 内生成 manifest，逐对象复验；
- restore 只写独立恢复目录；复验成功且 current 不可用或 rollback policy 命中时由 lifecycle 工具原子切换，不询问用户；演练模式只复验不切换；
- partial release/install/profile write 不影响 current；
- rollback 只切换到有完整 verify evidence 的 previous release；
- state schema 不兼容时拒绝代码回滚，不强行降级数据；
- 旧 run handle 在允许期限和历史 trust 下仍可 verify/read；
- daily backup task 的 executable/config 指向 current registry，不硬编码 repo；
- daily backup retention 只清理 `retention_class=daily`、超过 30 天、`hold=false` 且 manifest 完整的备份；不删除 audit current state；
- quota、bundle size、并发、2500ms solver deadline 和 page limits 有本机实测报告；
- backup/operations logs 不含案件正文、私钥或绝对内部异常。

**提交**：`feat(operations): close local production recovery and rollback`。

### W10-10　逐任务 verifier 和 receipt 收口

**Depends**：`W10-09`。  
**允许路径**：runner/verifier、tasks/schema/file/issue maps、测试。  
**动作**：为 W10-00..09 各写独立只读 verifier；每个 report 绑定目标-specific evidence；不得用一个函数参数化 task_id 后返回相同结论。

**Gate**：

- 每项 command/assertion/report schema 不同且与 objective 对应；
- 删除或不可达旧共享 W9/Z gate；
- 把任一 positive run、profile、wheel、pack、backup evidence 替换为另一任务 report 时相应 gate 失败；
- attempt receipt 绑定 start/result commit/tree、argv、exit、stdout/stderr、changed paths、test/artifact digests、previous receipt；
- runner resume 从最新有效 W10 receipt 恢复。

**提交**：`fix(remediation): verify production closure task by task`。

## 14. Z10 独立终检

### Z10-00　全仓和控制面复算

独立执行：

- tasks schema、DAG、commands、allowed paths、assertions；
- issue-map 全注册项的 closure evidence；
- final tracked file disposition missing/extra/duplicate=0；
- CodeGraph 对最终 tree 强制 full index、SQLite `PRAGMA integrity_check=ok`；
- V3/legacy fallback、旧 profile active 引用、空 factory、repo-source production import 为 0；
- current docs、version、schema、ToolSpec、wheel、profile 口径一致。

Z10-00 不启动 production service，不读取 Z10-01 结果。

### Z10-01　artifact 和真实 run 独立复验

在新进程、installed wheel、无 repo/PYTHONPATH 环境中：

1. 读取 current release；
2. 重验 wheel/checksums/SBOM/provenance；
3. 重验 pack/trust/current-time；
4. 读取 W10-08 六个 run capabilities；
5. 对每个 run 独立 verify；
6. 至少一个 run 做 offline replay；
7. 对证书和 result handles 分页读完并复算 digest；
8. 重新运行一次 `jc-formal` production bundle；
9. 输出只含原始 evidence refs 的 `z10-artifact-reverification.json`。

Z10-01 禁止调用 W10 gate、禁止信任 W10 report 中的 `status=PASS`、禁止复用原运行进程对象。

### Z10-02　安装、Git、EFS、运维终检

验证：

- current/previous/profile registry 原子指针和 release identity；
- production process command 指向 venv wheel；
- repo working tree clean；
- 主工作树用户内容未改；
- EFS AES-256；
- service key ACL/EFS，runtime 无 root seed 访问；
- backup/restore/rollback/task scheduler evidence；
- no push/no remote tag/no GitHub Release；
- 本地生产局限明确为 PIPL 13-18、owner automated、observation required。

### Z10-03　唯一完成输出

Z10-03 只聚合 Z10-00、Z10-01、Z10-02 的原始 digests，不再次执行 W10。最终文件：

```text
D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state\evidence\final-production-runtime-result.json
```

必填字段：

```text
status = LOCAL_PRODUCTION_ACTIVE
scope = local-windows-efs-pipl-articles-13-18
start/final commit and tree
wheel/package/schema/tool/lock digests
runtime config and profile digests
pack/trust/storage refs
service key public identity
six positive run refs
certificate/bundle/verify/read refs
formal bridge evidence
backup/restore/rollback evidence
W10 receipt chain head
Z10-00/01/02 report refs
observation_required = true
independent_human_review = false
remote_release = false
push_performed = false
known_domain_limitations
recovery command
```

任一必填 evidence 缺失，status 必须是 `INCOMPLETE`，runner exit 非零；不得写 `BLOCKED` 来替代可修复的软件错误。

## 15. Phase 3：测试与验证设计

### 15.1 合同和 schema

- CaseArtifact/CaseInputBundle valid/invalid/canonical roundtrip；
- Python codec ↔ JSON Schema ↔ MCP ToolSpec differential；
- raw JSON duplicate key、float、depth、node、string/base64、array/member limits；
- V3、裸 request、request_handle、unknown field 全拒绝。

### 15.2 pack/trust/runtime

- 真实 local pack load；
- current time、expiry、revocation、wrong key/environment；
- runtime pins 和 file mutation；
- root seed access denial；
- service signer/receipt/certificate public verify；
- pack per-request reverify。

### 15.3 每案隔离

- sequential、parallel、exception、cancel、timeout；
- pack/case collision；
- same ref/same bytes idempotence；
- same ref/different bytes拒绝；
- overlay 不进入下一案件；
- bundle closure missing/orphan/extra policy。

### 15.4 真实业务状态

| 用例 | 预期 DecisionStatus | certificate |
|---|---|---|
| PIPL 13-18 六条正例 | accepted_formal_result | formal_verified |
| 缺必要事实 | missing_required_fact | none |
| 事实有争议 | review_only_result | none |
| 用户假设 | hypothetical_result | none |
| 规则/事实冲突 | conflict_certificate | conflict_verified |
| 来源/签名/pack 不合格 | blocked | none |
| 超资源 | engine_error/resource_exhausted transport mapping | none |
| cancel | cancelled transport mapping | none |

### 15.5 三入口和 bridge

- Python/CLI/MCP semantic parity；
- stdio framing、initialize once、tool list、capability pins；
- subprocess crash/reconnect/generation；
- bridge verify/read exact bytes；
- bypass、tool hiding、fake isError、stale receipt、old capability、page splice attacks。

### 15.6 installed production 和运维

- double-build reproducibility；
- clean venv install；
- no repo import；
- prepare failure atomicity；
- active pointer atomicity；
- backup manifest；
- independent restore；
- rollback compatibility；
- power-loss/corruption/quarantine；
- EFS/ACL/task scheduler postcheck。

## 16. 施工验证命令

开发波次先窄后宽：

```powershell
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\contract\test_case_input_bundle.py tests\security\test_case_bundle_attacks.py
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\security\test_artifact_resolver.py tests\integration\test_production_pack_loader.py
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\integration\test_production_runtime.py tests\formal_e2e\test_local_production_chain.py
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\mcp_protocol tests\dsh_formal
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\packaging\test_installed_production_runtime.py tests\storage_chaos\test_production_runtime_recovery.py
python -B tools\remediate_v4.py generated --check
python -B tools\remediate_v4.py verify-wave W0-04
python -B -m pytest -c tests\pytest.ini -q -p no:cacheprovider tests\
git diff --check
```

生产 release：

```powershell
python -B tools\local_production.py prepare --state-root "D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-production-state"
python -B tools\local_production.py verify --release <release_id>
python -B tools\local_production.py activate --release <release_id>
python -B tools\local_production.py status
<production-venv>\Scripts\jc-formal.exe --input <production-smoke-bundle>
python -B tools\remediate_v4.py run --through Z10-03
```

`prepare` 输出 release_id 后，后续命令必须使用该 exact id；不得使用“latest”目录猜测。

## 17. 安装、升级、回滚和恢复规则

### 17.1 首次安装

1. 自动校验 worktree clean 和 current production state EFS；
2. 双构建 wheel并复验；
3. 创建未激活 release；
4. 从 exact lock 安装 venv；
5. 生成 service key/config/profile；
6. installed full-chain verify；
7. 写 positive-chain evidence；
8. 原子 activate；
9. bridge postcheck；
10. 创建每日 backup task并立即手工执行一次。

### 17.2 升级

- 每次升级创建新 release，不原地修改 active venv/config/profile；
- pack-only、trust-only、code-only 更新都产生新 release identity；
- current release 继续服务，直到 prepared release 全部 verify；
- activation 只切 pointer；
- 激活后 bridge postcheck 失败立即回前一已验证 release，但不回退 state schema。

### 17.3 回滚

- 只允许回滚到 `previous.json` 指向且存在完整 verify evidence 的 release；
- 旧 shell-only profile 没有 runtime evidence，不能成为可回滚生产 release；
- 若新版本已执行不可逆 state migration，rollback 必须拒绝并走 restore-to-new-release，不做数据降级；
- 回滚后重新 capabilities、positive chain、verify/read。

### 17.4 备份和恢复

- backup 与 audit store writer 使用同一 storage lock/一致性边界；
- backup 包含 marker、objects、audit bundles、capability key、runtime/trust/profile identity manifest；
- 私钥备份只留在 EFS，manifest 不回显 seed；
- restore 永远先到新目录，执行完整 store/layout/object/audit verification；
- 只有恢复验证成功才允许执行自动 activation transaction；失败时保持 current 不变并进入自动修复与重试；
- 当前目录不做就地覆盖恢复。

## 18. 观测与生产状态

`operations/events.jsonl` 每行只记录：

```text
event schema
UTC time
release_id
operation
result status
stable error code
run identity digest if applicable
duration bucket
bytes/count budget
```

禁止记录：案件正文、证据内容、bundle JSON、私钥、完整绝对异常路径、traceback。stdio stdout 只属于 MCP JSON-RPC；任何日志写 stderr 或 operations file，不能污染协议。

`status` 的事实层级：

```text
INSTALLED          wheel/config/profile 存在并复验
RUNTIME_READY      factory + pack + storage 启动成功
POSITIVE_VERIFIED  当前 release 有 valid evaluate/verify/read
BRIDGE_ACTIVE      active registry + jc-formal postcheck 成功
LOCAL_PRODUCTION_ACTIVE = all four
```

## 19. 安全边界

1. EFS 是当前批准的 at-rest 边界；不增加 BitLocker 要求。
2. runtime 不读 master seed；service key 与 pack signing roles 分离。
3. MCP 不接受 path、URL、UNC、device、pipe 或任意文件读取指令。
4. case bundle 有字段级和总量限制；解码前后都计数。
5. pack materials 启动时验证，每请求按 current time reverify；active bytes 不原地更新。
6. audit handles 绑定 run/artifact/scope/expiry/max bytes/signature。
7. bridge 对 capabilities/tool pins/reconnect generation fail closed。
8. 本机当前用户同时拥有 bridge 和 JC 进程，不能宣称独立 OS identity；当前安全声明只限“DSH-compatible bridge 不直接写 JC state API，state 由 EFS/ACL 保护”。
9. 不虚构认证远程 transport；当前 transport 明确是 local stdio child process。
10. 生产 smoke bundle 不含真实个人信息；真实案件由用户后续输入，审计和 retention 按 production policy 执行。

## 20. 版本和发布口径

- W10-00..09 开发期间保留 `4.0.0rc1` 或顺序升级 rc；
- 只有 W10-08 installed production positive chain 和 W10-09 recovery 全绿后，才改 `compiler_core/version.py` 为 `4.0.0`；
- 改版本后必须重新双构建、安装、全测试、production E2E、SBOM/provenance 和 Z10；
- pack `cn-official-local-4.0.0` 与 engine `4.0.0` 独立 digest，但 RunIdentity 同时绑定；
- 对外口径固定为“本机 PIPL 第 13-18 条观察生产”，不是全量中国法、不是远程发布、不是独立双 reviewer 法律产品。

## 21. 回滚点和提交边界

每个 W10 task 一个本地提交。发现错误时只 revert 当前未进入后续依赖的原子提交；禁止 `reset --hard`、rebase 改写既有历史或把旧 V3/空 runtime 恢复为生产链。

| 波次 | 安全回滚点 |
|---|---|
| W10-00 | supersession receipt；旧 bytes 不变 |
| W10-01 | 新合同提交前的 rc1 schema/tool publications |
| W10-02 | bundle 合同可保留，overlay commit 可独立 revert |
| W10-03 | 当前 pack/trust bytes；不改 active profile |
| W10-04 | production factory 尚未被 profile 激活 |
| W10-05 | old CLI/MCP contract 仅限未发布 rc history |
| W10-06 | bridge 未激活前可删 prepared entrypoint |
| W10-07 | prepared release 可删除；current 不变 |
| W10-08 | previous verified release pointer |
| W10-09 | operations功能可逐子命令回滚，state 不降级 |

## 22. 硬失败条件

遇到以下任一项，当前 task 必须失败并自主修复，不得写 PASS：

- production profile 无 factory/config 或仍含 `PYTHONPATH`/repo cwd；
- runtime factory 返回缺 Application/audit/output factory 的 client；
- valid case bundle 无法进入 resolver；
- active pack 只在 capabilities 出现、未被 verifier 加载；
- runtime 打开 root master seed；
- 使用固定 build verification_time 作为运行 current time；
- accepted result 没有 formal certificate、bundle、verify/read；
- bridge 没有真实 subprocess 调用；
- production E2E 只运行 test-only pack/key；
- W9/Z 多任务继续共用同一报告逻辑；
- installed runtime 从 repo import；
- release verify 失败仍更新 current；
- backup 未复验、restore 就地覆盖或 rollback 指向 shell-only release；
- EFS 关闭、私钥复制到非 EFS、stdout 泄露日志；
- 为了过 gate 写死状态、计数、digest 或 expected output。

## 23. 唯一恢复命令

施工中断后：

```powershell
$env:JC_REMEDIATION_STATE_ROOT='D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state'
python -B tools\remediate_v4.py run --through Z10-03
```

runner 从最后一个仍绑定当前 input receipts、commit/tree、assertions 和 artifacts 的 W10 receipt 恢复。production current release 状态由 `python -B tools\local_production.py status` 单独复验，不由 runner 猜测。

## 24. 最终交付物

仓库：

- 完整 production runtime/pack/bridge/lifecycle code；
- CaseInputBundle 合同和 generated publications；
- 全部 W10/Z10 tasks/verifiers/tests/docs；
- `4.0.0` installed-wheel source commit。

生产 state：

- EFS service key；
- immutable current/previous releases；
- active profile registry；
- 六规则 positive chain；
- certificate/bundle/verify/read artifacts；
- backup/restore/rollback evidence；
- final production runtime result。

交付报告必须给出：最终 commit/tree、wheel/package/schema/tool/lock/config/profile/pack/trust/storage digests、测试命令和 exit codes、六个 positive run refs、bridge evidence、EFS/backup/rollback状态、已知领域限制和唯一恢复命令。

## 25. 本方案自身验收

- 覆盖了此前反查的全部五类缺口：runtime factory、pack consumption、valid E2E、DSH/bridge consumer、独立 gates；
- 没有把方案缩成补环境变量或单个 smoke；
- 没有新增第二法律执行主链；
- 公共输入能携带真实案件 artifact 闭包且无 path 输入；
- 每案隔离、密钥最小权限、current time、installed wheel、备份恢复均有施工和测试；
- W10/Z10 依赖、exact paths、验证、提交和回滚均已定义；
- 本机授权与不 push/不远程发布/不启用 BitLocker 边界保持一致；
- 最终完成证明是有效业务运行和独立复验，不是标签、文件、计数或空参数错误。
