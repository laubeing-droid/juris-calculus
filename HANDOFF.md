# juris-calculus V4 handoff

## 当前事实

- 当前系统版本为 4.0.0，只保留 V4 正式执行链。
- 当前整改任务定义为 `remediation/v4/tasks.v3.json`，入口为 `tools/remediate_v4.py`。
- `remediation/v4/tasks.json` 与 `task.schema.json` 仅作字节冻结的历史记录，当前 runner 不读取它们。
- 正式 wheel 包含 official YAML 规则准入所需的 `compiler_core/rule_admission.py`，不依赖已退出正式包的 `compiler_core/types.py`。
- addons 中 CN/HK/US/federation 代码保留在源码树，不进入正式 wheel。
- 仓库不以外部状态目录、旧 receipt 或旧 CodeGraph 数据库作为当前 V4 验收前提。

## 接手命令

```powershell
python -B tools\remediate_v4.py lint-plan
python -B tools\remediate_v4.py run --through V4-03-OFFICIAL-YAML
python -B tools\remediate_v4.py run
```

每次运行从头按依赖顺序执行，并写一份 JSON run log；没有旧收据修补、恢复或 supersede 流程。失败就修当前根因后重跑。

## 发布边界

生产发布 not completed。任何远程发布仍要求 branch protection、生产 Ed25519 签名材料及 [V4 发布流程](docs/operations/RELEASE_V4.md) 中的授权条件。本次整改不包含 push、tag、GitHub release 或部署。
