#!/usr/bin/env python3
"""
distill_hk_legislation.py — Distill HK ordinances into Horn rules
═══════════════════════════════════════════════════════════════════
输入: D:/LegalOS/香港法数据/「電子版香港法例」— 香港法例(現行版本)/
输出: configs/hk/rules_expanded.yaml

章节目标:
  Cap 622 — Companies Ordinance 公司条例
  Cap 32  — Companies (Winding Up) Ordinance 公司(清盘)条例  
  Cap 6   — Bankruptcy Ordinance 破产条例
  Cap 8   — Evidence Ordinance 证据条例
  Cap 221 — Criminal Procedure Ordinance 刑事诉讼程序条例
  Cap 336 — District Court Ordinance 区域法院条例
  Cap 571 — Securities and Futures Ordinance 证券及期货条例
  Cap 609 — Arbitration Ordinance 仲裁条例
  Cap 23  — Law Amendment and Reform Ordinance 法律修订及改革条例
═══════════════════════════════════════════════════════════════════
"""
import xml.etree.ElementTree as ET
import json, yaml, os, re
from pathlib import Path
from collections import defaultdict

HK_BASE = "D:/LegalOS/香港法数据/「電子版香港法例」— 香港法例(現行版本)"
OUTPUT = Path("D:/LegalOS/git/juris-calculus/configs/hk/rules_expanded.yaml")
NS = {'h': 'http://www.xml.gov.hk/schemas/hklm/1.0'}

TARGET_CAPS = {
    622: "Companies Ordinance",
    32: "Companies Winding Up",
    6: "Bankruptcy Ordinance", 
    8: "Evidence Ordinance",
    221: "Criminal Procedure Ordinance",
    336: "District Court Ordinance",
    571: "Securities and Futures Ordinance",
    609: "Arbitration Ordinance",
    23: "Law Amendment and Reform",
    614: "Legislation Publication Ordinance",
}

def get_chapter_title(xml_path):
    try:
        tree = ET.parse(xml_path)
        doc = tree.find('.//h:docTitle', NS)
        if doc is not None:
            return ''.join(doc.itertext()).strip()[:120]
    except:
        pass
    return ""

def extract_sections(xml_path):
    """Extract section headings and key operative provisions"""
    sections = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Find all section elements
        for sec in root.iter('{http://www.xml.gov.hk/schemas/hklm/1.0}section'):
            sid = sec.get('id', '')
            num = sec.get('number', '')
            
            # Get section heading
            heading = sec.find('.//h:heading', NS)
            heading_text = ''.join(heading.itertext()).strip() if heading is not None else ''
            
            # Get subsection operative text
            subs = sec.findall('.//h:subsection', NS)
            sub_texts = []
            for sub in subs[:3]:  # First 3 subsections
                sub_texts.append(''.join(sub.itertext())[:200])
            
            if heading_text:
                sections.append({
                    'number': num,
                    'heading': heading_text[:150],
                    'key_text': ' '.join(sub_texts)[:300] if sub_texts else '',
                })
    except Exception as e:
        pass
    return sections

def section_to_rule(cap_num, cap_name, section):
    """Convert a section heading to a Horn rule candidate"""
    heading = section['heading']
    num = section['number']
    
    # Generate rule ID
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', heading)[:40]
    rule_id = f"HK-C{cap_num}-S{num}-{safe_name}"
    
    # Generate premise atoms from heading keywords
    premises = extract_premises(heading, section.get('key_text', ''))
    
    # Generate head claim
    head = f"HK_C{cap_num}_S{num}_{safe_name}_Applies"
    
    return {
        'id': rule_id,
        'premise_atoms': premises,
        'head_claim': head,
        'concepts': extract_concepts(heading),
        'exception_chain': [],
        'head_type': 'HORN',
        'mechanical_exception': True,
        'namespace': f'hk_cap_{cap_num}',
        'output_type': 'Intermediate_Node',
        'source_section': f'Cap {cap_num} s.{num}',
    }

def extract_premises(heading, text):
    """Generate premise atoms from heading and text patterns"""
    premises = []
    heading_lower = (heading + ' ' + text).lower()
    
    # Common HK legal patterns
    if 'application' in heading_lower:
        premises.append('HK_Application_Conditions_Met')
    if 'power' in heading_lower or 'may' in heading_lower:
        premises.append('HK_Statutory_Power_Granted')
    if 'court' in heading_lower:
        premises.append('HK_Court_Jurisdiction_Established')
    if 'duty' in heading_lower or 'shall' in heading_lower:
        premises.append('HK_Statutory_Duty_Imposed')
    if 'offence' in heading_lower or 'penalty' in heading_lower:
        premises.append('HK_Criminal_Liability_Triggered')
    if 'register' in heading_lower or 'registration' in heading_lower:
        premises.append('HK_Registration_Requirement_Met')
    if 'director' in heading_lower:
        premises.append('HK_Director_Fiduciary_Duty')
    if 'shareholder' in heading_lower or 'member' in heading_lower:
        premises.append('HK_Shareholder_Rights_Invoked')
    if 'winding up' in heading_lower or 'liquidation' in heading_lower:
        premises.append('HK_Company_Insolvent')
    if 'evidence' in heading_lower:
        premises.append('HK_Evidence_Tendered')
    if 'contract' in heading_lower:
        premises.append('HK_Contract_Existence')
    if 'arbitration' in heading_lower:
        premises.append('HK_Arbitration_Agreement_Valid')
    if 'bankruptcy' in heading_lower:
        premises.append('HK_Debtor_Insolvent')
    if 'criminal' in heading_lower or 'convicted' in heading_lower:
        premises.append('HK_Criminal_Proceedings_Active')
    
    if not premises:
        premises.append(f'HK_Statutory_Condition_Met')
    
    return premises

def extract_concepts(heading):
    keywords = ['Company', 'Director', 'Shareholder', 'Winding Up', 'Court', 'Evidence',
                'Contract', 'Arbitration', 'Bankruptcy', 'Criminal', 'Offence',
                'Registration', 'Liability', 'Duty', 'Property', 'Trust', 'Security']
    return [kw for kw in keywords if kw.lower() in heading.lower()][:5] or ['Statutory']

def distill_chapter(cap_num, cap_label):
    en_dir = Path(HK_BASE) / f"A{cap_num}_en_c"
    if not en_dir.exists():
        print(f"  Cap {cap_num}: NOT FOUND")
        return []
    
    xml_files = list(en_dir.glob("*.xml"))
    if not xml_files:
        print(f"  Cap {cap_num}: no XML")
        return []
    
    all_rules = []
    for xml_path in xml_files:
        sections = extract_sections(str(xml_path))
        for sec in sections:
            rule = section_to_rule(cap_num, cap_label, sec)
            if rule['premise_atoms'] and rule['head_claim']:
                all_rules.append(rule)
    
    print(f"  Cap {cap_num} {cap_label}: {len(all_rules)} rules from {len(sections)} sections")
    return all_rules


# ═══ MAIN ═══
if __name__ == "__main__":
    print("Distilling HK Legislation...")
    print()
    
    all_rules = []
    
    for cap_num, cap_label in sorted(TARGET_CAPS.items()):
        rules = distill_chapter(cap_num, cap_label)
        all_rules.extend(rules)
    
    # Load existing Cap 26 rules
    with open("D:/LegalOS/git/juris-calculus/configs/hk/rules.yaml", 'r', encoding='utf-8') as f:
        existing = yaml.safe_load(f)
    
    cap26_rules = existing['rules']
    print(f"\nExisting Cap 26 rules: {len(cap26_rules)}")
    print(f"New distilled rules: {len(all_rules)}")
    
    # Merge
    merged = cap26_rules + all_rules
    
    # Output
    output_data = {
        'metadata': {
            'version': 'v1.2.0-expanded',
            'source': 'HK e-Legislation XML (DoJ)',
            'chapters_distilled': list(TARGET_CAPS.keys()),
            'total_rules': len(merged),
        },
        'rules': merged,
    }
    
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        yaml.dump(output_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120)
    
    size = os.path.getsize(OUTPUT)
    print(f"\n[OK] {OUTPUT} ({size:,} bytes, {len(merged)} total rules)")
