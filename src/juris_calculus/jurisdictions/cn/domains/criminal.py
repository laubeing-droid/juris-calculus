#!/usr/bin/env python3
"""中国法域 — 刑事犯罪核心 Provider"""
from src.juris_calculus.core.base import BaseDomainProvider

class CNCriminalProvider(BaseDomainProvider):
    @property
    def domain_id(self) -> str: return "criminal"
    @property
    def jurisdiction(self) -> str: return "cn"
    @property
    def atom_registry(self) -> dict:
        return {
            "致人重伤": "Crim.Objective.SEVERE_INJURY",
            "致人死亡": "Crim.Objective.DEATH",
            "秘密窃取": "Crim.Objective.SECRET_STEALING",
            "暴力胁迫": "Crim.Objective.FORCE_INTIMIDATION",
            "数额巨大": "Crim.Objective.LARGE_AMOUNT",
            "利用职务便利": "Crim.Objective.ABUSE_OF_OFFICE",
            "直接故意": "Crim.Subjective.DIRECT_INTENT",
            "间接故意": "Crim.Subjective.INDIRECT_INTENT",
            "正当防卫": "Crim.Justification.SELF_DEFENSE",
            "防卫过当": "Crim.Justification.EXCESSIVE_DEFENSE",
            "紧急避险": "Crim.Justification.NECESSITY",
            "自首": "Crim.Mitigation.SURRENDER",
            "立功": "Crim.Mitigation.MERITORIOUS",
            "认罪认罚": "Crim.Mitigation.GUILTY_PLEA",
            "退赃退赔": "Crim.Mitigation.RESTITUTION",
            "累犯": "Crim.Aggravation.RECIDIVISM",
            "主犯": "Crim.Role.PRINCIPAL",
            "从犯": "Crim.Role.ACCESSORY",
            "非法证据排除": "Crim.Exclusion.ILLEGAL_EVIDENCE",
            "刑讯逼供": "Crim.Exclusion.TORTURE",
        }
    @property
    def rules(self) -> list:
        import yaml
        from compiler_core.evaluator import load_rules_from_yaml
        from pathlib import Path
        p = Path(__file__).resolve().parents[5] / "configs" / "zh_CN" / "rules.yaml"
        return load_rules_from_yaml(str(p)) if p.exists() else []
    @property
    def concepts(self) -> list:
        return ["犯罪构成要件","自首认定","立功认定","共同犯罪区分","正当防卫界限","非法证据排除","认罪认罚从宽","数罪并罚规则","缓刑适用条件"]
