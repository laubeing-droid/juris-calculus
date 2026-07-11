# JC v3 Phase 0 基线证据

## 范围与快照

- [计算生成的][高等] 基线分支：`codex/jc-v3-auditable-cli`
- [计算生成的][高等] 基线起点：`6a281a3eef1f7f3649020435fbe916f24caac564`
- [计算生成的][高等] Python：3.11.15、3.12.5。
- [计算生成的][高等] 上游规格测试显式设置`LEGAL_MATH_MODELING_ROOT`，但本证据不写入机器绝对路径。
- [计算生成的][高等] 正式语义冻结测试：`tests/unit/test_v3_semantic_baseline.py`。
- [计算生成的][高等] 求值入口处置台账：`docs/v3-evaluation-entrypoints.md`。
- [计算生成的][高等] 33项工具与12项resource处置表：`docs/jc-v3-full-remediation-plan.md`第13节。

[有理有据的][高等] 本文件冻结的是v3改造前的可重复工程和语义基线，不把当前元数据缺陷或自然语言报告晋升为正式规范。

## 命令与结果

[计算生成的][高等] 下表每一项均来自本分支的实际命令、退出码和计时结果。

| 门禁 | Python 3.11.15 | Python 3.12.5 | 结论 |
|---|---|---|---|
| 推荐窄测、真实stdio、三轨相关单测 | 27 passed、6 skipped，exit 0，226.6s | 27 passed、6 skipped，exit 0，203.3s | PASS |
| 完整`tests/`（加入语义fixture后） | 365 passed、38 skipped，exit 0，483.0s | 365 passed、38 skipped，exit 0，448.3s | PASS |
| `mcp_server.py --test` | exit 0，25.5s | exit 0，21.6s | PASS；仅代表进程内功能smoke |
| 真实MCP业务`tools/call` | 1 passed，32.43s | 1 passed，27.47s | PASS；stdout全程仅JSON-RPC |
| `tools/supply_chain_gate.py` | PASS，0个已知漏洞，33.6s | PASS，0个已知漏洞，58.3s | PASS |
| 新增语义fixture及受影响测试 | 20 passed，exit 0，2.82s | 20 passed，exit 0，2.42s | PASS |
| `git diff --check` | — | — | PASS |

[计算生成的][高等] 供应链门禁第一次经故障本地代理运行时返回`BLOCKED(tls_error)`和非零退出码；移除故障代理、保持TLS校验后直连重跑，两个版本才得到上表PASS。BLOCKED未被记录为PASS。

### 三轨矩阵

- [计算生成的][高等] Python 3.12执行`tools/run_trirail_matrix.py`，12个场景全部完成，exit 0，43.1s。
- [计算生成的][高等] 分类为7个`CHINA_US_COLLISION`、4个`HK_CN_ASYMMETRY`、1个`TRI_RESONANCE`。
- [计算生成的][高等] 生成型JSON和文本报告与基线内容一致；HTML只有时间戳/空白漂移，因此未改写已跟踪证据。
- [有理有据的][高等] 运行时仍明确报告来源锚缺失候选；该警告不得被解释为正式准入成功。

## MCP迁移表核验

[计算生成的][高等] 当前`mcp_manifest.json`恰有33项工具和12项resources。全量计划WP7.3与WP7.4逐项表和manifest集合完全一致，无遗漏、无额外名称。Phase 7以该表迁移，不建立第二份运行时兼容层。

## 数据与隐私基线

[计算生成的][高等] 扫描范围是全部Git跟踪文本文件；扫描只报告匹配，不复制潜在秘密内容。下表结果均来自实际扫描。

| 检查 | 结果 | Phase 0处置 |
|---|---:|---|
| 形似API key/token/secret/password赋值 | 0 | PASS |
| 形似客户或当事人姓名字段赋值 | 0 | PASS |
| 私网IPv4地址 | 0 | PASS |
| 机器绝对路径引用 | 11 | 5处活跃边界文档在Phase 8改为仓库无关表达；6处有日期历史证据报告保持原样 |
| 已跟踪v2审计包目录或`events.jsonl/checksums.sha256` | 0 | 无真实外部v2审计格式需要运行时兼容或迁移 |

[有理有据的][高等] 绝对路径引用是公开叙述卫生问题，不是本轮发现的客户数据或凭证泄漏；Phase 0只记录基线，避免在“仅测试/证据”提交中混入历史文档改写。

## 规则、来源与报告文件快照

[计算生成的][高等] 规范字节来自Git index blob，避免Windows工作树换行过滤造成漂移。行格式为`相对路径<TAB>字节数<TAB>SHA-256`，按路径排序、以UTF-8无BOM和LF连接并保留末尾LF。下列36行均为实际index结果；整体SHA-256为`3f9f2dc12bca5eb8d397ff100921159e58e52770bb5ed53abb030131f395db64`。

```text
configs/en_US/L0_overrides_us.yaml	31117	c23439c50b8e85666f664ee264eca3548f4f8ff5c36983cdc53d46d854cccecf
configs/en_US/rules.yaml	10	e0dfa70eb69d47fe9cb2be8a4fcd53e74cf7fe26fcbb1f06912b57a9c028e4e0
configs/en_US/US_Adapter.yaml	67062	0c887dd7e48dc043e04b231cc0165f09d89f9e25c2a819f80f1d2b86a0d06fd3
configs/hk/blocking_rules.yaml	10777	53a0598bf1f2bcfa829eef0d0ab9115ad08a0f045b27d1a1b571fc0352d52387
configs/hk/extended_rules.yaml	14590	ade7552076e2f0fb51e190086e7e9c6647098cac7aad7b7782a1b044fcd7135a
configs/hk/provenance.yaml	743	98e09561c2c057f0f9ec359ece683069faca974239af5a0817edf988949da118
configs/hk/rules.yaml	39964	c7f54338904e37369287d39ee193f2d4cb00ff56c0d61a041d38f19262de24a8
configs/hk/rules_expanded.yaml	132409	dc7e2b450c8c525e0acaa89d91efff5b168ccc2418b95951cb366374a1f1cd60
configs/hk/term_L0_mappings.yaml	263933	c2ae7a01506dabd6ca4785b8b9ad6f66dd641a1522a5419f4aa59adfc2708f1b
configs/L0_overrides_cn.yaml	972	00022c2c6538d4bc702e03b0c64ff6b58212a1d5191ef222c721d46b54df8ab5
configs/L0_overrides_hk.yaml	2463	b46d396e60269f85c756c82919891685cb84da09d64099e8a2bc285dab8b1638
configs/prc_us_alignment/blocking_rules.yaml	14919	7b04240a728c323ce8d841b3ff4a0f23f8d7986367342b76daf10f8fc4dcc321
configs/prc_us_alignment/long_tail_collision_matrix.json	269	bbc77a1f5f2db6c4e202fbba7d9f87e7ff3cbc84a464335776f79b5a8efbd645
configs/prc_us_alignment/meta_constraints.yaml	2361	c8e2f53c29489ae080e365ec874780cdf2cc826f17ead1dac01ebbcb2817d215
configs/prc_us_alignment/procedural_justice_rules.yaml	5248	4c20a765532bef38433d666cc61a666cef8db685957a1cc6df84b3114edece61
configs/prc_us_alignment/spc_rules.yaml	12413	ec472c6795dd7a77f18569c7ce6cbe8549b9ed3f86f2afa7564af7ac533f9368
configs/prc_us_alignment/term_L0_mappings.yaml	41424	674ddf4af96e596b0c584146671642b5b03a6933ddd7821cbf3cffcb8ab4b90a
configs/prc_us_alignment/term_L0_mappings_batch2.yaml	27022	928664ac195471e78a2135973a1ec57a46e3fd40c86b4f8798ae9e6dacb483fb
configs/prc_us_alignment/trirail_matrix_report.json	35026	26bd22def2c597beb243a99e0eb36afc6f7aefced2237c88d837f5591ba2133c
configs/uk/rules_candidates.yaml	2901	0a7865a9082c09ad1f3606f748e5cd69c8b72d54f98fab40e9792121c2a09a22
configs/us/blocking_rules.yaml	9161	d15dff9a2995972ae023d00adee7f64794f00096a4a7c59c06868ab0b847dd81
configs/us/modal_mapping.yaml	2199	acf565e5e87f278fcf17da500b4d97f62d58390ff598516fae6343d7410209a8
configs/us/rules.yaml	58635	a9166e515437a6f02a9800c21daaf80e4fac8a7a5c0e336383d6a4eaaf86a8e9
configs/us/term_L0_mappings.yaml	21283	025d376a8b87214ff24ebe91853e617ed85fd433a5e9d24034d9953b637d5daf
configs/us/threat_signatures/nj_pen_signature.yaml	6759	5dc2f595f919660db9de895780f30c78b5fa07ca0cee8d3744e9510e5c49949a
configs/us/threat_signatures/wi_enf_signature.yaml	6627	41d2d6c794dc7a8151c32a1523f45e126cf960f3d2e6644dd9b7e099800f63f9
configs/zh_CN/classifier_rules.yaml	2215	bea82835d3adefcb06b26572d3c67597fff4f0d8d10f6331d8f30d87d8eb54aa
configs/zh_CN/rules.yaml	13620766	032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44
configs/zh_CN/source_manifest.yaml	2143	92a002fd9e992f4a3c7b2710af66e1279129f7344706d32365093da8c48c50b7
reports/blind_reconstruction_audit.md	1671	b2be5cebb5fbb7614a82239a584ea6bed1d9bc5c869f0585e74644a76b171ece
reports/lsc_absorption_final_report_2026-07-03.md	13890	bae770cdf8925fa0fdc80e67fe214a6973d902682232d91bf3364471e5d5d0ed
reports/lsc_absorption_snapshot_2026-07-03.md	1722	cc74cf2558549e24963d502de950ae1ffaad7defad2d2da2fd3e42c189b6821e
reports/trirail_heatmap_v1.2.0.html	15910	b9141e38dd28a60ff8d2b18a9a2e24c9554e1bb59137ea2ea5270cae2a860bb6
reports/trirail_report_v1.2.0.txt	3493	7847baab3a4d1e547c7d3df28ae44ec01a21a1328bfe754cb894432a17aac667
runtime/spec_shadow_report.json	26048	e3f266a4ed6fa5501bec7e21043c495dbadbe11846ba5908e3c6fe3f0191aad5
runtime/spec_shadow_report.md	1147	f951f7ce808659a94c3796aa6e0daa46d967ede5b4c47fe12e9f68ec1ac90a97
```

## Phase 0停止条件检查

- [计算生成的][高等] 完整tests不存在原因不明的失败。
- [计算生成的][高等] 工作树起点无用户未提交产品改动。
- [计算生成的][高等] 当前基线没有把候选事实、无来源规则或供应链BLOCKED包装成PASS。
- [计算生成的][高等] Phase 0不修改Horn、attack、exception、permission、priority或checker实现。

## [我违规之处]

无。
