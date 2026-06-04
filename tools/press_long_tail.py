#!/usr/bin/env python3
"""
press_long_tail.py — 美国法长尾术语饱和攻击引擎 v1.2.0
══════════════════════════════════════════════════════════
输入: uscourts.gov 242条全新术语 (A-W)
输出: long_tail_collision_matrix.json — 仅保留 COLLISION + ASYMMETRY

管道:
  [242 Raw Terms] → [L0 Atomic Converter] → [Dict[str, LegalFact]]
  → [TriRailCollider (HK×US×PRC)] → [Filter: COLLISION | ASYMMETRY]
══════════════════════════════════════════════════════════
"""

import sys
import json
import copy
import re
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compiler_core.types import LegalFact, IRState
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig, LegalDomain
from adapter.prc_adapter import PRCAdapter


# ═══════════════════════════════════════════
# 242 条全新术语 (uscourts.gov A-W)
# ═══════════════════════════════════════════

USCOURTS_GLOSSARY = [
    # A (21) — 排除已在81条中的: Acquittal, Adversary proceeding, Affirmed, Automatic stay, Assets
    "Administrative law judge", "Administrative Office of the United States Courts (AO)", "Admissible",
    "Affidavit", "Alternate juror", "Alternative dispute resolution (ADR)", "Amicus curiae",
    "Answer", "Appeal", "Appellant", "Appellate", "Appellee", "Arbitration", "Arraignment",
    "Article III judge", "Assume",
    # B (12)
    "Bail", "Bankruptcy", "Bankruptcy administrator", "Bankruptcy code", "Bankruptcy court",
    "Bankruptcy estate", "Bankruptcy judge", "Bankruptcy petition", "Bench trial",
    "Brief", "Burden of proof", "Business bankruptcy",
    # C (41)
    "Capital offense", "Case ancillary to a foreign proceeding", "Case file", "Case law",
    "Caseload", "Cause of action", "Chambers", "Chapter 11", "Chapter 12", "Chapter 13",
    "Chapter 13 trustee", "Chapter 15", "Chapter 7", "Chapter 7 trustee", "Chapter 9",
    "Chief judge", "Circuit Executive", "Claim", "Class action", "Clerk of court",
    "Collateral", "Common law", "Community service", "Complaint", "Concurrent sentence",
    "Confirmation", "Consecutive sentence", "Consumer bankruptcy", "Consumer debtor",
    "Consumer debts", "Contested matter", "Contingent claim", "Contract", "Conviction",
    "Counsel", "Count", "Court", "Court of International Trade", "Court reporter",
    "Credit counseling", "Creditor",
    # D (18)
    "Damages", "De facto", "De jure", "De novo", "Debtor", "Declaratory judgment",
    "Default judgment", "Defendant", "Deposition", "Discharge", "Dischargeable debt",
    "Disclosure statement", "Discovery", "Dismissal with prejudice", "Dismissal without prejudice",
    "Disposable income", "Docket", "Due process",
    # E (11)
    "En banc", "Equitable", "Equity", "Evidence", "Ex parte", "Exclusionary rule",
    "Exculpatory evidence", "Executory contracts", "Exempt assets", "Exemptions, exempt property",
    # F (8)
    "Family farmer", "Federal public defender", "Federal public defender organization",
    "Federal question jurisdiction", "Felony", "File", "Financial management", "Fraudulent transfer",
    # G (1)
    "Grand jury",
    # H (3)
    "Habeas corpus", "Hearsay", "Home confinement",
    # I (10)
    "Impeachment", "In camera", "In forma pauperis", "Inculpatory evidence", "Indictment",
    "Information", "Injunction", "Insider (bankruptcy)", "Interrogatories", "Issue",
    # J (10)
    "Joint administration", "Joint petition", "Judge", "Judgeship", "Judgment",
    "Judicial Conference of the United States", "Jurisdiction", "Jurisprudence", "Jury",
    "Jury instructions",
    # L (5)
    "Lawsuit", "Lien", "Liquidated claim", "Liquidation", "Litigation",
    # M (9)
    "Magistrate judge", "Means test", "Mediation", "Misdemeanor", "Mistrial",
    "Moot", "Motion", "Motion in Limine", "Motion to lift the automatic stay",
    # N (4)
    "No-asset case", "Nolo contendere", "Nondischargeable debt", "Nonexempt assets",
    # O (5)
    "Objection to discharge", "Objection to dischargeability", "Objection to exemptions",
    "Opinion", "Oral argument",
    # P (31)
    "Panel", "Parole", "Party", "Party in interest", "Per curiam", "Peremptory challenge",
    "Petit jury (or trial jury)", "Petition", "Petition preparer", "Petty offense",
    "Plaintiff", "Plan", "Plea", "Pleadings", "Postpetition transfer", "Prebankruptcy planning",
    "Precedent", "Preference (bankruptcy)", "Presentence report", "Pretrial conference",
    "Pretrial services", "Priority", "Priority claim", "Pro se", "Pro tem", "Probation",
    "Probation officer", "Procedure", "Proof of claim", "Property of the estate", "Prosecute",
    # R (6)
    "Reaffirmation agreement", "Recalled judge", "Record", "Redemption", "Remand", "Reverse",
    # S (23)
    "Sanction", "Schedules", "Section 341 meeting", "Secured creditor", "Secured debt",
    "Senior judge", "Sentence", "Sentencing guidelines", "Sequester", "Service of process",
    "Settlement", "Small business or Subchapter V case", "Standard of proof",
    "Statement of financial affairs", "Statement of intention", "Statute", "Statute of limitations",
    "Sua sponte", "Subordination", "Subpoena", "Subpoena duces tecum",
    "Substantive consolidation", "Summary judgment",
    # T (7)
    "Temporary restraining order", "Testimony", "Toll", "Tort", "Transcript", "Transfer", "Trustee",
    # U (9)
    "U.S. attorney", "U.S. trustee", "Undersecured claim", "Undue hardship (bankruptcy)",
    "Unlawful detainer action", "Unliquidated claim", "Unscheduled debt", "Unsecured claim", "Uphold",
    # V (3)
    "Venue", "Verdict", "Voir dire",
    # W (5)
    "Wage garnishment", "Warrant", "Witness", "Writ", "Writ of certiorari",
]


# ═══════════════════════════════════════════
# L0 原子转换器 (Pattern-based, no LLM)
# ═══════════════════════════════════════════

def term_to_l0_facts(term: str) -> Dict[str, float]:
    """
    将自然语言术语转换为 {fact_id: confidence} 字典。
    不用 LLM，使用关键词模式匹配。
    """
    facts: Dict[str, float] = {}
    term_lower = term.lower()
    
    # ── 生成 L0 原语触发事实 ──
    
    # Status 触发
    if any(kw in term_lower for kw in ["acquittal", "conviction", "verdict", "judgment", "sentence",
                                          "confirmation", "discharge", "dismissal", "stay", "injunction"]):
        facts[f"US_Status_{sanitize(term)}"] = 0.90
    
    # Act 触发
    if any(kw in term_lower for kw in ["trial", "hearing", "arraignment", "deposition", "discovery",
                                          "appeal", "motion", "petition", "complaint", "indictment",
                                          "testimony", "subpoena", "warrant", "arrest", "bail"]):
        facts[f"US_Act_{sanitize(term)}"] = 0.88
    
    # Power 触发
    if any(kw in term_lower for kw in ["jurisdiction", "authority", "trustee", "judge", "court",
                                          "attorney", "prosecutor", "defender", "counsel", "clerk"]):
        facts[f"US_Power_{sanitize(term)}"] = 0.85
    
    # Asset 触发
    if any(kw in term_lower for kw in ["debt", "claim", "estate", "property", "asset", "collateral",
                                          "lien", "garnishment", "damages", "exemption"]):
        facts[f"US_Asset_{sanitize(term)}"] = 0.87
    
    # Defect 触发
    if any(kw in term_lower for kw in ["fraud", "error", "bias", "prejudice", "violation",
                                          "misconduct", "contempt", "default", "dismissal"]):
        facts[f"US_Defect_{sanitize(term)}"] = 0.86
    
    # Agent 触发
    if any(kw in term_lower for kw in ["debtor", "creditor", "defendant", "plaintiff", "party",
                                          "witness", "juror", "officer"]):
        facts[f"US_Agent_{sanitize(term)}"] = 0.89
    
    # ── 特殊触发: 跨境敏感 ──
    if any(kw in term_lower for kw in ["foreign", "international", "cross", "extraterritorial"]):
        facts["Cross_Border_Context"] = 1.0
    
    # ── 破产触发 ──
    if any(kw in term_lower for kw in ["bankruptcy", "chapter", "liquidation", "discharge",
                                          "reorganization", "trustee", "estate", "debtor"]):
        facts["Bankruptcy_Petition_Filed"] = 0.92
        facts["Cross_Border_Context"] = 0.85
    
    # ── 刑事触发 ──
    if any(kw in term_lower for kw in ["criminal", "felony", "misdemeanor", "indictment",
                                          "grand jury", "plea", "sentence", "parole", "probation"]):
        facts["US_Criminal_Proceeding"] = 0.90
    
    # ── 证据触发 ──
    if any(kw in term_lower for kw in ["discovery", "evidence", "hearsay", "testimony",
                                          "deposition", "subpoena", "witness"]):
        facts["US_Pre_Trial_Discovery"] = 0.88
    
    # ── 雇佣触发 ──
    if any(kw in term_lower for kw in ["employment", "wage", "labor", "worker"]):
        facts["At_Will_Employment"] = 0.85
    
    # ── 数据触发 ──
    # GEMINI审计修正: data/privacy 仍然映射为数据出境，但 record/file 等通用词不再触发
    # "record" "file" "case file" 等通用诉讼术语不再自动映射为数据出境
    if any(kw in term_lower for kw in ["data export", "data transfer", "data privacy", "sensitive data", "state secret", "cross border data"]):
        facts["Cross_Border_Data_Transfer_To_US"] = 0.83
        facts["Identified_Sensitive_Data_Or_State_Secret"] = 0.90
    
    return facts


def sanitize(term: str) -> str:
    """清理术语名为合法 fact ID"""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', term)
    return clean.strip('_')[:60]


# ═══════════════════════════════════════════
# 饱和攻击引擎
# ═══════════════════════════════════════════

class LongTailPressEngine:
    """242条术语 × 三轨对撞 饱和攻击"""

    def __init__(self):
        base = Path(__file__).resolve().parents[1]

        # HK 引擎
        hk_rules_path = base / "configs" / "hk" / "rules.yaml"
        hk_overrides_path = base / "configs" / "L0_overrides_hk.yaml"
        hk_rules = load_rules_from_yaml(str(hk_rules_path))
        self.hk_engine = FixpointEvaluator(
            hk_rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=str(hk_overrides_path)
        )

        # US 引擎
        us_rules_path = base / "configs" / "en_US" / "US_Adapter.yaml"
        us_overrides_path = base / "configs" / "en_US" / "L0_overrides_us.yaml"
        us_rules = load_rules_from_yaml(str(us_rules_path))
        self.us_engine = FixpointEvaluator(
            us_rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=str(us_overrides_path)
        )

        # PRC 引擎
        self.prc_engine = PRCAdapter()

        # 分类器
        from tools.run_trirail_matrix import classify_tri_state
        self.classify = classify_tri_state

        print(f"[PressEngine] HK={len(hk_rules)} | US={len(us_rules)} | PRC={len(self.prc_engine.constraint_rules)}")

    def press_term(self, term: str, idx: int) -> Dict:
        """压榨单条术语"""
        fact_dict = term_to_l0_facts(term)
        facts = {
            k: LegalFact(id=k, description=f"{term} → {k}", extraction_confidence=v)
            for k, v in fact_dict.items()
        }

        # 三轨独立副本
        f_hk = copy.deepcopy(facts)
        f_us = copy.deepcopy(facts)
        f_prc = copy.deepcopy(facts)

        # HK
        hk_state = IRState(facts=f_hk)
        try:
            hk_state = self.hk_engine.evaluate(hk_state)
        except CriticalClarityFailure as e:
            if hasattr(e, 'partial_state') and e.partial_state is not None:
                hk_state = e.partial_state

        # US
        us_state = IRState(facts=f_us)
        try:
            us_state = self.us_engine.evaluate(us_state)
        except CriticalClarityFailure as e:
            if hasattr(e, 'partial_state') and e.partial_state is not None:
                us_state = e.partial_state

        # PRC
        prc_state = self.prc_engine.execute_prc_first_override(f_prc)

        # 分类
        classification = self.classify(hk_state, us_state, prc_state)

        # 状态提取
        hk_terminal = hk_state.state_tracker.get("Contract_Validity", "?")
        us_terminal = us_state.state_tracker.get("Contract_Validity", "?")
        if not hk_terminal:
            hk_terminal = "VALID" if hk_state.claims else "?"
        if not us_terminal:
            us_terminal = "VALID" if us_state.claims else "?"

        return {
            "term_id": f"TAIL_{idx+1:04d}",
            "term": term,
            "classification": classification,
            "hk_state": hk_terminal,
            "us_state": us_terminal,
            "hk_claims": list(hk_state.claims.keys()),
            "us_claims": list(us_state.claims.keys()),
            "prc_overrides": {
                "force_void": [
                    rid for rid, v in prc_state.items()
                    if v.get("type") == "FORCE_VOID"
                ],
                "force_suppress": [
                    rid for rid, v in prc_state.items()
                    if v.get("type") == "FORCE_SUPPRESS"
                ],
                "mapping_override": [
                    rid for rid, v in prc_state.items()
                    if v.get("type") == "MAPPING_OVERRIDE"
                ],
            },
            "total_prc_overrides": len(prc_state),
        }

    def run_saturation(self, terms: List[str] = None):
        """执行饱和攻击"""
        if terms is None:
            terms = USCOURTS_GLOSSARY

        print(f"\n[SATURATION] Pressing {len(terms)} long-tail terms through Tri-Rail Collider...")
        print(f"  Strategy: COLLISION + ASYMMETRY only (drop TRI_RESONANCE)\n")

        collisions = []
        asymmetries = []
        resonance = 0
        complex_parallax = 0
        errors = 0

        for i, term in enumerate(terms):
            try:
                result = self.press_term(term, i)
            except Exception as e:
                errors += 1
                continue

            cls = result["classification"]
            if cls == "CHINA_US_COLLISION":
                collisions.append(result)
            elif cls == "HK_CN_ASYMMETRY":
                asymmetries.append(result)
            elif cls == "TRI_RESONANCE":
                resonance += 1
            elif cls == "COMPLEX_PARALLAX":
                complex_parallax += 1
            else:
                errors += 1

            if (i + 1) % 20 == 0:
                tag = "C" * (len(collisions) % 5 + 1) if collisions else "."
                sys.stdout.write(f"\r  [{i+1:4d}/{len(terms)}] COLL={len(collisions)} ASYM={len(asymmetries)} RES={resonance} {tag}")
                sys.stdout.flush()

        print(f"\r  [{len(terms)}/{len(terms)}] COLL={len(collisions)} ASYM={len(asymmetries)} RES={resonance} CPLX={complex_parallax} ERR={errors}")
        print()

        # ── 统计 ──
        total = len(terms)
        print(f"=== Saturation Results ===")
        print(f"  Total terms pressed: {total}")
        print(f"  CHINA_US_COLLISION:  {len(collisions)} ({len(collisions)/total*100:.1f}%)")
        print(f"  HK_CN_ASYMMETRY:     {len(asymmetries)} ({len(asymmetries)/total*100:.1f}%)")
        print(f"  TRI_RESONANCE:       {resonance} ({resonance/total*100:.1f}%)")
        print(f"  COMPLEX_PARALLAX:    {complex_parallax} ({complex_parallax/total*100:.1f}%)")
        print(f"  Errors:              {errors}")

        # ── COLLISION 聚类 ──
        if collisions:
            prc_voider = Counter()
            for c in collisions:
                for fv in c["prc_overrides"]["force_void"]:
                    prc_voider[fv] += 1
                for fs in c["prc_overrides"]["force_suppress"]:
                    prc_voider[f"SUPPRESS:{fs}"] += 1

            print(f"\n  Top PRC override triggers in COLLISIONs:")
            for rule_id, count in prc_voider.most_common(10):
                print(f"    [{count}] {rule_id}")

        # ── ASYMMETRY 聚类 ──
        if asymmetries:
            asym_domains = Counter()
            for a in asymmetries:
                for ov in a["prc_overrides"]["mapping_override"]:
                    asym_domains[ov] += 1
            print(f"\n  Top MAPPING_OVERRIDE in ASYMMETRYs:")
            for rule_id, count in asym_domains.most_common(10):
                print(f"    [{count}] {rule_id}")

        # ── 保存 ──
        output_dir = Path(__file__).resolve().parents[1] / "configs" / "prc_us_alignment"
        report = {
            "metadata": {
                "version": "v1.2.0-TriRail-Saturation",
                "total_terms": total,
                "stats": {
                    "COLLISION": len(collisions),
                    "ASYMMETRY": len(asymmetries),
                    "TRI_RESONANCE": resonance,
                    "COMPLEX_PARALLAX": complex_parallax,
                    "ERROR": errors,
                }
            },
            "collisions": collisions,
            "asymmetries": asymmetries,
        }

        output_path = output_dir / "long_tail_collision_matrix.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        import os
        print(f"\n[OK] -> {output_path} ({os.path.getsize(output_path):,} bytes)")
        return report


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Long-Tail Saturation Engine v1.2.0")
    print(f"  {len(USCOURTS_GLOSSARY)} uscourts.gov terms -> Tri-Rail Collider")
    print("=" * 60)

    engine = LongTailPressEngine()
    results = engine.run_saturation()
