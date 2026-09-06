# Changelog

## 5.0.0 — V5 upgrade (JC-UPGRADE-20260906-01, in progress on upgrade/ulm-bound-runtime-v5)

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
