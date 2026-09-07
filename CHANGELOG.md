# Changelog

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
