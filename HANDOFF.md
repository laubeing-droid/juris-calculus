# juris-calculus V5 handoff

## 当前检查点（2026-09-06，V5 升级完成）

- V5 一次性升级（JC-UPGRADE-20260906-01）已在本地完成：`remediation/v5/tasks.v1.json` 六项验收全部 PASSED，候选 wheel `juris_calculus-5.0.0-py3-none-any.whl` A/B 字节一致（见 [FINAL_UPGRADE_REPORT.md](FINAL_UPGRADE_REPORT.md)）。
- 当前系统版本为 5.0.0（公共协议 jc/5.0）；正式输入拒绝 `jc/4.0` 与 4.x 引擎版本，V4 输入迁移走 `tools/migrate_v4_bundle.py`（离线、不自签、不复用旧证书）。
- V4 整改历史由封存 wheel、`remediation/v4/`（tasks.v3.json runner 与 STATUS）和旧证据承担；正式链只保留一套，不建 V4/V5 并行内核。
- 证明依据：`proofs/lmm-binding.json`（LMM 23c5a310，CI run 33978186916）与 `proofs/runtime-obligation-map.json`（91 模块 / 452 声明处置）。运行时实现保证为 crossCheckOnly，不是 kernelVerified。
- addons 中 CN/HK/US/federation 代码保留在源码树，不进入正式 wheel。
- 待授权阻塞：远程推送/PR（CI 四矩阵证据）、生产信任材料、经验模型数据——详见最终报告 §六。

## 接手命令

```powershell
python -B toolserify_upgrade.py --plan remediation/v5/tasks.v1.json --output work/v5-acceptance
python -B toolsemediate_v4.py lint-plan
python -B toolsemediate_v4.py run
```

每次运行从头按依赖顺序执行，并写一份 JSON run log；失败命令的完整 stdout/stderr 保存在 `<log>-failed-output/`，CI 无论成败上传运行证据。没有旧收据修补、恢复或 supersede 流程；失败就修当前根因后重跑。

## 远程发布边界

远程生产发布尚未执行。候选构建验收通过只支持报告 BUILD_ACCEPTED；生产激活要求 branch protection、生产 Ed25519 签名材料、当次操作授权及 [V5 发布流程](docs/operations/RELEASE_V5.md) 中的其他条件。不得把本地验收解释为已经发布、部署或获得现实法律正确性认证。
