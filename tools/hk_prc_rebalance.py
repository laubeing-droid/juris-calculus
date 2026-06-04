#!/usr/bin/env python3
"""
hk_prc_rebalance.py — 补齐香港 + PRC术语主权归位
═══════════════════════════════════════════════════════════════════
1. 从121K词汇表提取A/B级术语 → 生成HK Horn规则
2. 为PRC term_L0_mappings.yaml补充27项CN_SPEC_标识
═══════════════════════════════════════════════════════════════════
"""
import csv, yaml, json, re, os
from pathlib import Path
from collections import defaultdict

OUT_HK = Path("D:/LegalOS/git/juris-calculus/configs/hk/rules_expanded.yaml")
OUT_PRC = Path("D:/LegalOS/git/juris-calculus/configs/prc_us_alignment/term_L0_mappings.yaml")

# ═══ 1. HK: Extract A-grade terms with cap references ═══
GLOSSARY = "D:/LegalOS/香港法数据/hk_terms_clean.csv"

print("[HK] Extracting from 121K glossary...")
raw_terms = []
with open(GLOSSARY, 'r', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        if row.get('grade','C') in ('A','B') and row.get('english_term',''):
            raw_terms.append(row)

# Focus on company/insolvency/bankruptcy domains
target_caps = {'6', '32', '33', '622', '571', '4A'}
domain_terms = defaultdict(list)

for t in raw_terms:
    src = t.get('sources','')
    caps_in_src = set(re.findall(r'Cap\.\s*(\d+[A-Z]*)', src))
    for c in caps_in_src:
        domain_terms[c].append(t['english_term'])

print(f"[HK] Chapters found: {sorted(domain_terms.keys(), key=lambda x: -len(domain_terms[x]))[:10]}")
print(f"  Cap 6 (Bankruptcy): {len(domain_terms.get('6',[]))} terms")
print(f"  Cap 622 (Companies): {len(domain_terms.get('622',[]))} terms")
print(f"  Cap 4A (Rules of Court): {len(domain_terms.get('4A',[]))} terms")

# Generate Horn rules from key terms
hk_rules_new = []

cap_labels = {
    '6': 'Bankruptcy',
    '32': 'Companies_Winding_Up',
    '33': 'Insurance',
    '622': 'Companies_Ordinance',
    '571': 'Securities_Futures',
    '4A': 'Rules_of_High_Court',
}

for cap, term_list in sorted(domain_terms.items()):
    if cap not in cap_labels:
        continue
    label = cap_labels[cap]
    
    # Deduplicate and take first 30 per chapter
    seen = set()
    unique_terms = []
    for t in term_list:
        key = t.lower().strip()
        if key not in seen and len(t) >= 5:
            seen.add(key)
            unique_terms.append(t)
    
    for term in unique_terms[:50]:
        safe_id = re.sub(r'[^a-zA-Z0-9]', '_', term)[:50]
        rule_id = f"HK-C{cap}-{safe_id}"
        
        # Derive premise from term
        premise_key = re.sub(r'[^a-zA-Z]', '_', term.split()[0])[:30] if term.split() else 'Condition'
        
        rule = {
            'id': rule_id,
            'premise_atoms': [f'HK_{premise_key}_Established'],
            'head_claim': f'HK_Cap{cap}_{safe_id}_Applies',
            'concepts': [label] + [w for w in term.split()[:3] if len(w) > 3][:2],
            'exception_chain': [],
            'head_type': 'HORN',
            'mechanical_exception': True,
            'namespace': f'hk_cap_{cap}',
            'output_type': 'Intermediate_Node',
            'source': f'Cap {cap} {label}',
            'term': term,
        }
        hk_rules_new.append(rule)

print(f"\n[HK] Generated {len(hk_rules_new)} new Horn rules")

# Load existing rules
with open("D:/LegalOS/git/juris-calculus/configs/hk/rules.yaml", 'r', encoding='utf-8') as f:
    existing = yaml.safe_load(f)

merged = existing['rules'] + hk_rules_new
output_hk = {
    'metadata': {
        'version': 'v1.2.0-expanded',
        'source': 'HK e-Legislation + DoJ 121K Glossary',
        'chapters_covered': ['26'] + sorted(cap_labels.keys()),
        'total_rules': len(merged),
        'cap26_rules': len(existing['rules']),
        'new_rules': len(hk_rules_new),
    },
    'rules': merged,
}

with open(OUT_HK, 'w', encoding='utf-8') as f:
    yaml.dump(output_hk, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120)

print(f"[HK] rules_expanded.yaml: {len(merged)} total ({os.path.getsize(OUT_HK):,} bytes)")

# ═══ 2. PRC: 27项 CN_SPEC_ 主权归位 ═══
print("\n[PRC] Fixing term_L0_mappings.yaml with CN sovereignty markers...")

prc_terms = [
    {"id":"PRC_SPEC_001_Horizontal_Veil_Piercing","cn":"横向人格否认","us":"Affiliate_Asset_Confusion_Liability","l0":"Agent","expr":"Agent(Asso_Entities_Merged_Liability)","law":"公司法2024第23条3款"},
    {"id":"PRC_SPEC_002_Leniency_Admission","cn":"认罪认罚从宽","us":"Plea_Bargaining_Non_Equivalent","l0":"Status","expr":"Status(CN_Statutory_Mitigation)","law":"刑诉法第15条"},
    {"id":"PRC_SPEC_003_Data_Export_Assessment","cn":"数据出境安全评估","us":"Cross_Border_Data_Interdiction","l0":"Act","expr":"Act(Data_Transfer_Suspended)","law":"数据安全法第36条"},
    {"id":"PRC_SPEC_004_Algorithm_Filing","cn":"算法备案","us":"Algorithm_Registration_Mandatory","l0":"Act","expr":"Act(Algorithm_Must_File)","law":"互联网信息服务算法推荐管理规定"},
    {"id":"PRC_SPEC_005_Factoring_Chapter","cn":"保理合同独立成章","us":"Factoring_As_Named_Contract","l0":"Status","expr":"Status(CN_Factoring_Article_761)","law":"民法典第761条"},
    {"id":"PRC_SPEC_006_Divorce_CoolingOff","cn":"离婚冷静期","us":"Divorce_Mandatory_Waiting_Period","l0":"Status","expr":"Status(30Day_Cooling_Off)","law":"民法典第1077条"},
    {"id":"PRC_SPEC_007_Shadow_Director","cn":"影子董事/事实董事","us":"DeFacto_Director_Liability","l0":"Agent","expr":"Agent(Shadow_Director_Identified)","law":"公司法2024"},
    {"id":"PRC_SPEC_008_Voice_Right","cn":"声音权","us":"Voice_Right_Personality_Protection","l0":"Asset","expr":"Asset(Voice_Reference_Portrait_Right)","law":"民法典第1023条"},
    {"id":"PRC_SPEC_009_Admin_Public_Interest","cn":"行政公益诉讼","us":"Administrative_Public_Interest_Litigation","l0":"Power","expr":"Power(Procuratorate_Sue_Admin)","law":"行政诉讼法第25条"},
    {"id":"PRC_SPEC_010_Normative_Review","cn":"规范性文件一并审查","us":"Incidental_Normative_Review","l0":"Power","expr":"Power(Court_Review_Normative)","law":"行政诉讼法第53条"},
    {"id":"PRC_SPEC_011_Important_Core_Data","cn":"重要数据/核心数据体系","us":"Important_Core_Data_Classification","l0":"Asset","expr":"Asset(Data_Grade_Important_Core)","law":"数据安全法第21条"},
    {"id":"PRC_SPEC_012_Vertical_Piercing","cn":"纵向人格否认(一人公司)","us":"Vertical_Veil_Piercing_OnePerson","l0":"Defect","expr":"Defect(Shareholder_Asset_Confusion)","law":"公司法第23条1款"},
    {"id":"PRC_SPEC_013_Community_Corrections","cn":"社区矫正","us":"Community_Correction_System","l0":"Status","expr":"Status(Community_Correction_Active)","law":"社区矫正法"},
    {"id":"PRC_SPEC_014_Environmental_PIL","cn":"环境公益诉讼","us":"Environmental_Public_Interest_Standing","l0":"Power","expr":"Power(NGO_Environmental_Lawsuit)","law":"环境保护法第58条"},
    {"id":"PRC_SPEC_015_Guiding_Case","cn":"指导性案例","us":"Guiding_Case_NOT_Binding_Precedent","l0":"Asset","expr":"Asset(SPC_Guiding_Case_Must_Refer)","law":"最高法关于案例指导工作的规定"},
    {"id":"PRC_SPEC_016_Retrial_Procedure","cn":"审判监督程序(再审)","us":"Retrial_Procedure_Ex_Officio","l0":"Act","expr":"Act(Retrial_Initiated_By_Court_OR_Procuratorate)","law":"民诉法第198-213条"},
    {"id":"PRC_SPEC_017_Preservation_Measures","cn":"行为保全/财产保全","us":"Preservation_Injunction_Attachment","l0":"Power","expr":"Power(Court_Preserve_Property_Pre_Judgment)","law":"民诉法第100-105条"},
    {"id":"PRC_SPEC_018_Enforcement_System","cn":"执行程序(执行难治理)","us":"Judgment_Enforcement_Special_Procedures","l0":"Act","expr":"Act(Enforcement_Court_Specialized)","law":"民诉法执行编"},
    {"id":"PRC_SPEC_019_Anti_Foreign_Sanction","cn":"反外国制裁阻断","us":"Anti_Foreign_Sanction_Countermeasure","l0":"Power","expr":"Power(Block_Foreign_Sanction_Effect)","law":"反外国制裁法第12条"},
    {"id":"PRC_SPEC_020_State_Compensation","cn":"国家赔偿","us":"State_Compensation_Liability","l0":"Asset","expr":"Asset(State_Pays_Compensation)","law":"国家赔偿法"},
    {"id":"PRC_SPEC_021_Securities_Class_Action","cn":"证券特别代表人诉讼","us":"Securities_Special_Representative_Action","l0":"Act","expr":"Act(Investor_Center_Files_Class)","law":"证券法第95条3款"},
    {"id":"PRC_SPEC_022_Crypto_Prohibition","cn":"加密货币全面禁止","us":"Cryptocurrency_Total_Ban","l0":"Asset","expr":"Asset(Crypto_Transaction_Invalid)","law":"2021年虚拟货币通知"},
    {"id":"PRC_SPEC_023_Cross_Border_Data_Law","cn":"数据出境三轨制","us":"Cross_Border_Data_Three_Track","l0":"Act","expr":"Act(Data_Export_Assessment_Or_Contract_Or_Cert)","law":"数据出境安全评估办法"},
    {"id":"PRC_SPEC_024_Domestic_Violence_Order","cn":"人身安全保护令","us":"Domestic_Violence_Protective_Order","l0":"Power","expr":"Power(Court_Issue_Habeas_DV_Order)","law":"反家庭暴力法第23条"},
    {"id":"PRC_SPEC_025_Third_Party_Revocation","cn":"第三人撤销之诉","us":"Third_Party_Revocation_Lawsuit","l0":"Act","expr":"Act(Non_Party_Vacates_Judgment)","law":"民诉法第56条"},
    {"id":"PRC_SPEC_026_Tax_Anti_Avoidance","cn":"一般反避税规则","us":"General_Anti_Avoidance_Rule","l0":"Power","expr":"Power(Tax_Authority_Recharacterize)","law":"企业所得税法第47条"},
    {"id":"PRC_SPEC_027_FiveYear_Capital_Contribution","cn":"五年认缴期限","us":"FiveYear_Capital_Contribution_Deadline","l0":"Status","expr":"Status(Capital_Must_Paid_Within_5Years)","law":"公司法2024第47条"},
]

print(f"[PRC] {len(prc_terms)} CN_SPEC terms compiled")

# Write updated term_L0_mappings.yaml
with open(OUT_PRC, 'r', encoding='utf-8') as f:
    current = yaml.safe_load(f)

existing_ids = {t.get('id','') for t in current.get('term_alignments', [])}
added = 0
for pt in prc_terms:
    if pt['id'] not in existing_ids:
        current['term_alignments'].append({
            'id': pt['id'],
            'term_cn': pt['cn'],
            'term_us_approximate': pt['us'],
            'l0_chain': {
                'primitive': pt['l0'],
                'expression': pt['expr'],
                'status': 'FORCE_OVERRIDE' if pt['l0'] in ('Power','Act') else 'CN_SOVEREIGN',
            },
            'legal_basis': pt['law'],
            'description': f'中国法特有制度——严禁用普通法概念等同映射。法条依据: {pt["law"]}。',
        })
        existing_ids.add(pt['id'])
        added += 1

current['metadata']['total_terms'] = len(current['term_alignments'])
current['metadata']['cn_spec_terms'] = added

with open(OUT_PRC, 'w', encoding='utf-8') as f:
    yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120)

print(f"[PRC] Updated: +{added} CN_SPEC terms → {len(current['term_alignments'])} total ({os.path.getsize(OUT_PRC):,} bytes)")

print(f"\n=== DONE ===")
print(f"  HK: {len(merged)} rules ({len(existing['rules'])} Cap26 + {len(hk_rules_new)} new)")
print(f"  PRC: {len(current['term_alignments'])} term mappings (+{added} CN_SPEC)")
