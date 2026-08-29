# V4 build-once release and promotion

版本权威是 `compiler_core/version.py`；当前版本为 4.0.0。公共合同是 `schemas/jc-v4.schema.json` 与 `mcp_manifest.json`。

## 候选产物

`.github/workflows/ci.yml` 执行 Ubuntu/Windows Python 矩阵、authority 和生成物检查、完整测试、两次干净源码构建、wheel 字节对比、隔离安装、official YAML 正反验证、SBOM 与 test-only provenance。

测试夹具密钥只能生成 `TEST_ONLY_NOT_PROMOTABLE` 候选证明。`tools/build_provenance.py` 在生产验证中拒绝该密钥，除非调用者明确进入测试验证模式。

## 生产晋级

`.github/workflows/auto-release.yml` 只消费 CI 已构建的同一份产物，不重新构建。生产发布必须同时满足：

1. tag、源码提交、包版本和运行身份一致；
2. A/B wheel 字节一致且隔离安装门禁通过；
3. protected release environment 提供获授权的生产 Ed25519 密钥；
4. 生产 provenance、SBOM 与 checksums 对同一产物验证通过；
5. 仓库 branch/tag protection、required checks、review 和 retention 已在外部真实启用；
6. 有当前操作授权。

工作流文件不能证明外部治理已启用，也不能自行产生生产密钥或授权。`cn-official` 另有法律来源和签名边界；发布引擎不会把 candidate、OCR、教材、案例或旧语料自动变成官方规则。

本次 V4 整改只完成本地代码与候选产物验收，不执行 push、tag、release 或 deploy。

[Current remediation status](../../remediation/v4/STATUS.md) · [Rule packs](../contracts/RULE_PACKS.md) · [Audit bundle](../contracts/AUDIT_BUNDLE.md) · [Documentation index](../README.md)
