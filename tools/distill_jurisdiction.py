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


# ═══════════════════════════════════════════════════════════
# State-Level Topological Router — US 50-State Coverage
# ═══════════════════════════════════════════════════════════

def load_state_router(router_path: str = None) -> dict:
    """加载州级路由表"""
    if router_path is None:
        router_path = str(Path(__file__).resolve().parents[1] / "configs" / "en_US" / "state_router.yaml")
    with open(router_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def route_state_law_to_backbone(raw_state_fact: str, state_code: str = None, router: dict = None) -> dict:
    """
    将美国任意州的特有地方黑话,通过语义签名匹配,
    无缝路由回四大拓扑主干 (DE_CORPORATE / LONG_ARM / CFA_PUNITIVE / DEFAULT_UCC).

    Args:
        raw_state_fact: 州法术语或fact名 (e.g. "CA_BP_17200_unfair_competition")
        state_code: 可选的两字母州代码 (e.g. "CA", "TX", "DE")
        router: 预加载的路由表 (避免重复IO)

    Returns:
        {
            "backbone": "LONG_ARM",
            "standard_label": "US_STANDARD_AGGRESSIVE_LONG_ARM",
            "trigger_facts": ["US_Long_Arm_Jurisdiction_Asserted"],
            "cross_rails": {"hk": "...", "prc": "..."},
            "matched_by": "state_code" | "keyword_signature" | "fact_pattern"
        }
    """
    if router is None:
        router = load_state_router()

    routing = router.get("routing_table", {})
    engine = router.get("router_engine", {})

    # ═══ 优先级1: 精确州代码匹配 (支持多标签) ═══
    if state_code and state_code.upper() in engine.get("state_to_backbone", {}):
        backbone = engine["state_to_backbone"][state_code.upper()]
        # Gemini审计: CA multi-label — 同时命中 LONG_ARM + CFA_PUNITIVE
        multi_labels = state_code.upper() in _MULTI_LABEL_STATES
        model = routing.get(backbone, {})
        result = {
            "backbone": backbone,
            "standard_label": model.get("target_backbone", ""),
            "trigger_facts": [],
            "cross_rails": {
                "hk": model.get("cross_rail_hk", ""),
                "prc": model.get("cross_rail_prc", "")
            },
            "states": model.get("states", []),
            "matched_by": "state_code",
        }
        if multi_labels:
            result["multi_label"] = True
            result["additional_backbones"] = _MULTI_LABEL_STATES[state_code.upper()]
        return result

    # ═══ 优先级2: 事实模式匹配 ═══
    fact_lower = raw_state_fact.lower()
    for entry in engine.get("fact_pattern_to_backbone", []):
        pattern = entry["pattern"]
        if re.search(pattern, fact_lower, re.IGNORECASE):
            backbone = entry["backbone"]
            model = routing.get(backbone, {})
            return {
                "backbone": backbone,
                "standard_label": model.get("target_backbone", ""),
                "trigger_facts": entry.get("trigger_facts", []),
                "cross_rails": {
                    "hk": model.get("cross_rail_hk", ""),
                    "prc": model.get("cross_rail_prc", "")
                },
                "states": model.get("states", []),
                "matched_by": f"fact_pattern: {pattern[:50]}",
            }

    # ═══ 优先级3: 州级关键词签名匹配 ═══
    for backbone, model in routing.items():
        if backbone == "DEFAULT_UCC":
            continue
        for sig in model.get("keyword_signatures", []):
            if re.search(sig, fact_lower, re.IGNORECASE):
                return {
                    "backbone": backbone,
                    "standard_label": model.get("target_backbone", ""),
                    "trigger_facts": [],
                    "cross_rails": {
                        "hk": model.get("cross_rail_hk", ""),
                        "prc": model.get("cross_rail_prc", "")
                    },
                    "states": model.get("states", []),
                    "matched_by": f"keyword: {sig[:50]}",
                }

    # ═══ 降级: 默认UCC/联邦通用 ═══
    default = routing.get("DEFAULT_UCC", {})
    return {
        "backbone": "DEFAULT_UCC",
        "standard_label": default.get("target_backbone", "US_STANDARD_DEFAULT_UCC"),
        "trigger_facts": [],
        "cross_rails": {"hk": "", "prc": ""},
        "states": default.get("states", []),
        "matched_by": "fallback_default",
    }


def generate_state_fact_injection(term: str, state_code: str = None, router: dict = None) -> dict:
    """
    为长尾术语生成骨干模型对齐后的标准事实注入集。

    返回: {fact_name: confidence, ...} 可直接注入 press_long_tail 或 TriRailCollider
    """
    route = route_state_law_to_backbone(term, state_code, router)

    facts = {route["standard_label"]: 0.90}

    for tf in route.get("trigger_facts", []):
        facts[tf] = 0.88

    # 根据骨干模型追加特征事实
    backbone = route["backbone"]
    if backbone == "DE_CORPORATE":
        facts["Director_Duty_Breach_Potential"] = 0.85
        facts["Affiliated_Companies_Asset_Confusion"] = 0.82
    elif backbone == "LONG_ARM":
        facts["US_Long_Arm_Jurisdiction_Asserted"] = 0.90
        facts["Cross_Border_Context"] = 1.0
    elif backbone == "CFA_PUNITIVE":
        facts["US_Punitive_Damages_Potential"] = 0.88
        facts["US_Pre_Trial_Discovery"] = 0.85

    return facts


# ═══════════════════════════════════════════════════════════
# FastPathInterceptor — 威胁签名物理降维挂钩
# ═══════════════════════════════════════════════════════════

class FastPathInterceptor:
    """
    威胁情报拦截器——TriRailCollider 的预处理哨兵。

    行为:
      扫描共享事实池→匹配WI/NJ威胁签名→命中则旁路全部Horn推演
      → 直接返回 CBL 阻断指令(不经过Fixpoint迭代)

    设计原则:
      平时: 零开销——无匹配则返回None, 对撞机照常走三轨流程
      战时: 烧断US轨——检测到高威胁签名, 直接返回PRC CBL指令
    """

    def __init__(self, signature_dir: str = None):
        if signature_dir is None:
            signature_dir = str(Path(__file__).resolve().parents[1] / "configs" / "us" / "threat_signatures")
        self.signatures = self._load_all_signatures(signature_dir)

    def _load_all_signatures(self, sig_dir: str) -> list:
        """加载全部威胁签名YAML文件"""
        all_sigs = []
        sig_path = Path(sig_dir)
        if not sig_path.exists():
            return all_sigs

        for yf in sig_path.glob("*.yaml"):
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    sigs = data.get("signatures", [])
                    for s in sigs:
                        s["_source_file"] = yf.name
                    all_sigs.extend(sigs)
            except Exception:
                pass

        return sorted(all_sigs, key=lambda s: {
            "CRITICAL": 0, "HIGH": 1, "MEDIUM": 2
        }.get(s.get("threat_level", ""), 99))

    def intercept(self, shared_facts: list) -> dict or None:
        """
        扫描共享事实池, 检测高威胁签名。

        Args:
            shared_facts: 事实ID列表 (str) 或 Dict[str, LegalFact]

        Returns:
            None  → 无威胁, 正常走三轨流程
            dict  → 检测到威胁, 返回CBL旁路指令
        """
        if isinstance(shared_facts, dict):
            fact_names = list(shared_facts.keys())
        elif isinstance(shared_facts, list):
            fact_names = shared_facts
        else:
            return None

        # 将所有事实名拼接为一个可搜索的字符串
         # v2.0: US Code citation validation against blueprint
        try:
            from compiler_core.us_lookup import validate_usc_citation
            citations = validate_usc_citation(fact_blob)
            for cit in citations:
                if not cit.get("valid"):
                    return {
                        "intercepted": True,
                        "signature_id": "USC_INVALID_TITLE",
                        "threat_level": "HIGH",
                        "action": "FORCE_SUPPRESS",
                        "target_rule": cit.get("citation", ""),
                        "reason": f"Invalid US Code: Title {cit.get("title","?")}",
                        "method": "USC_VALIDATION",
                        "source_file": "blueprint:united_states_code",
                    }
        except Exception:
            pass

        fact_blob = " | ".join(fact_names)

        for sig in self.signatures:
            for pat in sig.get("pattern", []):
                # 管道分隔的多模式: 逐个匹配而非整体escape
                sub_patterns = [p.strip() for p in pat.split("|")]
                for sp in sub_patterns:
                    if not sp:
                        continue
                if re.search(re.escape(sp), fact_blob, re.IGNORECASE):
                    return {
                        "intercepted": True,
                        "signature_id": sig["signature_id"],
                        "threat_level": sig.get("threat_level", "MEDIUM"),
                        "action": sig.get("action", "FORCE_SUPPRESS"),
                        "target_rule": sig.get("target_rule", ""),
                        "reason": sig.get("description", ""),
                        "method": "FAST_PATH_BYPASS",
                        "source_file": sig.get("_source_file", ""),
                        # P2: sovereignty audit trail
                        "sovereignty_audit": {
                            "gate": "FastPathInterceptor",
                            "bypassed_validation": ["LegalTaskSchema.is_prc_sovereign_boundary"],
                            "forced_operators": [sig.get("target_rule", "")],
                            "sovereignty_anchored": True,
                            "settlement_blocked": True,
                            "timestamp": __import__('datetime').datetime.now().isoformat(),
                        },
                    }

        return None

    def get_threat_report(self, shared_facts: list) -> list:
        """返回所有匹配的威胁(不阻断, 仅报告)"""
        hits = []
        if isinstance(shared_facts, dict):
            fact_names = list(shared_facts.keys())
        elif isinstance(shared_facts, list):
            fact_names = shared_facts
        else:
            return hits

        fact_blob = " | ".join(fact_names)

        for sig in self.signatures:
            for pat in sig.get("pattern", []):
                if re.search(re.escape(pat), fact_blob, re.IGNORECASE):
                    hits.append({
                        "signature_id": sig["signature_id"],
                        "threat_level": sig.get("threat_level", "MEDIUM"),
                        "matched_pattern": pat,
                        "action": sig.get("action", ""),
                    })
                    break  # 每条签名只报告一次

        return hits


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════
# Gemini审计: 加州/纽约/华盛顿为多标签路由
# 同时具有 LONG_ARM + CFA_PUNITIVE 双重身份
# ═══════════════════════════════════════
_MULTI_LABEL_STATES = {
    "CA": ["LONG_ARM", "CFA_PUNITIVE"],
    "NY": ["LONG_ARM", "CFA_PUNITIVE"],
    "WA": ["LONG_ARM", "CFA_PUNITIVE"],
}
