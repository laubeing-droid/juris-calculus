#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Juris-Calculus 法域蒸馏工作台 v1.0
=====================================
输入: 新法域的法律文本 (PDF/TXT) + L0 Schema + 121K 词典索引
输出: 候选 Horn 规则集 (configs/{jurisdiction}/rules.yaml)

管线:
  法律文本 → 术语提取(词典索引) → L0原语映射 → Horn骨架生成 → 本体校验 → 人工审核

用法:
  python tools/distill_jurisdiction.py --input uk_sale_of_goods.txt --jurisdiction uk --family common_law
  python tools/distill_jurisdiction.py --input es_codigo_civil.txt --jurisdiction es --family civil_law
"""
import sys, os, re, json, yaml, argparse
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field

# ─── 配置路径 ───
BASE = Path(__file__).resolve().parents[1]
CONFIGS = BASE / "configs"
LEXICON_INDEX = CONFIGS / "lexicon_index.json"
ONTOLOGY = CONFIGS / "core_ontology.yaml"


@dataclass
class DistilledTerm:
    """蒸馏出的法律术语"""
    raw_term: str          # 原文中的术语
    mapped_concept: str     # 映射到的 L2 概念
    L0_primitive: str       # 映射到的 L0 原语
    confidence: float       # 映射置信度
    context: str            # 原文上下文


@dataclass
class HornCandidate:
    """候选 Horn 规则"""
    rule_id: str
    premise_atoms: List[str]
    head_claim: str
    concepts: List[str]
    exception_chain: List[str]
    head_type: str           # HORN / NON_HORN
    legal_basis: str         # 法条出处
    source_text: str         # 原始条文
    L0_verified: bool = False
    validation_issues: List[str] = field(default_factory=list)


class DistillationWorkbench:
    """法域蒸馏工作台"""

    def __init__(self):
        self.lexicon: Dict[str, List[str]] = {}
        self.ontology: Dict = {}
        self.L0_schema: Dict = {}
        self.L1_meta: Dict = {}
        self._loaded = False

    # ═══════════════════════════════════════════
    # Phase 1: Load knowledge base
    # ═══════════════════════════════════════════

    def load(self):
        """加载词典索引 + 本体 + L0 Schema"""
        if LEXICON_INDEX.exists():
            with open(LEXICON_INDEX, "r", encoding="utf-8") as f:
                self.lexicon = json.load(f)
        if ONTOLOGY.exists():
            with open(ONTOLOGY, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            self.ontology = raw.get("concepts", {})
            self.L0_schema = raw.get("L0_schema", {}).get("schemas", {})
            self.L1_meta = raw.get("L1_meta_ontology", {}).get("concepts", {})
        self._loaded = True
        print(f"  Lexicon: {sum(len(v) for v in self.lexicon.values())} terms, {len(self.lexicon)} domains")
        print(f"  Ontology: {len(self.ontology)} L2 concepts, {len(self.L0_schema)} L0 schemas")

    # ═══════════════════════════════════════════
    # Phase 2: Term extraction via lexicon index
    # ═══════════════════════════════════════════

    def extract_terms(self, text: str, target_domain: str = "contract") -> List[DistilledTerm]:
        """扫描法律文本，用词典索引提取术语并映射到 L0 原语"""
        terms = []
        seen = set()
        text_lower = text.lower()

        # 优先目标领域词典
        domain_terms = set(self.lexicon.get(target_domain, []))

        for term in domain_terms:
            if term in seen or len(term) < 4:
                continue
            if term in text_lower:
                seen.add(term)
                # 提取上下文
                idx = text_lower.find(term)
                ctx = text[max(0, idx - 40): idx + len(term) + 40]
                # 尝试映射到 L0
                l0, l2 = self._map_to_L0(term)
                terms.append(DistilledTerm(
                    raw_term=term,
                    mapped_concept=l2,
                    L0_primitive=l0,
                    confidence=0.7 if l0 else 0.3,
                    context=ctx[:120].strip()
                ))
        return terms

    def _map_to_L0(self, term: str) -> tuple:
        """将术语映射到 L0 原语 + L2 概念"""
        term_l = term.lower()
        # 关键词 → L0 原语快速映射
        kw_to_L0 = {
            "contract": "Act",
            "sale": "Act", "sell": "Act", "buy": "Act",
            "deliver": "Act", "payment": "Act", "pay": "Act",
            "warrant": "Status", "guarantee": "Status",
            "title": "Power", "ownership": "Power", "property": "Asset",
            "goods": "Asset", "asset": "Asset",
            "breach": "Status", "default": "Status",
            "damages": "Act", "remedy": "Act",
            "fraud": "Defect", "mistake": "Defect", "duress": "Defect",
            "capacity": "Agent", "party": "Agent", "buyer": "Agent", "seller": "Agent",
            "void": "Status", "voidable": "Status",
            "consideration": "Status",
            "performance": "Act", "specific performance": "Act",
            "condition": "Status", "term": "Status",
            "exclusion": "Defect", "limitation": "Defect",
            "agent": "Agent", "principal": "Agent",
            "negligence": "Defect", "tort": "Defect",
        }
        for kw, l0 in kw_to_L0.items():
            if kw in term_l:
                return l0, term  # L2 = term itself for now
        return "", term

    # ═══════════════════════════════════════════
    # Phase 3: Horn rule generation from extracted terms
    # ═══════════════════════════════════════════

    def generate_horn_candidates(
        self, text: str, terms: List[DistilledTerm], jurisdiction: str, family: str
    ) -> List[HornCandidate]:
        """从提取的术语和原文中生成候选 Horn 规则骨架"""
        candidates = []
        sections = self._split_sections(text)

        for i, section in enumerate(sections):
            if len(section) < 50:
                continue
            # 提取 section 编号
            sec_num = self._extract_section_number(section)
            # 提取核心名词短语作为概念
            concepts = self._extract_concepts(section)
            # 尝试识别 if-then 结构
            atoms, head, is_horn = self._detect_horn_structure(section, terms, family)

            if atoms and head:
                rid = f"{jurisdiction.upper()}-S{sec_num or i+1}"
                candidates.append(HornCandidate(
                    rule_id=rid,
                    premise_atoms=atoms,
                    head_claim=head,
                    concepts=concepts[:5],
                    exception_chain=[],
                    head_type="HORN" if is_horn else "NON_HORN",
                    legal_basis=f"§{sec_num}" if sec_num else f"Section {i+1}",
                    source_text=section[:300]
                ))

        # L0 Schema 校验
        for c in candidates:
            c.L0_verified, c.validation_issues = self._validate_against_L0(c, family)

        return candidates

    def _split_sections(self, text: str) -> List[str]:
        """按 section/条 拆分文本"""
        parts = re.split(r'(?:(?:Section|SECTION|§|第)\s*\d+[\.\s])', text)
        if len(parts) <= 1:
            parts = re.split(r'\n\n+', text)
        return [p.strip() for p in parts if len(p.strip()) > 30]

    def _extract_section_number(self, text: str) -> str:
        m = re.search(r'(?:Section|§|第)\s*(\d+[A-Za-z]*)', text)
        return m.group(1) if m else ""

    def _extract_concepts(self, text: str) -> List[str]:
        """提取文本中的法律概念词"""
        concepts = []
        text_l = text.lower()
        # 从本体中匹配概念
        for concept_name in self.ontology:
            aliases = self.ontology[concept_name].get("aliases", [])
            mapping = self.ontology[concept_name].get("mapping", {})
            search_terms = [concept_name.lower()] + [a.lower() for a in aliases]
            for cn_term in mapping.values():
                search_terms.append(cn_term.lower())
            for st in search_terms:
                if len(st) > 3 and st in text_l and concept_name not in concepts:
                    concepts.append(concept_name)
                    break
        return concepts

    def _detect_horn_structure(
        self, text: str, terms: List[DistilledTerm], family: str
    ) -> tuple:
        """检测文本中的 if-then 逻辑结构，提取 premise_atoms 和 head_claim"""
        atoms = []
        head = ""

        # 关键词模式匹配
        condition_kws = ["if", "where", "when", "provided that", "subject to"]
        result_kws = ["then", "shall", "must", "is", "the court may"]

        has_condition = any(kw in text.lower() for kw in condition_kws)
        has_result = any(kw in text.lower() for kw in result_kws)

        if not has_condition:
            return [], "", False

        # 从术语中提取原子
        for t in terms:
            if t.raw_term in text.lower() and t.L0_primitive:
                atom_name = t.raw_term.replace(" ", "_").replace("-", "_").title()
                if atom_name not in atoms:
                    atoms.append(atom_name)

        # 从 L0 Schema 推断 head
        status_terms = [t for t in terms if t.L0_primitive == "Status"]
        if status_terms:
            head = f"Status_{status_terms[0].raw_term.replace(' ', '')}"
        else:
            head = "Legal_Effect_Established"

        return atoms, head, has_result

    def _validate_against_L0(self, candidate: HornCandidate, family: str) -> tuple:
        """用 L0 Schema 校验候选规则"""
        issues = []
        if not self.L0_schema:
            return True, issues

        # 检查前提原子是否可映射到 L0
        mapped_count = 0
        for atom in candidate.premise_atoms:
            # 模糊匹配：atom 名称是否包含已知 L0 范畴
            if any(p.lower() in atom.lower() for p in self.L0_schema):
                mapped_count += 1

        if mapped_count == 0 and candidate.premise_atoms:
            issues.append(f"前提原子无法映射到任何 L0 原语")

        # 检查 head 是否属于可识别的 L0 范畴
        head_mapped = any(p.lower() in candidate.head_claim.lower() for p in self.L0_schema)
        if not head_mapped:
            issues.append(f"结论主张无法映射到 L0 原语")

        return len(issues) == 0, issues

    # ═══════════════════════════════════════════
    # Phase 4: Output
    # ═══════════════════════════════════════════

    def export_rules(self, candidates: List[HornCandidate], jurisdiction: str) -> str:
        """将候选规则导出为 YAML"""
        rules = []
        for c in candidates:
            rules.append({
                "id": c.rule_id,
                "premise_atoms": c.premise_atoms,
                "head_claim": c.head_claim,
                "concepts": c.concepts,
                "exception_chain": c.exception_chain,
                "head_type": c.head_type,
                "mechanical_exception": True,
                "namespace": f"{jurisdiction}_contract",
                "legal_basis": c.legal_basis,
                "source_text": c.source_text[:200],
                "L0_verified": c.L0_verified,
            })

        output_path = CONFIGS / jurisdiction / "rules_candidates.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump({"rules": rules, "meta": {"jurisdiction": jurisdiction, "auto_generated": True, "requires_human_review": True}}, f, allow_unicode=True, sort_keys=False, width=200)
        return str(output_path)

    def generate_report(self, terms: List[DistilledTerm], candidates: List[HornCandidate], jurisdiction: str) -> str:
        """生成蒸馏报告"""
        verified = sum(1 for c in candidates if c.L0_verified)
        total_horn = sum(1 for c in candidates if c.head_type == "HORN")

        report = f"""
══════════════════════════════════════════════
 Juris-Calculus 法域蒸馏报告: {jurisdiction.upper()}
══════════════════════════════════════════════

Phase 2 — 术语提取
  词典命中: {len(terms)} 个术语
  L0 映射成功: {sum(1 for t in terms if t.L0_primitive)} / {len(terms)}

Phase 3 — Horn 规则生成
  候选规则: {len(candidates)} 条
  HORN: {total_horn} | NON_HORN: {len(candidates) - total_horn}
  L0 Schema 校验通过: {verified} / {len(candidates)}

Phase 4 — 下一步
  1. 打开 configs/{jurisdiction}/rules_candidates.yaml
  2. 逐条审核 premise_atoms 和 head_claim
  3. 手动修正 L0_verified=false 的规则
  4. 重命名为 rules.yaml
  5. 运行: python tools/verify_migration.py --dir configs/{jurisdiction}
"""
        return report


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="juris-calculus 法域蒸馏工作台")
    parser.add_argument("--input", required=True, help="法律文本文件路径")
    parser.add_argument("--jurisdiction", required=True, help="法域代码 (uk/es/in/sg...)")
    parser.add_argument("--family", default="common_law", choices=["common_law", "civil_law"], help="法系")
    parser.add_argument("--domain", default="contract", help="目标领域")
    parser.add_argument("--output-dir", help="输出目录 (默认 configs/{jurisdiction}/)")
    args = parser.parse_args()

    # Load input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"文件不存在: {args.input}")
        sys.exit(1)
    text = input_path.read_text(encoding="utf-8", errors="replace")
    print(f"Input: {len(text)} chars, {len(text.split())} words")

    # Run pipeline
    wb = DistillationWorkbench()
    wb.load()

    # Phase 2
    terms = wb.extract_terms(text, args.domain)
    print(f"\n[Phase 2] Extracted {len(terms)} terms")
    for t in terms[:5]:
        print(f"  {t.raw_term[:40]:40s} → L0={t.L0_primitive:8s} L2={t.mapped_concept[:30]}")

    # Phase 3
    candidates = wb.generate_horn_candidates(text, terms, args.jurisdiction, args.family)
    print(f"\n[Phase 3] Generated {len(candidates)} Horn candidates")
    for c in candidates[:5]:
        status = "✅" if c.L0_verified else "⚠️"
        print(f"  {status} {c.rule_id:15s} | {c.head_claim[:40]:40s} | atoms={len(c.premise_atoms)}")

    # Phase 4
    output = wb.export_rules(candidates, args.jurisdiction)
    print(f"\n[Phase 4] Exported to {output}")

    # Report
    print(wb.generate_report(terms, candidates, args.jurisdiction))


if __name__ == "__main__":
    main()
