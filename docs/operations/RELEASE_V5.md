# V5 发布流程（JC-UPGRADE-20260906-01）

状态：**BUILD_PENDING_FINAL_ACCEPTANCE** —— 本文档描述 V5 候选版本的构建、验收与撤回流程；不声明发布已完成，也不构成现实法律正确性认证。

## 版本身份

- 引擎版本：`5.0.0`（`compiler_core/version.py` 唯一版本源）。
- 公共协议：`jc/5.0`（`compiler_core/contracts.py::SCHEMA_VERSION_V5`）。
- 正式输入拒绝 `jc/4.0` 与 4.x 引擎版本；迁移走 `tools/migrate_v4_bundle.py`（SOURCE_TOOL，不进 wheel）。
- 证明依据：`proofs/lmm-binding.json`（LMM `23c5a310...`，CI run 33978186916）+ `proofs/runtime-obligation-map.json`（91 模块 / 452 声明处置）。

## 构建与验收（同一 artifact）

```powershell
# 完整验收（构建 wheel 并按计划顺序实跑全部必需任务）
python -B tools\verify_upgrade.py --plan remediation/v5/tasks.v1.json --output work/v5-acceptance
```

- 验收计划 `remediation/v5/tasks.v1.json`：V5-01 权威与生成物 → V5-02 合同 → V5-03 语义 → V5-04 迁移 → V5-05 生产链 → V5-06 wheel。
- 汇总报告 `work/v5-acceptance/acceptance-summary.json`；失败任务的完整 stdout/stderr 保存在 `work/v5-acceptance/required-run-failed-output/`。
- 全部必需任务实际通过后，可报告 `BUILD_ACCEPTED`；发布阶段不得重建出另一个未经验证的 wheel。

## CI 闭环

`.github/workflows/ci.yml` 的四个必需矩阵（Windows/Linux × 3.11/3.12）不被弱化；`Required current suites` 步骤无论成败上传 `work/required-run.json` 与 `work/required-run-failed-output/`。

## 宿主激活条件（未满足则不得激活）

1. 有效生产 Ed25519 信任材料与规则包（测试密钥仅限测试，`production_allowed=false`）。
2. 存储 state_root、资源预算与权限按宿主环境配置并通过本机验收。
3. 经验证的经验模型与数据（如需经验预测；缺省返回“未提供经验证的经验估计”）。

## 撤回

- 停止接受新请求；保留既有审计包原字节。
- 切换回封存的 V4 wheel 与原配置；禁止用 V4 代码读取并改写 V5 包。
- 规则撤销与代码回滚分别记录，不删除历史证据。
