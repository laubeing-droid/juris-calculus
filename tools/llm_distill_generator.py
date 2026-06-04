#!/usr/bin/env python3
"""
llm_distill_generator.py — LLM 原子蒸馏批处理管线
══════════════════════════════════════════════════════════════
输入: configs/en_US/state_combined_terms.json (3,259条)
输出: configs/en_US/llm_distilled_full.json

模式: 我(DeepSeek-V4 Pro)直接在对话中逐批蒸馏

批次: 50条/批 → 约65回合
══════════════════════════════════════════════════════════════
"""

DISTILL_PROMPT = """你是一个法律术语→L0原语转换器。严格遵守以下格式输出JSON，不要输出任何其他内容。

对每条术语，输出:
{{
  "term": "原始术语",
  "l0_primitive": "Agent|Asset|Act|Status|Power|Defect",
  "structural_chain": "Agent(X)→Act(Y)→Status(Z) 格式的L0推理链",
  "horn_premise_atom": "前提条件1 AND 前提条件2 → 结论",
  "domains": ["领域1", "领域2"],
  "cross_border_relevant": true/false,
  "prc_mapping": "BLK阻断ID | OVR映射名 | 或CN法条引用"
}}

规则:
- l0_primitive 只能是6个原语之一
- structural_chain 必须包含至少2个原语节点
- 如果涉及跨境资产/数据/制裁, cross_border_relevant=true
- prc_mapping 必须引用laubeing-droid阻断清单或民法典对应条款

以下术语列表(Dict[str, LegalFact]):
"""


def extract_terms_batch(terms_list, batch_size=50):
    """output a batch of terms for me to process"""
    batches = []
    for i in range(0, len(terms_list), batch_size):
        batch = terms_list[i:i+batch_size]
        prompt = DISTILL_PROMPT + "\n" + "\n".join(f"- {t}" for t in batch)
        batches.append({
            "start_idx": i,
            "end_idx": min(i+batch_size, len(terms_list)),
            "count": len(batch),
            "prompt": prompt,
            "terms": batch
        })
    return batches


if __name__ == "__main__":
    import json
    with open('configs/en_US/state_combined_terms.json','r',encoding='utf-8') as f:
        terms = json.load(f)
    batches = extract_terms_batch(terms)
    print(f"Total: {len(terms)} terms, {len(batches)} batches (50 terms/batch)")
    print(f"\nBatch 0 ({batches[0]['count']} terms):")
    for t in batches[0]['terms'][:5]:
        print(f"  {t}")
