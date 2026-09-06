# juris-calculus

JC 5.0.0 是公开、可审计的法律推理内核；公共协议为 jc/5.0，正式输入拒绝 jc/4.0 与 4.x 引擎版本。它接收结构化请求，只让已验证事实和已准入规则进入形式推理，并由同一 application service 向 CLI、Python 与四工具 stdio MCP 输出规范结果和可重放证据。

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

当前仓库只维护一套正式执行链（V5）。旧 V3/W1b/V4 执行链、旧兼容入口、零消费者模块和旧施工状态不属于当前系统；V4 历史由封存 wheel 与旧证据承担。中港美 addons 保留在源码树用于规则对齐，但不进入正式 wheel。

## 使用

支持 Python 3.11 和 3.12。版本权威是 `compiler_core/version.py`，公共输入合同是 `schemas/jc-v5.schema.json`，MCP 工具合同是 `mcp_manifest.json`。

```powershell
python -m pip install .
jc --version
$env:JC_RUNTIME_MANIFEST = "<runtime-manifest.json>"
$env:JC_RUNTIME_FACTORY = "compiler_core.production_runtime"
$env:JC_PRODUCTION_CONFIG = "<production-runtime.json>"
jc capabilities --json
```

```powershell
jc evaluate --input case-input-bundle.json --json
jc verify --input artifact-handle.json --json
jc replay --input artifact-handle.json --json
jc render --input artifact-handle.json --format markdown --audience agent --json
```

`jc-formal --registry <deployment/profile-registry.json> --input <case-input-bundle.json>` 运行 profile 固定的正式入口。运行宿主必须显式提供配置、信任材料、已签名规则包和 artifact store；仓库不内置任何生产部署状态或私有材料。

## 验证

```powershell
python -B tools/remediate_v4.py lint-plan
python -B tools/remediate_v4.py run
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests
python -B mcp_server.py --test
git diff --check
```

`remediation/v4/tasks.json` 和 `task.schema.json` 是冻结的历史任务定义；V4 执行器只读取 `tasks.v3.json`。V5 整体验收使用版本化计划 `remediation/v5/tasks.v1.json`（含 A/B wheel 构建与字节一致性核验）：

```powershell
python -B tools/verify_upgrade.py --plan remediation/v5/tasks.v1.json --output work/v5-acceptance
```

正式 wheel 只能从干净 `git archive` 提取构建（由该计划的 V5-06 任务与 CI `package` job 执行）；本地验收通过只支持报告 BUILD_ACCEPTED，不是发布或生产激活。

## 文档

- 使用与集成：[中文说明](docs/guides/README_CN.md)、[CLI](docs/guides/CLI.md)、[规则包](docs/contracts/RULE_PACKS.md)、[审计与重放](docs/contracts/AUDIT_BUNDLE.md)
- 开发与维护：[文档索引](docs/README.md)、[合同权威](docs/architecture/contract-authority-v4.md)、[V5 对象与状态矩阵](docs/contracts/V5_OBJECT_STATE_MATRIX.md)、[证明依据绑定](proofs/lmm-binding.json)
- 发布与验收：[V5 发布流程](docs/operations/RELEASE_V5.md)、[V4 发布流程（历史）](docs/operations/RELEASE_V4.md)、[最终升级报告](FINAL_UPGRADE_REPORT.md)

`.github/workflows/ci.yml` 负责验证发布构建产物，`.github/workflows/auto-release.yml` 只在额外授权和生产签名条件满足后晋级同一产物。`tools/build_provenance.py` 生成的测试密钥证明不得冒充生产发布证明。

## License

[MIT](LICENSE) © 2026 laubeing-droid.
