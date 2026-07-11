#!/usr/bin/env python3
"""
PRC-US 法律语义对齐插件 v1.0
从对齐框架知识仓库加载阻断规则 + 功能映射，注入 pipeline 预检层
"""
import re, yaml, os
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ═══ 从对齐框架提取的 22 条绝对阻断规则 ═══
# 注：框架已完全吸收至 configs/prc_us_alignment/，此为管道内联副本
# 格式: {US概念 → (阻断说明, 中国法替代方案)}
HARD_BLOCKS = {
    "consideration": ("对价", "中国合同成立不以对价为要件，以意思表示一致为准"),
    "discovery": ("全面证据开示", '建议"证据交换"，范围远小于美式discovery'),
    "miranda rights": ("米兰达权利", "建议刑事诉讼权利告知"),
    "estate tax": ("遗产税", "替换为契税/个人所得税/印花税"),
    "gift tax": ("赠与税", "替换为个人所得税"),
    "adverse possession": ("逆权占有", "无功能替代，中国法不存在取得时效"),
    "chevron deference": ("谢弗林遵从", "中国行政诉讼中法院对行政行为独立审查"),
    "at-will employment": ("自由雇佣", '强制替换为"法定解雇限制制"'),
    "punitive damages": ("惩罚性赔偿", "仅限消法/食品安全法/知产/环境特定情形"),
    "class action": ("集团诉讼", '替换为"代表人诉讼"或"公益诉讼"'),
    "jury trial": ("陪审团审理", "中国无陪审团制度，适用合议庭审理"),
    "summary judgment": ("简易判决", "中国无该制度，适用简易程序"),
    "equitable relief": ("衡平法救济", "功能替代为停止侵害/排除妨害/消除危险"),
    "injunction": ("禁令", "近似功能：行为保全/先予执行"),
    "contempt of court": ("藐视法庭", "功能替代：妨害民事诉讼强制措施"),
    "privity of contract": ("合同相对性", "中国法也有相对性但更强调实质利害关系"),
    "promissory estoppel": ("允诺禁反言", "功能近似：缔约过失责任"),
    "unjust enrichment": ("不当得利", "基本对应但构成要件不同"),
    "strict liability": ("严格责任", "侵权法部分领域适用"),
    "vicarious liability": ("雇主替代责任", "近似对应《民法典》第1191条"),
    "trespass to chattels": ("动产侵害", "转换为物权法/侵权法的相应请求权"),
    "market share liability": ("市场份额责任", "中国侵权法无该制度"),
}

# ═══ 功能映射表 — US Factors → CN AND ═══
FUNCTIONAL_MAP = {
    # US Factors-based → CN Binary AND
    "Material Breach": {
        "us_factors": ["受损利益程度", "补偿可能性", "违约方丧失", "转机可能性", "诚信"],
        "cn_atom": "Contract.Breach.FUNDAMENTAL",
        "cn_standard": "是否致使合同目的不能实现",
        "alignment": "5因素加权 → 二元判断",
    },
    "Due Diligence": {
        "us_factors": ["调查范围", "合理程度", "时间投入", "专业标准"],
        "cn_atom": "Defense.BLOCKED_NO_EQUIVALENT",
        "cn_standard": "替换为合理审查义务",
        "alignment": "阻断 + 近似功能替换",
    },
    "Fair Use": {
        "us_factors": ["使用目的", "作品性质", "使用量", "市场影响"],
        "cn_atom": "IP.Defense.FAIR_USE",
        "cn_standard": "著作权法规定的12种合理使用情形(封闭清单)",
        "alignment": "4因素开放清单转换为12种封闭情形",
    },
}


class AlignmentPlugin:
    """PRC-US 法律语义对齐插件 — 双向 + 统一扁平注册表"""

    def __init__(self, source: str = "US", target: str = "CN", auto_sync: bool = True):
        self.source = source
        self.target = target
        if auto_sync:
            try:
                self._sync_remote()
            except Exception:
                pass

    def check_block(self, text: str) -> List[Dict]:
        hits = []
        for rule in _compiled_registry:
            if rule["from"] != self.source or rule["to"] != self.target:
                continue
            if rule["action"] == "block" and rule["re"].search(text):
                hits.append({"pattern": rule["pattern"], "atom": rule["atom"]})
        return hits

    def map_factors(self, text: str) -> List[Dict]:
        results = []
        for rule in _compiled_registry:
            if rule["from"] != self.source or rule["to"] != self.target:
                continue
            if rule["action"] == "map" and rule["re"].search(text):
                results.append({"pattern": rule["pattern"], "atom": rule["atom"]})
        return results

    def enrich_facts(self, facts: dict, case_text: str) -> dict:
        """预检层：注入对齐后的阻断/映射事实"""
        # 1. 阻断检查 → 注入 Defense.* 异常
        blocks = self.check_block(case_text)
        for b in blocks:
            if b["action"] == "HARD_BLOCK":
                facts["Defense.BLOCKED_NO_EQUIVALENT"] = f"触及美国法制度'{b['us_concept']}'，中国法无对应，已阻断"
                facts[f"Defense.BLOCKED_{b['us_concept'].upper().replace(' ','_')}"] = b["block_reason"]

        # 2. 功能映射 → CN 原子替换
        mappings = self.map_factors(case_text)
        for m in mappings:
            facts[m["cn_atom"]] = f"功能映射自US概念'{m['us_concept']}'，策略: {m['alignment_strategy']}"

        return facts


# 全局单例
_plugin = None

def get_aligner() -> AlignmentPlugin:
    global _plugin
    if _plugin is None:
        _plugin = AlignmentPlugin()
    return _plugin


# ═══════════════════════════════════════════
# 前置看门狗 — 0.1ms 硬编码正则扫射（双向）
# 单一扁平注册表 + source/target 动态过滤
# ═══════════════════════════════════════════

# 全局唯一的对齐知识注册表（单源信赖）
# 格式：{from, to, action, pattern, atom}
# - action="block": 硬阻断，命中了就是致命对齐失败
# - action="map":   功能映射，将源法域概念转化为目标法域原子
#
# 开源贡献指南：美国开发者只需追加 {"from":"CN","to":"US",...} 行，
# 无需修改任何控制流代码。心智负担为零。
ALIGNMENT_REGISTRY = [
    # ═══ US → CN: 阻断美国法独有概念 ═══
    {"from":"US","to":"CN","action":"block","pattern":r"Due\s*Diligence|尽职调查|尽调","atom":"Defense.BLOCKED_US_DUE_DILIGENCE"},
    {"from":"US","to":"CN","action":"block","pattern":r"Punitive\s*Damages|惩罚性赔偿","atom":"Defense.BLOCKED_US_PUNITIVE_DAMAGES"},
    {"from":"US","to":"CN","action":"block","pattern":r"equitable\s*relief|衡平法救济|衡平救济","atom":"Defense.BLOCKED_US_EQUITABLE_RELIEF"},
    {"from":"US","to":"CN","action":"block","pattern":r"jury\s*trial|陪审团","atom":"Defense.BLOCKED_US_JURY_TRIAL"},
    {"from":"US","to":"CN","action":"block","pattern":r"at-will\s*employment|自由雇佣","atom":"Defense.BLOCKED_US_ATWILL_EMPLOYMENT"},
    {"from":"US","to":"CN","action":"block","pattern":r"costs?\s*follow\s*the\s*event|败诉方承担律师费","atom":"Defense.BLOCKED_US_COSTS_FOLLOW_EVENT"},
    {"from":"US","to":"CN","action":"block","pattern":r"class\s*action|集团诉讼","atom":"Defense.BLOCKED_US_CLASS_ACTION"},
    {"from":"US","to":"CN","action":"block","pattern":r"adverse\s*possession|逆权占有","atom":"Defense.BLOCKED_US_ADVERSE_POSSESSION"},
    {"from":"US","to":"CN","action":"block","pattern":r"summary\s*judgment|简易判决","atom":"Defense.BLOCKED_US_SUMMARY_JUDGMENT"},
    {"from":"US","to":"CN","action":"block","pattern":r"promissory\s*estoppel|允诺禁反言","atom":"Defense.BLOCKED_US_PROMISSORY_ESTOPPEL"},
    {"from":"US","to":"CN","action":"block","pattern":r"discovery\s*(?!of\s*service)","atom":"Defense.BLOCKED_US_DISCOVERY"},

    # ═══ US → CN: 功能映射（US Factors → CN AND 原子）═══
    {"from":"US","to":"CN","action":"map","pattern":r"Material\s*Breach|实质性违约|根本违约","atom":"Contract.Breach.FUNDAMENTAL"},
    {"from":"US","to":"CN","action":"map","pattern":r"Liquidated\s*Damage|约定损害赔偿|违约金","atom":"Contract.Relief.LIQUIDATED_DAMAGES"},
    {"from":"US","to":"CN","action":"map","pattern":r"Specific\s*Performance|强制履行|实际履行","atom":"Contract.Relief.SPECIFIC_PERFORMANCE"},

    # ═══ CN → US: 阻断中国法独有概念 ═══
    # CN概念进入US轨道时仅执行下列显式阻断映射；未列出的概念不得猜测转换。
    {"from":"CN","to":"US","action":"block","pattern":r"民事调解|法院调解|司法调解","atom":"Defense.BLOCKED_CN_JUDICIAL_MEDIATION"},
    {"from":"CN","to":"US","action":"block","pattern":r"执行异议之诉|案外人异议|执行异议","atom":"Defense.BLOCKED_CN_EXECUTION_OBJECTION"},
    {"from":"CN","to":"US","action":"block","pattern":r"先予执行|诉前保全|诉中保全","atom":"Defense.BLOCKED_CN_PRELIMINARY_REMEDY"},
    {"from":"CN","to":"US","action":"block","pattern":r"审判监督程序|再审审查|抗诉","atom":"Defense.BLOCKED_CN_RETRIAL_PROCEDURE"},
    {"from":"CN","to":"US","action":"block","pattern":r"代表人诉讼(?!.*class)","atom":"Defense.BLOCKED_CN_REPRESENTATIVE_ACTION"},
    {"from":"CN","to":"US","action":"block","pattern":r"公益诉讼(?!.*class)","atom":"Defense.BLOCKED_CN_PUBLIC_INTEREST_LITIGATION"},
    {"from":"CN","to":"US","action":"block","pattern":r"情势变更|情事变更","atom":"Defense.BLOCKED_CN_CHANGED_CIRCUMSTANCES"},
    {"from":"CN","to":"US","action":"block","pattern":r"违约金调减|酌减|违约金过高","atom":"Defense.BLOCKED_CN_PENALTY_ADJUSTMENT"},
    {"from":"CN","to":"US","action":"block","pattern":r"三倍赔偿|惩罚性赔偿.*(?:消法|食品安全)","atom":"Defense.BLOCKED_CN_TREBLE_DAMAGES"},
    {"from":"CN","to":"US","action":"block","pattern":r"公序良俗|社会公共利益","atom":"Defense.BLOCKED_CN_VAGUE_PUBLIC_POLICY"},

    # ═══ CN → US: 功能映射（CN 概念 → US 原子）═══
    # 功能映射只表达现有工程对齐，不宣称对应法源或结论等价。
    {"from":"CN","to":"US","action":"map","pattern":r"违约金调减|违约金酌减|违约金过高.*调","atom":"USCon.Relief.PENALTY_REDUCTION_UCC"},
    {"from":"CN","to":"US","action":"map","pattern":r"情势变更|情事变更","atom":"USCon.Defense.IMPOSSIBILITY_FRUSTRATION"},
    {"from":"CN","to":"US","action":"map","pattern":r"格式条款无效|格式合同无效|霸王条款","atom":"USCon.Defense.UNCONSCIONABILITY"},
    {"from":"CN","to":"US","action":"map","pattern":r"缔约过失责任|缔约过失","atom":"USCon.Relief.PROMISSORY_ESTOPPEL"},
]

# 预编译所有正则（一次性）
_compiled_registry = [
    {**r, "re": re.compile(r["pattern"], re.IGNORECASE)}
    for r in ALIGNMENT_REGISTRY
]

def run_alignment_watchdog(case_text: str, source: str = "US", target: str = "CN") -> dict:
    """
    前置看门狗 — 单一扁平注册表 + source/target 动态过滤。

    用法:
        run_alignment_watchdog(text, source="US", target="CN")  # 中国人审美国合同
        run_alignment_watchdog(text, source="CN", target="US")  # 美国人审中国合同

    Args:
        case_text: 案卷原始文本
        source:    源文本法域 ("US" / "CN")
        target:    目标引擎法域 ("US" / "CN")
    """
    pre_triggered = {}
    block_reasons = []
    is_blocked = False

    # 动态过滤：只扫描当前方向的规则
    for rule in _compiled_registry:
        if rule["from"] != source or rule["to"] != target:
            continue
        if rule["re"].search(case_text):
            pre_triggered[rule["atom"]] = True
            if rule["action"] == "block":
                is_blocked = True
                block_reasons.append(f"[{source}→{target} 阻断] {rule['pattern']}")

    return {
        "is_blocked": is_blocked,
        "pre_triggered_atoms": pre_triggered,
        "block_reasons": block_reasons,
        "direction": f"{source}→{target}",
    }
