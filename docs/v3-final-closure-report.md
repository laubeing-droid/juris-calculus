# JC v3 本地闭环报告

日期：2026-07-11（Asia/Shanghai）

## 结论

- [计算生成的][高等] 本地实现门禁完成；受保护的 Horn、attack、exception、permission、priority、checker、`verified_fact` 与 fail-closed 语义未被削弱。
- [计算生成的][高等] 代码验证基线提交为 `29e67fcc52c5127ade518c6412ce97a4ef488fdd`；本报告由其后的文档收口提交承载。
- [计算生成的][高等] 远端 GitHub Actions 为 `NOT_EXECUTED`，因为当前授权禁止 push；本地完成不等于 release ready。

## 环境

| 项目 | 结果 |
|---|---|
| OS | Microsoft Windows NT 10.0.26200.0 |
| Python | 3.11.15、3.12.5 |
| 分支 | `codex/jc-v3-auditable-cli` |
| Engine/schema line | `3.0.0a1` / JC v3 schemas |
| Upstream specification | `a3a015941f75091c87d57aa956e712f1546dd7d4` |

## 验证命令

| 命令/门禁 | 退出码 | 结果 |
|---|---:|---|
| Python 3.11 `python -m pytest tests/ -q` | 0 | 484 passed, 38 skipped, 215.31s |
| Python 3.12 `python -m pytest tests/ -q` | 0 | 484 passed, 38 skipped, 198.80s |
| Phase 8 boundary/release narrow suite | 0 | 51 passed |
| WorkBuddy/MCP narrow suite | 0 | 13 passed；真实 subprocess stdio 调用四工具 |
| `python mcp_server.py --test` | 0 | 4 tools、0 resources、`readiness_claimed=false` |
| 性能 gate（固定合成 official pack） | 0 | PASS；无预算违规 |
| `pip-audit` core/documents/pipeline/render | 0 | 四个 profile 均 PASS，0 known vulnerabilities |
| clean wheel gate + 仓库外安装 | 0 | PASS；删除模块未复活，四工具/零资源 |
| 两次全新隔离构建 | 0/0 | 字节一致 |
| CycloneDX SBOM | 0 | 已生成；SHA-256 `127c8035918b94b78be1ec488de579cc8092360b4db2b71932c6450fd403078b` |
| `git diff --check` | 0 | PASS |

[计算生成的][高等] 早期隔离构建曾因失效代理 BLOCKED；清空进程代理后隔离构建真实通过。早期非隔离/隔离 wheel 又因 setuptools 81/83 漂移而不一致；将 build backend 固定为 setuptools 83.0.0、wheel 0.47.0 并绑定 `SOURCE_DATE_EPOCH` 后，两次隔离构建一致。

## 最终 wheel

- [计算生成的][高等] 文件：`juris_calculus-3.0.0a1-py3-none-any.whl`
- [计算生成的][高等] 大小：3,218,231 bytes
- [计算生成的][高等] SHA-256：`2b5a46ff7fad5ed5932f7acc83a18fd2c908137e659f9b0582f6ebc9bb613543`
- [计算生成的][高等] 两次独立隔离环境构建 hash 完全一致；仓库外 target 安装从 site-packages 加载。

## 规则包状态

| Pack | corpus / eligible / candidate | Digest | 状态 |
|---|---:|---|---|
| `cn-legacy-corpus` | 21144 / 0 / 21144 | `6ad83ec4016198c03f6c360b680dbb59e98e68ee99f062390ee74db02faf2491` | integrity valid, corpus only |
| `cn-official` | 0 / 0 / 0 | `2080ca703b2f671def179602e3e994e84556891a16deb7fb9ac1090eff2bb357` | BLOCKED: empty official pack |
| `hk-legacy-corpus` | 133 / 0 / 133 | `ab26406a0afb1159e4dea687781c6936e32805b0d19d4f8d505b930f12fd2143` | integrity valid, corpus only |
| `us-federal-legacy-corpus` | 123 / 0 / 123 | `c304d34f2af98ba614913fc0b90387502478415feee8234882e1efd7ace1551f` | integrity valid, corpus only |
| `us-l0-adapter-legacy-corpus` | 81 / 0 / 81 | `593b7b20ad741e14045dcd60e2528dc6e0c092f2a89e3b66c339c1ee3aaf65ec` | integrity valid, corpus only |

[计算生成的][高等] `jc packs verify --all --json` 总状态为 BLOCKED，不是失败伪装：所有 manifest 完整性有效，但没有 bundled reasoning-ready official pack。

## 性能观测

| 指标 | 观测 | 预算 |
|---|---:|---:|
| cold start | 0.779225s | 2.0s |
| warm run | 0.687969s | 1.0s |
| disputed branch | 1.386098s | 2.0s |
| peak memory | 1,257,141 bytes | 67,108,864 bytes |
| audit events | 10 | 100 |
| audit bundle | 9,218 bytes | 1,048,576 bytes |

[有理有据的][高等] 这些是固定合成 fixture 的工程回归上限，不是 21,144 条候选语料的吞吐量声明，也不是法律质量证据。

## 未完成/阻断项

- [计算生成的][高等] WorkBuddy 产品 UI 内四工具 E2E：BLOCKED；当前未识别到可供自动化核验的实际 WorkBuddy 安装/版本。真实 stdio 已通过，但不等于产品验证。
- [计算生成的][高等] 真实类案质量：BLOCKED；仓库只有明确标记的 synthetic index，没有合法授权、版本化的真实案例索引。
- [计算生成的][高等] 个人律师文风 profile：BLOCKED；尚缺 5—10 份用户确认样例与禁用表达清单。neutral profile 和 no-drift 机制已完成。
- [计算生成的][高等] bundled 正式 CN 推理：BLOCKED；`cn-official` 尚无一手来源快照规则。候选语料没有被猜测晋升。
- [计算生成的][高等] 远端 Ubuntu/Windows CI：NOT_EXECUTED；未 push、未 tag、未 release。

## [我违规之处]

无。
