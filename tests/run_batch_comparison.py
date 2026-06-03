#!/usr/bin/env python3
"""
P1-⑤: 批量对比 T1/T2 自动报告

用法：
    python tests/run_batch_comparison.py
    python tests/run_batch_comparison.py --cases "./data/cases"
"""
import sys, os, json, time, re
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from compiler_core.types import LegalFact, IRState, LegalDomain
from compiler_core.evaluator import FixpointEvaluator, CriticalClarityFailure, load_rules_from_yaml
from compiler_core.domain_config import get_domain_config

RULES_YAML = os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'rules.yaml')
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(REPORT_DIR, exist_ok=True)

# 加载引擎
ZH_RULES = load_rules_from_yaml(RULES_YAML)
import yaml
_cfg_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'domain_config.yaml')
ZH_CONFIG = get_domain_config(LegalDomain.CIVIL)
if os.path.exists(_cfg_path):
    _cfg = yaml.safe_load(open(_cfg_path, encoding='utf-8'))
    if 'alpha_calibrated' in _cfg:
        ZH_CONFIG.alpha = _cfg['alpha_calibrated']
ENGINE = FixpointEvaluator(ZH_RULES, ZH_CONFIG)


@dataclass
class CaseResult:
    case_id: str; category: str = ""
    has_text: bool = False
    text_chars: int = 0
    facts_found: int = 0
    old_t1: bool = False; old_t2: int = 0; old_claims: int = 0
    new_t1: bool = False; new_t2: int = 0; new_claims: int = 0
    elapsed_ms: float = 0.0


def extract_case_text(case_dir: Path) -> str:
    """只读提取案卷文本（含 OCR 兜底）"""
    combined = ""
    seen = set()
    ocr_engine = None

    def _ocr(img_path):
        nonlocal ocr_engine
        if ocr_engine is None:
            try:
                from paddleocr import PaddleOCR
                ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            except ImportError:
                return ""
        try:
            result = ocr_engine.ocr(img_path, cls=True)
            texts = []
            for line in result or []:
                for word in line or []:
                    txt = word[1][0] if len(word) > 1 else ""
                    if txt and txt.strip():
                        texts.append(txt.strip())
            return '\n'.join(texts)
        except:
            return ""

    for ext in ['.docx', '.txt', '.md', '.json', '.doc', '.pdf', '.jpg', '.jpeg', '.png', '.bmp']:
        for fp in sorted(case_dir.rglob(f'*{ext}')):
            if fp.is_dir() or fp.name.startswith('~$'):
                continue
            try:
                text = ""
                if ext == '.docx':
                    from docx import Document
                    doc = Document(str(fp))
                    text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
                elif ext in ('.txt', '.md', '.json'):
                    text = fp.read_text(encoding='utf-8', errors='ignore')
                elif ext == '.pdf':
                    import pdfplumber
                    with pdfplumber.open(str(fp)) as pdf:
                        texts = [p.extract_text() or "" for p in pdf.pages[:5]]
                        text = '\n'.join(texts)
                    if len(text.strip()) < 50:
                        ocr = _ocr(str(fp))
                        if ocr: text = ocr
                elif ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                    text = _ocr(str(fp))
                if text and len(text.strip()) > 100:
                    sig = text[:200]
                    if sig not in seen:
                        seen.add(sig)
                        combined += text + '\n'
            except Exception:
                pass
    return combined


# ── 旧方法（正则）─ 谓词提取 ──
OLD_PATTERNS = [
    (r'(?:民间借贷|借款|借条|欠条)', 'loan_contract'),
    (r'(?:买卖|购销|采购)\s*(?:合同)', 'sales_contract'),
    (r'(?:租赁|租用)', 'lease_contract'),
    (r'(?:建设工程|施工|工程款)', 'construction_contract'),
    (r'(?:劳动|劳务|雇佣)', 'labor_contract'),
    (r'(?:担保|保证|抵押|质押)', 'security_contract'),
    (r'(?:合同|协议)\s*(?:成立|签署|生效)', 'contract_formed'),
    (r'(?:违约|违反|不履行|拖欠)', 'breach_alleged'),
    (r'(?:未|没有|拒不|逾期)\s*(?:支付|付款|还款)', 'payment_default'),
    (r'(?:已|已经)?\s*(?:交付|交货|发货)', 'goods_delivered'),
    (r'(?:到期|届满|期限届满)', 'payment_due'),
    (r'(?:利息|违约金|滞纳金|罚息)', 'liquidated_damages'),
    (r'(?:超过|已过|经过)\s*(?:诉讼时效)', 'statute_barred'),
    (r'(?:不可抗力|疫情|自然灾害)', 'force_majeure'),
    (r'(?:交通事故|车祸|肇事)', 'traffic_accident'),
    (r'(?:故意|过失|明知|应知|疏忽)', 'fault_element'),
    (r'(?:损失|损害|伤害|死亡|伤残)', 'damages_suffered'),
    (r'(?:查封|冻结|扣押|保全)', 'enforcement_action'),
    (r'(?:二审|上诉|再审|抗诉)', 'appeal_proceeding'),
    (r'(?:鉴定|评估|审计|检测)', 'expert_evidence'),
    (r'(?:自首|立功|坦白|认罪)', 'leniency_factor'),
    (r'(?:行政|处罚|许可|强制|复议)', 'administrative_action'),
    (r'(?:国家赔偿)', 'state_compensation'),
    (r'(?:破产|重整|和解|清算)', 'bankruptcy'),
    (r'(?:不动产|房产|房屋|土地|产权)', 'real_estate'),
]

# ── 语义匹配器（按需加载，可选）──
MATCHER = None

def _lazy_load_matcher():
    """惰性加载语义匹配器（首次调用时加载模型）"""
    global MATCHER
    if MATCHER is not None:
        return MATCHER
    try:
        from extractors.zh_CN.semantic_fact_matcher import SemanticFactMatcher
        print("  [加载语义匹配器...]")
        MATCHER = SemanticFactMatcher(RULES_YAML)
        return MATCHER
    except Exception as e:
        print(f"  [语义匹配器加载失败: {e}]")
        return None


def process_case(case_dir: Path, category: str) -> CaseResult:
    case_id = case_dir.name
    result = CaseResult(case_id=case_id, category=category)

    t0 = time.time()
    text = extract_case_text(case_dir)
    result.text_chars = len(text)

    if not text.strip():
        result.has_text = False
        return result

    result.has_text = True

    # 旧方法：正则提取
    old_facts = {}
    for pat, pid in OLD_PATTERNS:
        if re.search(pat, text):
            old_facts[pid] = text[max(0,re.search(pat,text).start()-5):re.search(pat,text).end()+20][:80]
    result.facts_found = len(old_facts)

    if old_facts:
        state = IRState(world_id=case_id)
        for fid, desc in old_facts.items():
            state.facts[fid] = LegalFact(fid, str(desc)[:200])
        try:
            r = ENGINE.evaluate(state)
        except CriticalClarityFailure:
            r = state
        claims = list(r.claims.values()) if r.claims else []
        result.old_t1 = len(claims) > 0
        result.old_t2 = sum(1 for c in claims if c.requires_human_review)
        result.old_claims = len(claims)

    # 新方法：语义匹配（如需启用，删除下面这行的 return None）
    matcher = None  # 请手动设置为 _lazy_load_matcher() 启用语义匹配（需加载 bge-large-zh 模型）
    if matcher is not None and text:
        try:
            new_facts = matcher.extract_facts(text[:8000])
            if new_facts:
                state2 = IRState(world_id=case_id)
                for fid, desc in new_facts.items():
                    state2.facts[fid] = LegalFact(fid, str(desc)[:200])
                try:
                    r2 = ENGINE.evaluate(state2)
                except CriticalClarityFailure:
                    r2 = state2
                claims2 = list(r2.claims.values()) if r2.claims else []
                result.new_t1 = len(claims2) > 0
                result.new_t2 = sum(1 for c in claims2 if c.requires_human_review)
                result.new_claims = len(claims2)
        except Exception:
            pass

    result.elapsed_ms = round((time.time() - t0) * 1000, 1)
    return result


def scan_cases(base_dir: str) -> list:
    """扫描案卷目录"""
    all_cases = []
    for category_dir in sorted(Path(base_dir).iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        # 跳过非案卷目录
        if category in ('日常运营', '法律法规'):
            continue
        for case_folder in sorted(category_dir.iterdir()):
            if case_folder.is_dir():
                all_cases.append((case_folder, category))
    return all_cases


def main(cases_dir: str):
    cases = scan_cases(cases_dir)
    print(f"扫描到 {len(cases)} 个案卷目录\n")

    results = []
    for case_dir, category in cases:
        result = process_case(case_dir, category)
        results.append(result)

        icon = "✅" if result.has_text else "❌"
        old_t1 = f"T1={'✅' if result.old_t1 else '❌'}({result.old_claims}c)"
        new_t1 = f"T1={'✅' if result.new_t1 else '❌'}({result.new_claims}c)" if result.has_text else "-"
        print(f"  {icon} [{category}] {result.case_id[:30]:30s} | {result.text_chars:>5}字 | 旧:{old_t1:15s} | 新:{new_t1:15s}")

    # 汇总报告
    total = len(results)
    with_text = sum(1 for r in results if r.has_text)
    old_t1_count = sum(1 for r in results if r.old_t1)
    new_t1_count = sum(1 for r in results if r.new_t1)
    avg_old = sum(r.old_claims for r in results) / max(with_text, 1)
    avg_new = sum(r.new_claims for r in results) / max(with_text, 1)

    report_path = os.path.join(REPORT_DIR, "BatchComparison_T1T2.md")
    lines = [
        "# 批量 T1/T2 对比报告",
        "",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}",
        f"案卷目录: {cases_dir}",
        f"规则: {len(ZH_RULES)} 条 | α={getattr(ZH_CONFIG,'alpha',1.0)}",
        "",
        "## 汇总",
        "",
        f"| 指标 | 旧方法（正则） | 新方法（语义） |",
        f"|------|:-------------:|:-------------:|",
        f"| 总案卷 | {total} | {total} |",
        f"| 有文本 | {with_text} | {with_text} |",
        f"| T1 触发 | {old_t1_count}/{with_text} ({old_t1_count/max(with_text,1)*100:.0f}%) | {new_t1_count}/{with_text} ({new_t1_count/max(with_text,1)*100:.0f}%) |",
        f"| 平均结论/案 | {avg_old:.1f} | {avg_new:.1f} |",
        "",
        "## 逐案明细",
        "",
        "| 案卷 | 分类 | 字数 | 旧T1 | 旧结论 | 旧T2 | 新T1 | 新结论 | 新T2 | 耗时 |",
        "|------|:---:|:---:|:----:|:-----:|:----:|:----:|:-----:|:----:|:----:|",
    ]
    for r in results:
        lines.append(
            f"| {r.case_id[:25]} | {r.category} | {r.text_chars} | "
            f"{'✅' if r.old_t1 else '❌'} | {r.old_claims} | {r.old_t2} | "
            f"{'✅' if r.new_t1 else '❌'} | {r.new_claims} | {r.new_t2} | "
            f"{r.elapsed_ms:.0f}ms |"
        )

    Path(report_path).write_text('\n'.join(lines), encoding='utf-8')
    print(f"\n{'='*60}")
    print(f"报告: {report_path}")
    print(f"有文本: {with_text}/{total}")
    print(f"旧T1: {old_t1_count}/{with_text} ({old_t1_count/max(with_text,1)*100:.0f}%)")
    print(f"新T1: {new_t1_count}/{with_text} ({new_t1_count/max(with_text,1)*100:.0f}%)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="./data/cases")
    args = parser.parse_args()
    main(args.cases)
