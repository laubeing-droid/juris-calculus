# V4 remediation status

Updated: 2026-08-29

## 当前状态

当前整改以仓库工作树、Git 跟踪清单、本地 AST、测试结果和实际 wheel 为唯一验收证据。外部状态目录、旧 receipt、旧 CodeGraph 数据库和旧部署声明均不是当前权威。

当前 runner：

```powershell
python -B tools\remediate_v4.py lint-plan
python -B tools\remediate_v4.py run
```

入口只读取 `tasks.v3.json` 和 `task.v3.schema.json`。冻结历史文件 `tasks.json`、`task.schema.json` 不修改、不执行；未来任务路径变化必须再建新版本。

## 验收范围

- Git + AST module-authority 一致。
- 测试和工具无固定机器路径，Windows 中文路径按 UTF-8 工作。
- official YAML 在源码态和隔离安装 wheel 中均完成正反准入验证。
- 23 个零消费者模块、旧 shim、旧验证器和旧文档不在当前树。
- CN/HK/US/federation addons 保留并通过 smoke。
- 完整 pytest、文档链接与 `git diff --check` 通过。

## 边界

本状态页不声明本机或远程生产已经激活。本次整改不执行 push、tag、release 或 deploy。发布条件见 [V4 release procedure](../../docs/operations/RELEASE_V4.md)。
