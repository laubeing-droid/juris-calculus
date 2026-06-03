# juris-calculus Changelog

## v1.0.3 (V6) - 2026-06-03

### Kernel Upgrades (V6 LegalOS Integration)

#### compiler_core/types.py
- Added `TaintStatus` enum: CLEAR, TAINTED, ATTEMPTED_HIJACK, VERBATIM_MISMATCH
- Extended `LegalFact`: taint_status, extraction_confidence, carrier_level, raw_text, source_anchor
- Extended `LegalClaim`: claim_type, execution_trace_id
- Added `NegativeSpec` dataclass for reverse requirement gap detection

#### compiler_core/domain_config.py
- Added `DISCRETIONARY_CONCEPTS` registry (16 Chinese legal concepts)
- Added `check_discretionary()` function for automatic TAINTED marking
- Added `enable_discretionary_taint` flag to `DomainConfig`

#### compiler_core/evaluator.py
- M1 Multiplication Penalty: h==0 or p==0 -> score *= 0.5
- Imported `check_discretionary` from domain_config
- Added `check_fact_discretionary()` method
- Added `evaluate_with_taint_gate()` pipeline
- Added `check_negative_specs()` and `evaluate_with_full_gate()` stubs

#### compiler_core/classifier.py (NEW)
- `EvidenceClassifier`: A/B/C evidence carrier level classification (regex-based)
- `levenshtein_distance()`: Edit distance for OCR tolerance
- `verify_raw_text()`: Source-anchored verification with 4-step pipeline
- `detect_label_hijacking()`: ATTEMPTED_HIJACK detection

#### configs/zh_CN/classifier_rules.yaml (NEW)
- A_HARD_EVIDENCE: 6 rules (bank records, official docs)
- B_ALTERNATIVE_EVIDENCE: 5 rules (chat confirmations, emails)
- C_WEAK_SIGNAL: 5 rules (vague mentions, default catch-all)

#### configs/zh_CN/rules.yaml
- De-SPC-ified: "SPC v5.3" -> "民法典+司法解释(请求权基础分析)"
- Added 5 民间借贷 Horn rules (LOAN-001 to LOAN-005)
- Added 7 exception chain rules (LOAN-EXC-001 to LOAN-EXC-007)
- AND 前提增强: 单前提 48.2% → 31.9%, 注入 690 原子
- OCR 概念标签注入: 累计 1,453 次, 规则唯一概念 1,921
- Total rules: 2117

#### .github/workflows/ (NEW)
- `auto-release.yml`: Semantic versioning + changelog + auto-publish
- `rules-yaml-lint.yml`: YAML validation + Tarjan SCC cycle detection

#### mcp_server.py (NEW)
- FastMCP Server wrapper for WorkBuddy integration
- Three tools: evidence_review, argument_lint, contract_review
- JSON-RPC stdio fallback mode
- ExecutionTraceID generation and audit logging

### Design Principles (V6)
- 大模型全系统最高权限 = 摘原文 + 贴标签。永不裁判。
- carrier_level 由规则引擎机械判定，严禁大模型填写
- 自由裁量概念（显失公平、公序良俗等）自动 TAINTED
- Negative Spec: 不仅输出提取到的事实，还输出未找到的要件
- Source-Anchored Verification: 编辑距离 <= 3 容差

### Test Results
- Unit tests: 5/5 PASS
- Loan rules: LOAN-001, LOAN-002 verified end-to-end
- Classifier: A/B/C 6/6 test cases PASS
- Hijack detection: ATTEMPTED_HIJACK flagging verified
- Source verify: OK / VERBATIM_MISMATCH verified

### Upgrading from v1.0.2
```bash
git pull
pip install -r requirements.txt  # includes pyyaml
python -m unittest tests.unit.test_evaluator -v  # 5/5 should pass
```
