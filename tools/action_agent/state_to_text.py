# ═══════════════════════════════════════════════════════════
# state_to_text.py — 计算状态 → 律所法律用语映射表
# ═══════════════════════════════════════════════════════════
# 设计原则:
#   1. 确定性: 同一状态码永远映射到同一法律表述
#   2. 可引用: 每条映射附带具体法条引用
#   3. 风险分级: 红(紧急)/黄(预警)/绿(安全)
# ═══════════════════════════════════════════════════════════

from typing import Dict, List

# ── 分类 → 合伙人语调 ──
CLASSIFICATION_TEXT: Dict[str, Dict[str, str]] = {
    "CHINA_US_COLLISION": {
        "risk_level": "红色/紧急",
        "risk_tag": "RED",
        "tone": "系属违反中国法律强制性规定之行为，存在直接法律冲突。",
        "action": "立即阻断 / 拒绝履行 / 启动反措施",
        "signature_phrase": "鉴于上述事项涉及中华人民共和国法律强制性规定，本所建议立即采取阻断措施，不得执行或配合执行相关域外程序。",
    },
    "HK_CN_ASYMMETRY": {
        "risk_level": "黄色/预警",
        "risk_tag": "YELLOW",
        "tone": "系属中外法系冲突之灰色地带，存在法律适用的不对称风险。",
        "action": "庭外和解 / 战略性诉讼 / 备案观察",
        "signature_phrase": "鉴于上述事项在两法域间存在法律适用的不对称性，本所建议采取审慎策略，优先通过非诉讼途径解决争议。",
    },
    "TRI_RESONANCE": {
        "risk_level": "绿色/安全",
        "risk_tag": "GREEN",
        "tone": "三法域逻辑完全闭合，未发现法律效力冲突。",
        "action": "正常履行 / 无需特别措施",
        "signature_phrase": "经三法域对撞核查，未发现任何法律效力冲突，相关交易可正常推进。",
    },
    "COMPLEX_PARALLAX": {
        "risk_level": "黄色/预警",
        "risk_tag": "YELLOW",
        "tone": "存在高阶复杂视差，需人工审阅确认。",
        "action": "提交合伙人人审阅 / 启动深度审计",
        "signature_phrase": "鉴于系统检测到复杂法律视差，建议由资深合伙人进行人工审阅后出具最终意见。",
    },
}

# ── 状态码 → 法律意见 ──
STATE_TO_OPINION: Dict[str, Dict[str, str]] = {
    "SUPPRESSED": {
        "phrase": "该项主张因[法条]而丧失法律效力。",
        "template": "依据《{citation}》，{description}。该项主张依法丧失法律效力，不得作为请求权基础。",
        "action_tone": "依法予以驳回",
    },
    "FORCE_VOID": {
        "phrase": "该行为因违反中国法律强制性规定，自始无效。",
        "template": "依据《{citation}》，{description}。该等行为因违反中国法律强制性规定，自始无效(VOID AB INITIO)。",
        "action_tone": "绝对无效 — 不得执行",
    },
    "FORCE_SUPPRESS": {
        "phrase": "该域外权力因触发中国法域主权阻断而丧失境内效力。",
        "template": "依据《{citation}》，{description}。该域外权力(Power)在中国法域内的效力已被强制性阻断(SUPPRESSED)。",
        "action_tone": "境内效力归零 — 不得协助执行",
    },
    "MAPPING_OVERRIDE": {
        "phrase": "该域外概念在中国法下不存在对应制度，已由替代机制重构。",
        "template": "美国法下的{us_concept}在中国法下无直接对应制度，已由{cn_concept}替代重构。",
        "action_tone": "提请关注制度差异 — 不得直接套用",
    },
    "VOIDABLE": {
        "phrase": "该行为可被撤销，撤销前暂为有效。",
        "template": "{description}。该行为可被撤销(VOIDABLE)，撤销权行使前暂维持现状。",
        "action_tone": "可撤销 — 建议主动行使撤销权",
    },
    "VALID": {
        "phrase": "该主张在三法域审查中均未发现效力瑕疵。",
        "template": "经审查，{description}。未发现法律效力瑕疵。",
        "action_tone": "可正常履行",
    },
}

# ── PRC CBL 规则ID → 法条引用 ──
CBL_RULE_TO_CITATION: Dict[str, str] = {
    "BLK_001_Consideration_Shield": "《民法典》第471条(要约+承诺) / 《反外国制裁法》第12条",
    "BLK_002_Promissory_Estoppel": "《民法典》第500条(缔约过失责任)",
    "BLK_003_StatuteOfFrauds": "《民法典》第469条(书面形式要求)",
    "BLK_004_ParolEvidenceRule": "《民法典》第142条(意思表示解释)",
    "BLK_010_JuryTrial": "《人民陪审员法》(功能不等同)",
    "BLK_011_HabeasCorpus": "《刑事诉讼法》第97条(羁押必要性审查)",
    "BLK_012_PleaBargaining": "《刑事诉讼法》第15条(认罪认罚从宽)",
    "BLK_013_HearsayRule": "《刑事诉讼法》第61条(证人出庭与质证)",
    "BLK_014_MirandaRights": "《刑事诉讼法》第120条(告知义务)",
    "BLK_015_FruitOfPoisonousTree": "《刑事诉讼法》第56条(非法证据排除)",
    "BLK_017_SummaryJudgment": "《民事诉讼法》第157条(简易程序)",
    "BLK_018_ConsentDecree": "《民事诉讼法》第97条(调解书)",
    "BLK_019_AtWillEmployment": "《劳动合同法》第39-48条(解雇保护)",
    "BLK_021_Discovery_Fishing": "《民事诉讼法》第284条(域外证据取证) / 《民诉解释》第224条(证据交换)",
    "BLK_022_CollateralEstoppel": "《民事诉讼法》第247条(既判力)",
    "OVR_001_Plea_Bargaining_Restruct": "《刑事诉讼法》第15条(认罪认罚从宽)",
    "OVR_002_Discovery_To_Exchange": "《民诉解释》第224条(证据交换)",
    "OVR_003_RightOfPublicity_Name": "《民法典》第1018-1019条(肖像权/姓名权)",
    "OVR_005_RightOfPublicity": "《民法典》第1018-1019条(肖像权/姓名权)",
    "OVR_006_Wrongful_Omission_Fill": "《数据安全法》第21条 / 《刑法》第169条之一(背信损害上市公司利益)",
    "PEN_001_Data_CrossBorder_Security": "《数据出境安全评估办法》 / 《网络安全法》第37条",
    "PEN_002_Secondary_Sanction_Block": "《反外国制裁法》第12条",
    "PEN_003_Long_Arm_Interdiction": "《反外国制裁法》第12条 / 《阻断外国法律与措施不当域外适用办法》第9条",
    "PEN_004_OFAC_CounterCollision": "《反外国制裁法》第12条",
    "PEN_005_Crypto_Prohibition": "《关于进一步防范和处置虚拟货币交易炒作风险的通知》(2021)",
    "PEN_006_Anti_Suit_Secondary": "《反外国制裁法》第12条(条件性二级启用)",
    "CN_SPEC_001_Horizontal_Veil_Piercing": "《公司法》(2024修订)第23条第3款",
    "CN_SPEC_002_Factoring_Chapter": "《民法典》第761条(保理合同独立成章)",
    "CN_SPEC_003_Algorithm_Filing": "《互联网信息服务算法推荐管理规定》",
    "CN_SPEC_006_DataExportAssessment": "《数据出境安全评估办法》 / 《网络安全法》第37条",
}

# ── 中国法条全文引用库 ──
PRC_CITATION_FULL: Dict[str, str] = {
    "民法典第471条": "《中华人民共和国民法典》第四百七十一条：当事人订立合同，可以采取要约、承诺方式或者其他方式。",
    "民法典第500条": "《中华人民共和国民法典》第五百条：当事人在订立合同过程中有下列情形之一，造成对方损失的，应当承担赔偿责任：(一)假借订立合同，恶意进行磋商；(二)故意隐瞒与订立合同有关的重要事实或者提供虚假情况；(三)有其他违背诚信原则的行为。",
    "反外国制裁法第12条": "《中华人民共和国反外国制裁法》第十二条：任何组织和个人均不得执行或者协助执行外国国家对我国公民、组织采取的歧视性限制措施。",
    "公司法第23条第3款": "《中华人民共和国公司法》(2024修订)第二十三条第三款：股东利用其控制的两个以上公司实施前款规定行为的，各公司应当对任一公司的债务承担连带责任。",
    "刑事诉讼法第15条": "《中华人民共和国刑事诉讼法》第十五条：犯罪嫌疑人、被告人自愿如实供述自己的罪行，承认指控的犯罪事实，愿意接受处罚的，可以依法从宽处理。",
    "民事诉讼法第284条": "《中华人民共和国民事诉讼法》第二百八十四条：未经中华人民共和国主管机关准许，任何组织或者个人不得在中华人民共和国领域内直接送达文书、调查取证。",
}


def get_classification_text(classification: str) -> Dict[str, str]:
    """返回分类对应的法律用语"""
    return CLASSIFICATION_TEXT.get(classification, CLASSIFICATION_TEXT["COMPLEX_PARALLAX"])


def get_state_opinion(state_code: str) -> Dict[str, str]:
    """返回状态码对应的法律意见模板"""
    return STATE_TO_OPINION.get(state_code, {
        "phrase": "该状态需要进一步法律分析。",
        "template": "{description}",
        "action_tone": "提交审查",
    })


def get_citation(rule_id: str) -> str:
    """返回CBL规则ID对应的法条引用"""
    return CBL_RULE_TO_CITATION.get(rule_id, "参见相关法律法规")


def get_prc_citation_full(short_cite: str) -> str:
    """返回法条简称对应的完整条文"""
    for key, text in PRC_CITATION_FULL.items():
        if short_cite in key or key in short_cite:
            return text
    return ""


def render_risk_matrix(classification: str, force_void: List[str], force_suppress: List[str],
                       mapping_override: List[str], cn_claims_count: int) -> Dict:
    """生成风险矩阵"""
    cls = get_classification_text(classification)

    red_items = []
    yellow_items = []

    for fid in force_void:
        red_items.append({
            "rule_id": fid,
            "citation": get_citation(fid),
            "opinion": get_state_opinion("FORCE_VOID"),
        })

    for fid in force_suppress:
        red_items.append({
            "rule_id": fid,
            "citation": get_citation(fid),
            "opinion": get_state_opinion("FORCE_SUPPRESS"),
        })

    for fid in mapping_override:
        yellow_items.append({
            "rule_id": fid,
            "citation": get_citation(fid),
            "opinion": get_state_opinion("MAPPING_OVERRIDE"),
        })

    if cn_claims_count > 0:
        yellow_items.append({
            "rule_id": "CN_FULL_ENGINE",
            "citation": "《民法典》《公司法》《刑法》《民事诉讼法》《刑事诉讼法》等18部法律",
            "opinion": get_state_opinion("VALID"),
        })

    return {
        "classification": classification,
        "risk_level": cls["risk_level"],
        "risk_tag": cls["risk_tag"],
        "red_zone": red_items,
        "grey_zone": yellow_items,
        "signature_phrase": cls["signature_phrase"],
        "recommended_action": cls["action"],
    }
