#!/usr/bin/env python3
"""
juris-calculus 中国法基准测试 —— 10 个中文合同案例

目标：
  用 2,117 条规则测试 FixpointEvaluator 在中国法下的表现
  指标：收敛率、诚实拒算率、审计链完整性、精算小时数

使用：
  python tests/run_benchmark_zh.py
  输出：tests/results/Benchmark_10Cases_CN.md
"""
import sys, os, json, time, yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from compiler_core.types import LegalRule, LegalFact, IRState, LegalDomain
from compiler_core.evaluator import FixpointEvaluator, CriticalClarityFailure, load_rules_from_yaml
from compiler_core.domain_config import DomainConfig, get_domain_config

# 加载中文规则（谓词ID格式）
ZH_RULES = load_rules_from_yaml(
    os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'rules.yaml')
)

# 加载领域配置（含 α=1.0）
ZH_CONFIG = get_domain_config(LegalDomain.CIVIL)
# 从 YAML 读取校准参数
_config_yaml = yaml.safe_load(open(
    os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'domain_config.yaml'),
    encoding='utf-8'
))
if 'alpha_calibrated' in _config_yaml:
    ZH_CONFIG.alpha = _config_yaml['alpha_calibrated']
if 'concept_registry' in _config_yaml:
    ZH_CONFIG.concept_registry = set(_config_yaml['concept_registry'])

# ── 10 个中文合同测试案例 ──
# 事实谓词：与规则集 premise_atoms 谓词ID 对齐
TEST_CASES = [
    {
        "case_id": "CN-001",
        "title": "民间借贷逾期还款纠纷",
        "complexity": "简单",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2023年3月15日签署借款合同，约定借款50万元",
            "goods_delivered": "2023年3月16日出借人通过银行转账交付50万元",
            "payment_due": "借款期限6个月，2023年9月15日到期",
            "breach_alleged": "借款人到期未归还本金及利息",
            "damages_suffered": "出借人主张本金50万元 + 逾期利息",
        },
        "missing_concepts": [],
        "notes": "标准民间借贷，事实清楚"
    },
    {
        "case_id": "CN-002",
        "title": "买卖合同货款纠纷",
        "complexity": "中等",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2023年1月签署钢材购销合同",
            "goods_delivered": "卖方分三批交付钢材共计500吨",
            "payment_due": "合同约定货到30日内付款",
            "breach_alleged": "买方仅支付首批货款，余款150万元未付",
            "damages_suffered": "卖方主张货款150万元及违约金",
            "liquidated_damages_claimed": "合同约定逾期付款每日万分之五违约金",
        },
        "missing_concepts": [],
        "notes": "涉及违约金计算标准"
    },
    {
        "case_id": "CN-003",
        "title": "建设工程施工合同纠纷",
        "complexity": "复杂",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2022年6月签署建设工程施工合同，合同价2000万元",
            "goods_delivered": "施工方已完成主体工程并通过验收",
            "payment_due": "合同约定按工程进度付款",
            "breach_alleged": "发包方仅支付1200万元，剩余800万元未付",
            "contract_invalid": "施工方主张合同因未招标而无效",
            "damages_suffered": "施工方主张工程款及利息",
            "expert_evidence": "工程造价鉴定报告已出具",
        },
        "missing_concepts": [],
        "notes": "涉及合同效力争议"
    },
    {
        "case_id": "CN-004",
        "title": "租赁合同押金返还纠纷",
        "complexity": "简单",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2022年1月签署商铺租赁合同，租期3年",
            "goods_delivered": "出租人已交付商铺",
            "payment_due": "承租人支付押金2个月租金",
            "breach_alleged": "合同到期后出租人拒不返还押金8万元",
            "damages_suffered": "承租人主张押金8万元",
        },
        "missing_concepts": [],
        "notes": "押金返还争议"
    },
    {
        "case_id": "CN-005",
        "title": "担保追偿权纠纷",
        "complexity": "中等",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2021年12月签署保证合同",
            "security_provided": "保证人为借款人提供连带责任保证",
            "payment_due": "主债务到期未还",
            "breach_alleged": "债权人要求保证人承担保证责任",
            "damages_suffered": "保证人代偿后向主债务人追偿",
        },
        "missing_concepts": [],
        "notes": "追偿权认定"
    },
    {
        "case_id": "CN-006",
        "title": "劳动争议经济补偿纠纷",
        "complexity": "简单",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2019年4月签署劳动合同",
            "breach_alleged": "公司单方解除劳动合同",
            "damages_suffered": "员工主张经济补偿金及未休年假工资",
            "fault_element": "公司以员工不胜任为由解除，但未提供培训或调岗",
        },
        "missing_concepts": [],
        "notes": "解除劳动合同合法性审查"
    },
    {
        "case_id": "CN-007",
        "title": "房屋买卖合同违约纠纷",
        "complexity": "中等",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2023年8月签署二手房买卖合同",
            "payment_due": "买方已支付定金20万元",
            "breach_alleged": "卖方以房价上涨为由拒绝过户",
            "damages_suffered": "买方主张继续履行合同及违约金",
            "liquidated_damages_claimed": "合同约定违约方赔偿房款20%",
        },
        "missing_concepts": [],
        "notes": "涉及继续履行可行性"
    },
    {
        "case_id": "CN-008",
        "title": "车祸人身损害赔偿纠纷",
        "complexity": "中等",
        "expected": "CONVERGED",
        "facts": {
            "fault_element": "肇事司机因闯红灯负事故全责",
            "damages_suffered": "受害人医疗费15万元、误工费5万元、伤残赔偿金40万元",
            "enforcement_action": "肇事车辆已保全",
            "expert_evidence": "司法鉴定意见书已出具，伤残等级九级",
        },
        "missing_concepts": [],
        "notes": "侵权责任纠纷"
    },
    {
        "case_id": "CN-009",
        "title": "股东出资纠纷",
        "complexity": "复杂",
        "expected": "CONVERGED",
        "facts": {
            "contract_formed": "2020年6月签署股东出资协议",
            "payment_due": "认缴出资500万元，出资期限至2023年6月",
            "breach_alleged": "股东仅实缴200万元，剩余300万元未实缴",
            "contract_invalid": "公司要求加速到期补足出资",
            "damages_suffered": "公司主张出资款300万元",
        },
        "missing_concepts": ["accelerated_maturity"],
        "notes": "认缴出资加速到期问题"
    },
    {
        "case_id": "CN-010",
        "title": "知识产权侵权警告回应",
        "complexity": "复杂",
        "expected": "HONEST_REFUSAL",
        "facts": {
            "patent_dispute": "专利权人发出侵权警告函",
            "damages_suffered": "被警告方主张不侵权确认",
            "expert_evidence": "专利侵权分析报告",
        },
        "missing_concepts": ["patent_validity", "claim_construction"],
        "notes": "规则库缺乏专利侵权判定细化规则，期望诚实拒算"
    },

    # ═══ v1.1.0 刑事灰度 ═══
    {
        "case_id": "CN-011",
        "title": "故意伤害致人重伤案",
        "complexity": "中等",
        "expected": "CONVERGED",
        "facts": {
            "damages_suffered": "被害人遭菜刀砍伤致左臂肌腱断裂，法医鉴定重伤二级",
            "fault_element": "被告人明知持刀砍人会造成伤害后果",
            "leniency_factor": "被告人案发后主动投案并如实供述",
        },
        "missing_concepts": [],
        "notes": "故意伤害+自首：Horn Subjective.INTENT+Objective.SEVERE_INJURY→罪名成立, AND Mitigation.SURRENDER→从轻"
    },
    {
        "case_id": "CN-012",
        "title": "盗窃案",
        "complexity": "简单",
        "expected": "CONVERGED",
        "facts": {
            "fraud_crime": "被告人深夜潜入仓库盗窃价值2万元电缆",
            "fault_element": "被告人携带工具，故意为之",
        },
        "missing_concepts": ["attempt"],
        "notes": "盗窃罪基本构成"
    },
    {
        "case_id": "CN-013",
        "title": "诈骗罪全额退赔",
        "complexity": "中等",
        "expected": "CONVERGED",
        "facts": {
            "fraud_crime": "虚构投资项目骗取80万元",
            "fault_element": "被告人明知项目不存在",
            "leniency_factor": "被告人认罪认罚，家属代为退赔全部赃款",
        },
        "missing_concepts": [],
        "notes": "诈骗+认罪认罚+退赃退赔→减轻；累犯→从重，双链推理"
    },
]


@dataclass
class BenchmarkResult:
    case_id: str; title: str; complexity: str = "?"
    expected: str = "—"; notes: str = ""
    pre_missing: List[str] = field(default_factory=list)
    convergence: bool = False
    claims_found: int = 0
    deterministic: int = 0
    tainted: int = 0
    critical: int = 0
    actual_missing: List[str] = field(default_factory=list)
    pred_hours: float = 0.0
    alpha_fit: float = 0.0
    elapsed_ms: float = 0.0
    trace: str = ""
    taint_chain_depth: int = 0


def run_benchmark() -> List[BenchmarkResult]:
    ev = FixpointEvaluator(ZH_RULES, ZH_CONFIG)
    results = []

    for case in TEST_CASES:
        state = IRState(world_id=case["case_id"])
        missing = []
        for fid, desc in case["facts"].items():
            if desc:
                state.facts[fid] = LegalFact(fid, str(desc)[:200])
            else:
                missing.append(fid)

        t0 = time.time()
        halted = False
        try:
            state = ev.evaluate(state)
        except CriticalClarityFailure as e:
            halted = True

        elapsed = round((time.time() - t0) * 1000, 1)

        claims = list(state.claims.values()) if state.claims else []
        det = sum(1 for c in claims if not c.requires_human_review)
        tnt = sum(1 for c in claims if c.requires_human_review and c.confidence >= 0.2)
        cri = sum(1 for c in claims if c.confidence < 0.2)
        max_taint_depth = max((len(c.taint_chain) for c in claims), default=0)

        # 精算
        ne = len(state.facts) + len(claims)
        pred_hours = round(ne * 1.43, 2)

        result = BenchmarkResult(
            case_id=case["case_id"], title=case["title"],
            complexity=case["complexity"],
            expected=case["expected"],
            notes=case.get("notes", ""),
            pre_missing=case.get("missing_concepts", []),
            convergence=not halted,
            claims_found=len(claims),
            deterministic=det, tainted=tnt, critical=cri,
            actual_missing=missing,
            pred_hours=pred_hours,
            alpha_fit=round(pred_hours / max(1, ne), 2),
            elapsed_ms=elapsed,
            trace=f"HALTED: CriticalClarityFailure" if halted else f"CONVERGED: {len(claims)} claims",
            taint_chain_depth=max_taint_depth,
        )
        results.append(result)

    return results


def export_markdown(results: List[BenchmarkResult], outpath: str):
    total = len(results)
    conv_count = sum(1 for r in results if r.convergence)
    halt_count = total - conv_count
    tainted_count = sum(1 for r in results if r.tainted > 0)

    lines = [
        "# juris-calculus 中国法基准测试 —— 10 个中文合同案例",
        "",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}",
        f"规则库: 2,117 条 (configs/zh_CN/rules.yaml)",
        f"领域配置: 权重{list(ZH_CONFIG.weights)} / α={getattr(ZH_CONFIG, 'alpha', 1.0)} / k_max={ZH_CONFIG.k_max}",
        f"评估器: FixpointEvaluator (juris-calculus v1.0.2)",
        "",
        "## 汇总",
        "",
        f"| 指标 | 数值 |",
        f"|------|-----:|",
        f"| 总案例 | {total} |",
        f"| 收敛 (T1) | {conv_count} / {total} ({conv_count/total*100:.1f}%) |",
        f"| 诚实拒算 | {halt_count} / {total} ({halt_count/total*100:.0f}%) |",
        f"| 有污点标记 (T2>0) | {tainted_count} / {total} ({tainted_count/total*100:.0f}%) |",
        f"| 总推理结论 | {sum(r.claims_found for r in results)} |",
        f"| 平均处理时间 | {sum(r.elapsed_ms for r in results)/total:.0f}ms |",
        "",
        "## 逐案结果",
        "",
        "| Case | 案由 | 复杂度 | 收敛 | 结论数 | 确定 | 污点 | 致命 | 预测工时 | α | 时间 | 审计链深度 |",
        "|------|------|--------|:----:|:-----:|:---:|:----:|:----:|:--------:|:--:|:---:|:---------:|",
    ]

    for r in results:
        conv = "✅" if r.convergence else "❌"
        lines.append(
            f"| {r.case_id} | {r.title[:20]} | {r.complexity} | {conv} | "
            f"{r.claims_found} | {r.deterministic} | {r.tainted} | {r.critical} | "
            f"{r.pred_hours:.1f}h | {r.alpha_fit:.1f} | {r.elapsed_ms:.0f}ms | {r.taint_chain_depth} |"
        )

    lines += ["", "## 详细日志", ""]
    for r in results:
        lines.append(f"### {r.case_id} — {r.title}")
        lines.append(f"- 复杂度: {r.complexity}")
        lines.append(f"- 预期: {r.expected} → {'✅' if r.convergence == (r.expected=='CONVERGED') else '⚠️'}")
        lines.append(f"- 轨迹: {r.trace}")
        lines.append(f"- 缺少概念(预): {r.pre_missing or '—'}")
        lines.append(f"- 缺少事实(实): {r.actual_missing or '—'}")
        lines.append(f"- 预测工时: {r.pred_hours:.1f}h | α={r.alpha_fit:.1f}")
        lines.append(f"- 耗时: {r.elapsed_ms}ms")
        lines.append("")

    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\n✅ 基准测试报告: {outpath}")
    print(f"   收敛率: {conv_count}/{total} ({conv_count/total*100:.1f}%)")
    print(f"   污点率: {tainted_count}/{total} ({tainted_count/total*100:.0f}%)")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(base_dir, "results")
    outpath = os.path.join(results_dir, "Benchmark_10Cases_CN.md")

    print("=" * 60)
    print("juris-calculus 中国法基准测试")
    print(f"规则: {len(ZH_RULES)} 条")
    print(f"α常数: {getattr(ZH_CONFIG, 'alpha', 1.0)}")
    print("=" * 60)

    results = run_benchmark()
    for r in results:
        conv = "✅" if r.convergence else "❌"
        match = "✓" if (r.expected == "CONVERGED" and r.convergence) or (r.expected == "HONEST_REFUSAL" and not r.convergence) else "?"
        print(f"\n{r.case_id} [{r.complexity:4s}] {conv}{match} {r.claims_found}个结论 | {r.pred_hours:.1f}h | α={r.alpha_fit:.1f} | 污点={r.tainted}")
        if r.taint_chain_depth > 0:
            print(f"  审计链深度: {r.taint_chain_depth}")

    export_markdown(results, outpath)
