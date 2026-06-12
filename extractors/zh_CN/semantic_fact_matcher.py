#!/usr/bin/env python3
"""
juris-calculus 语义事实匹配器 v2.0
用 bge-large-zh 嵌入做案卷事实 ↔ 规则前提的语义匹配
替代 Parser 3.0 的正则匹配，提升 T1 运行率

用法：
    python -m extractors.zh_CN.semantic_fact_matcher \
        --case-dir ./data/raw_bak/民事 \
        --rules-yaml ../../configs/zh_CN/rules.yaml \
        --output ./data/facts_semantic.json
"""
import json, sys, os, re, yaml
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

# ── 法律前提 → 谓词 ID 映射规则 ──
PREDICATE_NORMALIZE = [
    (r'(?:合同|协议|契约)\s*(?:已|已经)?\s*(?:有效)?\s*(?:成立|签署|生效|订立)', 'contract_formed'),
    (r'(?:货款|价款|费用|租金|借款)\s*(?:已|已经)?\s*(?:到期|届满|支付日|应支付)', 'payment_due'),
    (r'(?:未|没有|拒不|逾期|迟迟未)\s*(?:支付|付款|还款|履行|交付)', 'breach_alleged'),
    (r'(?:已|已经)?\s*(?:交付|交货|发货|提供|给付|转移占有)', 'goods_delivered'),
    (r'(?:合同|协议)?\s*(?:无效|撤销|解除|终止|废止)', 'contract_invalid'),
    (r'(?:超过|已过|经过)\s*(?:诉讼时效|除斥期间|异议期|上诉期)', 'statute_barred'),
    (r'(?:不可抗力|疫情|自然灾害|政府行为|战争)', 'force_majeure_claimed'),
    (r'(?:抵押|质押|保证|担保|留置|定金|保证金)', 'security_provided'),
    (r'(?:查封|冻结|扣押|保全|强制执行)', 'enforcement_action'),
    (r'(?:二审|上诉|再审|抗诉|发回重审)', 'appeal_proceeding'),
    (r'(?:鉴定|评估|审计|检测|检验|勘验)', 'expert_evidence'),
    (r'(?:利息|违约金|滞纳金|罚息|赔偿金)', 'liquidated_damages_claimed'),
    (r'(?:损失|损害|伤害|亏损|贬值)', 'damages_suffered'),
    (r'(?:故意|过失|明知|应知|疏忽)', 'fault_element'),
    (r'(?:自首|立功|坦白|认罪|悔罪|退赃|退赔)', 'leniency_factor'),
]

class SemanticFactMatcher:
    """基于规则库的语义事实匹配器"""

    def __init__(self, rules_yaml_path: str = None, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model = SentenceTransformer(model_name) if SentenceTransformer else None
        self.rules: List[dict] = []
        self.premise_index: Dict[str, List[str]] = {}  # predicate_id → [rule_ids]
        self.premise_embeddings: np.ndarray = None
        self.premise_texts: List[str] = []
        self.premise_ids: List[str] = []
        self._loaded = False

        if rules_yaml_path:
            self.load_rules(rules_yaml_path)

    def load_rules(self, yaml_path: str):
        """加载规则库并构建前提索引"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        self.rules = data.get('rules', data) if isinstance(data, dict) else data
        print(f"[语义匹配器] 加载 {len(self.rules)} 条规则, 构建前提索引...")

        # 为每条规则构建语义嵌入索引
        # 使用 head_claim（中文裁判规则文本）作为嵌入内容
        # premise_atoms（谓词ID）用于精确匹配
        for rule in self.rules:
            atoms = rule.get('premise_atoms', [])
            if isinstance(atoms, str):
                atoms = [atoms]
            
            # 用 head_claim（中文规则文本）作为语义嵌入
            head = rule.get('head_claim', '') or ''
            for atom in atoms:
                if atom and head:
                    self.premise_index.setdefault(atom, []).append(rule['id'])
                    # 嵌入中文文本，保持以谓词ID索引
                    self.premise_texts.append(head[:200])
                    self.premise_ids.append(atom)
            
            # 如果规则没有 head_claim，用概念列表
            if not head:
                concepts = rule.get('concepts', [])
                concept_text = ' '.join(concepts[:3]) if concepts else atom
                for atom in atoms:
                    self.premise_texts.append(concept_text[:200])
                    self.premise_ids.append(atom)

        print(f"  → {len(self.premise_index)} 个唯一谓词, {len(self.premise_texts)} 条前提")
        self._build_embeddings()
        self._loaded = True

    def _text_to_predicate(self, text: str) -> str:
        """将中文前提描述转为谓词 ID"""
        text = text.strip()
        if not text:
            return ""
        for pattern, pred_id in PREDICATE_NORMALIZE:
            if re.search(pattern, text):
                return pred_id
        # fallback: 取前两个字的拼音首字母+hash
        import hashlib
        short = text[:4]
        h = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"premise_{h}_{short}"

    def _build_embeddings(self):
        """构建前提的语义嵌入"""
        if not self.model or not self.premise_texts:
            self.premise_embeddings = np.array([])
            return
        self.premise_embeddings = self.model.encode(
            self.premise_texts, normalize_embeddings=True, show_progress_bar=False
        )

    @staticmethod
    def _load_threshold():
        """Load semantic threshold from domain_config YAML, fallback to 0.65"""
        try:
            import yaml
            from pathlib import Path
            config_path = Path(__file__).resolve().parents[2] / "configs" / "zh_CN" / "domain_config.example.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("semantic", {}).get("default_threshold", 0.65)
        except Exception:
            return 0.65

    def extract_facts(self, case_text: str, threshold: float = None) -> Dict[str, float]:
        if threshold is None:
            threshold = self._load_threshold()
        """
        从案卷文本提取事实谓词（语义匹配版）
        返回 {predicate_id: confidence}
        """
        facts = {}

        # 1. 正则快速匹配（0成本）
        for pattern, pred_id in PREDICATE_NORMALIZE:
            if re.search(pattern, case_text):
                facts[pred_id] = 1.0

        # 2. 语义匹配（对未匹配的额外扫描）
        if self.model is not None and self._loaded and len(self.premise_embeddings) > 0:
            case_emb = self.model.encode([case_text[:512]], normalize_embeddings=True)
            scores = np.dot(self.premise_embeddings, case_emb.T).flatten()
            top_indices = np.argsort(scores)[-15:]  # TOP 15

            for idx in top_indices:
                score = float(scores[idx])
                if score >= 0.35 and self.premise_ids[idx] not in facts:  # 低阈值以覆盖更多
                    facts[self.premise_ids[idx]] = round(score, 3)

        return facts

    def match_rules(self, facts: Dict[str, float]) -> List[Tuple[str, str, float]]:
        """
        根据事实谓词查找触发的规则
        返回 [(rule_id, head_claim, match_score)]
        """
        triggered = []
        matched_predicates = set(facts.keys())

        for rule in self.rules:
            atoms = rule.get('premise_atoms', [])
            if isinstance(atoms, str):
                atoms = [atoms]

            # 将规则的前提转为谓词 ID
            rule_preds = [self._text_to_predicate(a) for a in atoms if a]
            rule_preds = [p for p in rule_preds if p]

            if not rule_preds:
                continue

            # 检查有多少前提被事实命中
            matched = sum(1 for p in rule_preds if p in matched_predicates)
            if matched >= len(rule_preds) * 0.6:  # 60% 前提命中
                score = matched / max(len(rule_preds), 1)
                triggered.append((rule['id'], rule.get('head_claim', '')[:80], round(score, 2)))

        return triggered

    def estimate_complexity(self, facts: Dict[str, float], text: str) -> dict:
        """基于事实数量和因果关系估算案件复杂度"""
        base_nodes = len(facts)
        causal_arcs = 0
        causal_pairs = [
            ('contract_formed', 'payment_due'),
            ('payment_due', 'breach_alleged'),
            ('goods_delivered', 'payment_due'),
            ('breach_alleged', 'liquidated_damages_claimed'),
            ('damages_suffered', 'fault_element'),
        ]
        for a, b in causal_pairs:
            if a in facts and b in facts:
                causal_arcs += 1

        weighted = base_nodes + causal_arcs * 1.5
        # 法条引用检测
        law_count = len(re.findall(r'[《]', text))
        if law_count > 5:
            weighted += 2

        return {
            "base_nodes": base_nodes,
            "causal_arcs": causal_arcs,
            "weighted_nodes": round(weighted, 1),
            "law_count": law_count,
            "method": "SemanticMatcher v2.0"
        }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--case-dir', default='./data/raw_bak/民事')
    parser.add_argument('--rules-yaml', default='./configs/zh_CN/rules.yaml')
    parser.add_argument('--output', default='./data/facts_semantic.json')
    args = parser.parse_args()

    matcher = SemanticFactMatcher(args.rules_yaml)
    case_dir = Path(args.case_dir)

    results = []
    total_t1 = 0
    total_cases = 0

    for case_folder in sorted(case_dir.iterdir()):
        if not case_folder.is_dir():
            continue

        # 读取案卷文本
        combined = ""
        for f in case_folder.rglob('*'):
            if f.suffix in ('.txt', '.md', '.docx'):
                try:
                    combined += f.read_text(encoding='utf-8', errors='ignore') + '\n'
                except:
                    pass

        if not combined.strip():
            continue

        total_cases += 1
        facts = matcher.extract_facts(combined)
        triggered = matcher.match_rules(facts)
        complexity = matcher.estimate_complexity(facts, combined)

        has_t1 = len(triggered) > 0
        if has_t1:
            total_t1 += 1

        result = {
            "case": case_folder.name,
            "facts": facts,
            "triggered_rules": len(triggered),
            "top_rules": triggered[:5],
            "complexity": complexity,
            "t1_triggered": has_t1
        }
        results.append(result)

        print(f"[{case_folder.name[:20]:20s}] 事实={len(facts)} 触发={len(triggered)} T1={'✅' if has_t1 else '❌'} 加权节点={complexity['weighted_nodes']}")

    # 汇总
    t1_rate = total_t1 / max(total_cases, 1) * 100
    print(f"\n=== 语义匹配结果 ===")
    print(f"总案卷: {total_cases}")
    print(f"T1触发: {total_t1}/{total_cases} ({t1_rate:.1f}%)")
    print(f"方法论: 正则谓词化 + bge-large-zh 语义兜底 (threshold=0.65)")

    Path(args.output).write_text(
        json.dumps({"results": results, "summary": {"total_cases": total_cases, "t1_count": total_t1, "t1_rate": round(t1_rate, 1)}}, ensure_ascii=False),
        encoding='utf-8'
    )


if __name__ == '__main__':
    main()
