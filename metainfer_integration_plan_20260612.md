# MetaInfer → jc v2.0 落地执行计划

**目标**: 从 MetaInfer 仓库中提取三项可落地资产，落地到 jc v2.0 源码树
**基线**: `D:\juris-calculus-fresh` (HEAD=024fb0b) + `D:\MetaInfer-fresh`

---

## 任务 1: 结构化 juris_blueprint.json

**来源**: MetaInfer `inference_blueprint.json` 的 `agent_navigation` + 分层存储结构
**落点**: `D:\juris-calculus-fresh\configs\juris_blueprint.json`

**内容**:
```
{
  "metadata": { name, version, foundation }
  "agent_navigation": { ref_docs_policy, forced_cross_validation }
  "knowledge_categories": { 6 类法律契约 (来自 LegalOS_v2.0 §3) }
  "compiler_passes": [6 pass]
  "forbidden_claims": [5 条禁止叙事]
  "runtime_acceptance_layer": { 8 个 legal_gates }
  "failure_mode_library": [4 条失败模式]
  "evidence_status_taxonomy": { 6-3 PROOF_LEDGER 对齐 }
}
```

**验收**: python -c "import json; json.load(open(...))"

---

## 任务 2: AGSKILL.md 执行铁律融入 Codex Playbook

**来源**: MetaInfer `AGENT_SKILL.md` §0.0-§2.0 的 Phase 门禁 + 防假 PASS
**落点**: `D:\codex_audit_prompt_and_playbook_20260611.md` 更新 Phase 0 的 verification 协议

**融入内容**:
- Phase 0 增加 "防假 PASS" 步骤 (import path 验证)
- 每个 Phase 的验证步骤增加 "脚本不可变" 约束
- 增加 "防懒惰" 检查 (每 Phase 必须跑完再进下一 Phase)

---

## 任务 3: 盲重建审计方法论融入融合报告

**来源**: MetaInfer `notebooks-cn/07_improvementPlan/build_prompt/isolated_reconstructability_audit*.md`
**落点**: `D:\juris-calculus_v2.0_工程融合报告_20260611.md` §2.3 已有，需补充具体审计脚本

**融入内容**:
- `tools/audit_blind_reconstruction.py` — 仅凭 juris_blueprint.json + 法条原文重建法律结论
- 审计流程: 20 案例 × 3 独立推理 → 对比差异 → 发现规则遗漏

---

## 预计工作量: 1-2 天
## 预计新增代码: ~400 行 (juris_blueprint.json 200 + audit脚本 120 + playbook更新 80)
