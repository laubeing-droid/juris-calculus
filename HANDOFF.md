# juris-calculus 交接检查点

## 当前检查点（2026-09-11，jc-business-root/1 第一批落地）

- 第一批业务能力已进入唯一正式主链：`compiler_core/business_root/`（solver/checker/analytics/delivery checker，独立校验）+ `CaseRequestV4.business_tasks_v1`（省空扩展，旧请求规范摘要逐字节不变）+ Application 业务阶段 + verify-only `verify_business_delivery`/`business_delivery_documents` + `business_capabilities()`。全部为条件模型分析，`formal_evidence` 如实为 kernel 待证；未关闭清单见 [docs/ulm-consolidated/IMPLEMENTATION_HANDOFF.md](docs/ulm-consolidated/IMPLEMENTATION_HANDOFF.md)。
- 契约与样例：[docs/contracts/BUSINESS_ROOT.md](docs/contracts/BUSINESS_ROOT.md)、[examples/harness/sample_local_business.py](examples/harness/sample_local_business.py)；测试 `tests/contract/test_business_root.py`、`tests/local/test_business_root_local.py`、`tests/packaging/test_business_wheel_install.py`（BC12 仓外 wheel 安装）。
- 数学权威仍在 LMM：BusinessRoot Lean 的 kernelChecked 证据以其 GitHub CI 为准，本批不取得（J00 基线登记见施工报告）。

## 上一检查点（2026-09-08，5.0.1 最终整改完成）

- 5.0.1（源提交 `6d1a621`）：分支身份结构化编码、查询反驳 argument→conclusion→refutes 语义与结果合同、incomplete 全链 typed obligation、priority 登记策略参与 defeat / 未支持阻断完整性（不签发证书）、真增量 Horn 默认启用（父状态经密封审计包跨实例复用，solver/checker 工作量分别计量）、程序四路公开可达（授权仅由 trust 校验的存档法律签章产生）；新增封闭 Harness 集成合同与三份可运行样本（`examples/harness/`）。
- 本地全量验收：Python 3.11.9 与 3.12.10（Windows）各 **1770 passed, 0 failed**；CI run 34171706216 四矩阵（Windows/Ubuntu × 3.11/3.12）+ A-B build/installed wheel/release evidence 全绿；installed-wheel E2E 67 用例 0 失败（本地 3.11 与 CI 各一份）；独立 profile oracle 复跑 PASS（531 图 × 4 语义 2,124 次对拍 0 不一致、16,660 次错误族注入全部拒绝）。
- CI 候选 wheel `juris_calculus-5.0.1-py3-none-any.whl`：sha256 `802d045a548c9101c0425cccda306cfc467832698e0b4e11b82c7071c2e32d99`（A/B 字节一致；本地 Windows 构建因行尾归一化仅 dist-info 三文件与 CI 差异，payload 43 文件逐字节相同——与 v5.0.0 已关闭的平台差异同类）。tag `v5.0.0` 未动；生产采用仍是宿主的显式决定。
- 生产激活待宿主条件不变（见 [V5 发布流程](docs/operations/RELEASE_V5.md)）。

## 上一检查点（2026-09-07，v5.0.0 已签名发布）

- v5.0.0（公共协议 jc/5.0）已完成签名发布：tag `v5.0.0` 触发 CI run 34150936429 全绿，promote 任务以生产密钥（protected release environment，生产 Ed25519 key）完成签名并创建 GitHub Release；provenance 为 `BYTE_IDENTICAL_REBUILD`，绑定源提交 `12d4ddd`（PR #5 已合入 main）。签名与公开发布是工程事实；`production_release_claimed=false`、`promotion_status=PENDING_TAG_VERIFICATION`——远程生产发布尚未执行，生产采用（部署激活）是宿主的显式决定。
- V5 一次性升级（JC-UPGRADE-20260906-01）全部验收完成；完整工程证据（含 2026-09-07 独立核查三项阻断的修复）见归档报告 [docs/archive/FINAL_UPGRADE_REPORT.md](docs/archive/FINAL_UPGRADE_REPORT.md)。
- 本地全量验收：Python 3.11.9 与 3.12.10（Windows）各 1703 passed, 0 failed；CI 四矩阵（Windows/Ubuntu × Python 3.11/3.12）与 `package`/`promote` 全绿。
- 证明依据：`proofs/lmm-binding.json`（LMM 23c5a310，CI run 33978186916）与 `proofs/runtime-obligation-map.json`（91 模块 / 452 声明处置）。运行时实现保证为 crossCheckOnly，不是 kernelVerified。
- 生产激活待宿主条件：branch protection 等外部治理在生产侧真实启用、生产 Ed25519 信任材料与有效规则包、存储 state_root 与资源预算、经验模型数据。满足前不得把候选/发布证据解释为已部署或获得现实法律正确性认证；激活步骤见 [V5 发布流程](docs/operations/RELEASE_V5.md)。

## 迁移与历史清算

- 正式链只有一套（V5，jc/5.0）。旧 V3/W1b/V4 执行链、旧兼容入口与零消费者模块不属于当前系统；V4 历史由封存 wheel、`remediation/v4/`（tasks.v3.json runner 与 STATUS）和旧证据承担。不建 V4/V5 并行内核。
- 正式输入拒绝 `jc/4.0` 与 4.x 引擎版本；V4 输入迁移走 `tools/migrate_v4_bundle.py`（离线、不自签、不复用旧证书）。
- addons（CN/HK/US/federation）保留在源码树用于规则对齐，不进入正式 wheel。
- 正式 wheel 只能从干净 `git archive` 提取构建（CI `package` job 或验收计划 V5-06）；`tools/build_provenance.py` 用测试密钥生成的证明不得冒充生产发布证明。
- `remediation/v4/tasks.json` 与 `task.schema.json` 是字节冻结的历史任务定义；当前 runner 只读取 `tasks.v3.json`，V5 整体验收使用 `remediation/v5/tasks.v1.json`（含 A/B wheel 构建与字节一致性核验）。

## 接手命令

```powershell
python -B tools/verify_upgrade.py --plan remediation/v5/tasks.v1.json --output work/v5-acceptance
python -B tools/remediate_v4.py lint-plan
python -B tools/remediate_v4.py run
```

每次运行从头按依赖顺序执行，并写一份 JSON run log；失败命令的完整 stdout/stderr 保存在 `<log>-failed-output/`，CI 无论成败上传运行证据。没有旧收据修补、恢复或 supersede 流程；失败就修当前根因后重跑。

## 下一执行面

1. 生产激活（宿主决定）：按 RELEASE_V5 满足信任材料、规则包、存储与经验数据条件后执行部署激活。
2. 常规维护：变更按 [AGENTS.md](AGENTS.md) 的验证梯度执行；文档体系变更后运行 `python -B tools/remediation/checks.py doc-links` 与 `tests/packaging` 文档测试。
