# juris-calculus

JC 4.0.0 是公开、可审计的 V4 法律推理内核。它接收结构化请求，只让已验证事实和已准入规则进入形式推理，并由同一 application service 向 CLI、Python 与四工具 stdio MCP 输出规范结果和可重放证据。

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

当前仓库只维护 V4 正式系统。旧 V3/W1b 执行链、旧兼容入口、零消费者模块和旧施工状态不属于当前系统。中港美 addons 保留在源码树用于规则对齐，但不进入正式 wheel。

## 使用

支持 Python 3.11 和 3.12。版本权威是 `compiler_core/version.py`，公共输入合同是 `schemas/jc-v4.schema.json`，MCP 工具合同是 `mcp_manifest.json`。

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

`remediation/v4/tasks.json` 和 `task.schema.json` 是冻结的历史任务定义；当前执行器只读取 `tasks.v3.json` 和 `task.v3.schema.json`。正式 wheel 的构建、隔离安装和 official YAML 正反验证由当前任务 `V4-04-WHEEL` 完成。

## 文档

- 使用与集成：[中文说明](docs/guides/README_CN.md)、[CLI](docs/guides/CLI.md)、[规则包](docs/contracts/RULE_PACKS.md)、[审计与重放](docs/contracts/AUDIT_BUNDLE.md)
- 开发与维护：[文档索引](docs/README.md)、[合同权威](docs/architecture/contract-authority-v4.md)、[当前系统状态](remediation/v4/STATUS.md)
- 发布：[V4 发布流程](docs/operations/RELEASE_V4.md)

`.github/workflows/ci.yml` 负责验证发布构建产物，`.github/workflows/auto-release.yml` 只在额外授权和生产签名条件满足后晋级同一产物。`tools/build_provenance.py` 生成的测试密钥证明不得冒充生产发布证明。

## License

[MIT](LICENSE) © 2026 laubeing-droid.
