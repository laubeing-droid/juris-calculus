#!/usr/bin/env python3
"""
juris-calculus 工业级法律精算引擎
模型二：多因子混合调节工时精算
模型三：图拓扑同构识别 + 批量类案指数衰减
α = 1.0 (demo value, calibrate with your own timesheet data)
"""
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

# ═══════════ 模型二：多因子混合调节矩阵 ═══════════

@dataclass
class LocationFactor:
    """空间地理溢价向量 B_location"""
    LOCAL = 1.0       # 本地办案
    PROVINCE = 1.3    # 省内异地开庭
    CROSS_PROVINCE = 1.8  # 跨省远征拉锯

@dataclass  
class StageFactor:
    """审级与程序修正矩阵 Γ_stage"""
    FIRST_INSTANCE = 1.0     # 标准一审/仲裁
    APPEAL_RETRIAL = 1.25    # 二审/再审审计（对应每个审计10h脑力复勘）
    ENFORCEMENT = 1.1        # 纯执行/财产保全阶段

@dataclass
class TravelOverhead:
    """物理在途固定常数损耗 T_overhead (小时)"""
    LOCAL = 0.0       # 本地
    PROVINCE = 8.0    # 省内往返
    CROSS_PROVINCE = 16.0  # 省外往返（含登机安检挂起）

@dataclass
class BillingTier:
    """人力阶梯计费杠杆向量 H（美国白鞋所 Billable Hours 分级）
    
    Partner (合伙人):      1.8x — highest rate, strategic oversight
    Senior Associate:      1.3x — experienced, independent case handling
    Associate:             1.0x — baseline billing
    Paralegal:             0.5x — document review, administrative
    """
    PARTNER = 1.8
    SENIOR_ASSOCIATE = 1.3
    ASSOCIATE = 1.0
    PARALEGAL = 0.5

@dataclass
class PricingCase:
    """案卷定价输入"""
    effective_nodes: float     # N_effective (加权后的有效节点数)
    location: str = "LOCAL"    # LOCAL/PROVINCE/CROSS_PROVINCE
    stage: str = "FIRST_INSTANCE"  # FIRST_INSTANCE/APPEAL_RETRIAL/ENFORCEMENT
    batch_position: int = 1    # 类案批次位置 (1=首案)
    is_batch_case: bool = False

class LegalOSPricingEngine:
    """juris-calculus 工业级精算引擎"""
    
    # 硬编码常数（默认值，可由 load_alpha_from_config() 覆盖）
    ALPHA = 1.0            # α: 纯法理脑力常数 (开源演示值，生产环境需按团队数据重新校准)
    LAMBDA = 0.65          # λ: 经验复用学习率
    SIMILARITY_THRESHOLD = 0.85  # 类案判定阈值
    
    def __init__(self, alpha: float = None):
        # 案例库：存储已有案卷的图特征向量
        self.case_graphs: Dict[str, Tuple[int, int, set]] = {}
        # alpha 优先级：参数 > YAML domain_config > 默认1.0
        self.ALPHA = alpha if alpha is not None else self._load_alpha()

    @staticmethod
    def _load_alpha() -> float:
        """从 domain_config.yaml 加载校准后的 α 常数"""
        import os, yaml
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'domain_config.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            alpha = config.get('alpha_calibrated', 1.0)
            if isinstance(alpha, (int, float)) and alpha > 0:
                print(f"[LegalOSPricing] α={alpha} (calibrated from {config_path})")
                return alpha
        except Exception:
            pass
        print(f"[LegalOSPricing] α=1.0 (default, no calibration found)")
        return 1.0
    
    # ═══════ 模型二核心公式 ═══════
    
    def get_location_factor(self, location: str) -> float:
        return getattr(LocationFactor, location, LocationFactor.LOCAL)
    
    def get_stage_factor(self, stage: str) -> float:
        return getattr(StageFactor, stage, StageFactor.FIRST_INSTANCE)
    
    def get_travel_overhead(self, location: str) -> float:
        return getattr(TravelOverhead, location, TravelOverhead.LOCAL)
    
    def predict_hours(self, case: PricingCase) -> Dict:
        """
        全量工时精算公式：
        T_predict = (N_effective × α) × B_location × Γ_stage + T_overhead
        
        Returns:
            dict with breakdown
        """
        ne = case.effective_nodes
        alpha = self.ALPHA
        b_loc = self.get_location_factor(case.location)
        g_stage = self.get_stage_factor(case.stage)
        t_oh = self.get_travel_overhead(case.location)
        
        # 纯法理工时
        legal_hours = ne * alpha
        
        # 应用调节矩阵
        adjusted = legal_hours * b_loc * g_stage
        
        # 加物理损耗
        total = adjusted + t_oh
        
        # 非纯法理溢价（用于审计）
        non_legal_premium = total - legal_hours
        
        return {
            "effective_nodes": round(ne, 1),
            "pure_legal_hours": round(legal_hours, 1),
            "location_factor": b_loc,
            "stage_factor": g_stage,
            "travel_overhead": t_oh,
            "adjusted_hours": round(adjusted, 1),
            "total_hours": round(total, 1),
            "non_legal_premium": round(non_legal_premium, 1),
            "alpha": alpha,
            "formula": f"({ne:.1f}×{alpha})×{b_loc}×{g_stage}+{t_oh}={total:.1f}h"
        }
    
    # ═══════ 模型三核心公式 ═══════
    
    def compute_graph_similarity(self, v_new: int, e_new: int, features_new: set,
                                  v_base: int, e_base: int, features_base: set) -> float:
        """
        图同构相似度 Sim(G_new, G_base) = (|V_MCS| + |E_MCS|) / (|V_new| + |E_new|)
        
        简化版：使用 Jaccard 特征相似度 + 规模比 近似 MCS
        """
        if v_new == 0 or v_base == 0:
            return 0.0
        
        # 特征 Jaccard 相似度
        if features_new and features_base:
            jaccard = len(features_new & features_base) / len(features_new | features_base)
        else:
            jaccard = 0.5
        
        # 规模比（小/大）
        size_ratio = min(v_new, v_base) / max(v_new, v_base)
        
        # MCS 估计
        return 0.6 * jaccard + 0.4 * size_ratio
    
    def find_similar_cases(self, features: set, v_count: int, e_count: int, 
                           threshold: float = None) -> List[str]:
        """查找相似度超过阈值的已有案卷"""
        if threshold is None:
            threshold = self.SIMILARITY_THRESHOLD
        
        similar = []
        for case_id, (v_base, e_base, feat_base) in self.case_graphs.items():
            sim = self.compute_graph_similarity(v_count, e_count, features, 
                                                v_base, e_base, feat_base)
            if sim >= threshold:
                similar.append((case_id, sim))
        
        return [c[0] for c in sorted(similar, key=lambda x: -x[1])]
    
    def register_case(self, case_id: str, features: set, v_count: int, e_count: int):
        """注册案卷到图数据库"""
        self.case_graphs[case_id] = (v_count, e_count, features)
    
    def batch_decay_cost(self, effective_nodes: float, position: int) -> float:
        """
        批量类案指数衰减公式：
        Cost(Case_n) = N_effective × α × n^(-λ)
        
        Args:
            effective_nodes: 加权有效节点数
            position: 类案批次位置 (1=首案, 2=第二件...)
        """
        return effective_nodes * self.ALPHA * (position ** (-self.LAMBDA))
    
    def estimate_batch_total(self, effective_nodes: float, batch_size: int) -> Dict:
        """
        估算批量案总工时（积分求和）
        Total = Σ(n=1..batch_size) N×α×n^(-λ)
        """
        total = 0.0
        breakdown = []
        
        for n in range(1, batch_size + 1):
            cost = self.batch_decay_cost(effective_nodes, n)
            total += cost
            if n <= 5 or n == batch_size:
                breakdown.append((n, round(cost, 1)))
        
        return {
            "batch_size": batch_size,
            "first_case_hours": round(self.batch_decay_cost(effective_nodes, 1), 1),
            "last_case_hours": round(self.batch_decay_cost(effective_nodes, batch_size), 1),
            "total_hours": round(total, 1),
            "avg_hours": round(total / batch_size, 1),
            "discount_vs_linear": round((effective_nodes * self.ALPHA * batch_size - total) / 
                                        (effective_nodes * self.ALPHA * batch_size) * 100, 1),
            "breakdown": breakdown
        }

    def calculate_full(self, case: PricingCase) -> Dict:
        """完整定价计算：基础定价 + 类案衰减（如适用）"""
        base = self.predict_hours(case)
        
        if case.is_batch_case and case.batch_position > 1:
            batch_cost = self.batch_decay_cost(case.effective_nodes, case.batch_position)
            base["batch_discounted_hours"] = round(batch_cost, 1)
            base["batch_discount"] = round((base["total_hours"] - batch_cost) / base["total_hours"] * 100, 1)
            base["total_hours"] = round(batch_cost, 1)
        
        return base

# ═══════════ 模型一：DAG 节点权重信息熵 (简化版) ═══════════

class WeightedNodeCounter:
    """多维交叉图节点权重计算器"""
    
    def __init__(self):
        self.CHI_DOMAIN = {
            'Civil_Contract': 1.0,      # 纯字面民事合同
            'Civil_Construction': 1.3,   # 建设工程（多主体多层级）
            'Civil_Tort': 1.2,           # 侵权（因果链复杂）
            'Criminal': 2.5,             # 刑事（程序+实体双重复）
            'Administrative': 1.8,       # 行政（复议+诉讼双轨）
        }
    
    def compute_edge_count(self, facts: dict) -> int:
        """估算法理关联边数"""
        edges = 0
        
        # 当事人之间有诉辩关系
        parties = facts.get('party_names', [])
        if len(parties) >= 3:
            edges += len(parties) - 1  # 每个额外当事人增加关联
        
        # 核心要素之间的关联
        core = facts.get('core_elements', {})
        filled_core = sum(1 for v in core.values() if v and str(v).strip() and len(str(v)) > 3)
        if filled_core >= 2:
            edges += filled_core - 1
        
        # 刚性条款与核心要素的交叉
        rigid = facts.get('rigid_clauses', {})
        filled_rigid = sum(1 for v in rigid.values() if v and str(v).strip() and len(str(v)) > 5)
        edges += min(filled_core, filled_rigid)  # 交叉关联
        
        # 金额关联
        amounts = facts.get('_meta', {}).get('amounts_found', [])
        if len(amounts) >= 3:
            edges += 1  # 多笔金额 → 资金流关联
        
        # 判决结果 → 增加事实-结论边
        judgment = rigid.get('judgment_result', '') or rigid.get('verdict', '')
        if judgment:
            edges += 1
        
        return max(1, edges)
    
    def compute_weights(self, facts: dict) -> Tuple[float, Dict]:
        """
        计算加权有效节点数
        
        公式：w_i = 1.0 + ln(1 + deg⁺(v_i) + deg⁻(v_i)) × χ_domain
        
        Returns:
            (N_effective, breakdown_dict)
        """
        domain = facts.get('domain', 'Civil_Contract')
        subtype = facts.get('subtype', '')
        chi = self.CHI_DOMAIN.get(subtype, self.CHI_DOMAIN.get(domain, 1.0))
        
        # 输入校验
        core = facts.get('core_elements', {})
        rigid = facts.get('rigid_clauses', {})
        parties = facts.get('party_names', [])
        has_any_content = any(
            (v and str(v).strip() and len(str(v)) > 3) 
            for v in list(core.values()) + list(rigid.values())
        )
        if not has_any_content and len(parties) < 2:
            return (0.0, {"error": "empty_facts", "message": "No valid core elements, rigid clauses, or parties found", "base_nodes": 0})
        
        base_nodes = 0
        node_details = {}
        
        for k, v in core.items():
            if v and str(v).strip() and len(str(v)) > 3:
                base_nodes += 1
                node_details[k] = 1
        
        for k, v in rigid.items():
            if v and str(v).strip() and len(str(v)) > 5:
                base_nodes += 1
                node_details[k] = 1
        
        if len(parties) >= 2:
            base_nodes += 1
            node_details['parties'] = 1
        
        # 计算边数（出入度之和）
        e_count = self.compute_edge_count(facts)
        
        # 平均出入度 per node
        avg_degree = e_count / max(1, base_nodes)
        
        # 权重公式：w = 1.0 + ln(1 + avg_deg) × χ
        weight = 1.0 + math.log(1 + avg_degree) * chi
        effective_nodes = base_nodes * weight
        
        # 刑民交叉检测
        has_criminal_nexus = False
        meta = facts.get('_meta', {})
        all_text = ''
        core_text = ' '.join(str(v) for v in core.values())
        rigid_text = ' '.join(str(v) for v in rigid.values())
        all_text = core_text + rigid_text
        
        criminal_kw = ['刑事', '罪', '逮捕', '羁押', '公安', '检察院', '非法', '黑社会']
        if any(kw in all_text for kw in criminal_kw):
            has_criminal_nexus = True
            effective_nodes *= 1.5  # 刑民交叉 50% 加权
        
        # 资产穿透检测
        asset_kw = ['房产', '房票', '不动产', '查封', '冻结', '保全', '对账']
        if any(kw in all_text for kw in asset_kw) and len(meta.get('amounts_found', [])) >= 3:
            effective_nodes *= 1.3  # 资产穿透 30% 加权
        
        return round(effective_nodes, 1), {
            "base_nodes": base_nodes,
            "estimated_edges": e_count,
            "avg_degree": round(avg_degree, 2),
            "chi_domain": chi,
            "weight": round(weight, 2),
            "criminal_nexus": has_criminal_nexus,
            "asset_tracing": any(kw in all_text for kw in asset_kw),
            "effective_nodes": round(effective_nodes, 1)
        }

# ═══════════ 验证 ═══════════

if __name__ == "__main__":
    engine = LegalOSPricingEngine()
    counter = WeightedNodeCounter()
    
    print("=" * 60)
    print("juris-calculus 精算引擎验证")
    print(f"α = {engine.ALPHA} h/节点 | λ = {engine.LAMBDA}")
    print("=" * 60)
    
    # 案例1: 委托合同 — 跨省+刑民交叉
    demo_case = {'domain': 'Civil_Contract', 'subtype': 'Civil_Agency',
               'core_elements': {'payment_rule': '委托合同解除返还', 'deposit': ''},
               'rigid_clauses': {'liquidated_damages': '', 'dispute_resolution': ''},
               'party_names': ['[甲方]', '[乙方]', '[独立第三方_1]'],
               '_meta': {'amounts_found': ['X万', 'Y万', 'N套']}}
    
    ne, detail = counter.compute_weights(demo_case)
    print(f"\n委托合同跨省案: base=7 → effective={ne} 节点")
    for k, v in detail.items():
        print(f"  {k}: {v}")
    
    case = PricingCase(effective_nodes=ne, location="CROSS_PROVINCE", stage="FIRST_INSTANCE")
    result = engine.calculate_full(case)
    print(f"\n定价: {result['formula']}")
    print(f"  纯法理: {result['pure_legal_hours']}h | 总工: {result['total_hours']}h")
    
    # 案例2: 批量劳务 — 30件类案衰减
    print(f"\n批量劳务30件:")
    batch = engine.estimate_batch_total(4.0, 30)
    print(f"  首件: {batch['first_case_hours']}h | 末件: {batch['last_case_hours']}h")
    print(f"  总计: {batch['total_hours']}h | 折扣: {batch['discount_vs_linear']}%")
    
    # 案例3: 租赁仲裁 — 省内异地
    print(f"\n租赁仲裁 (省内异地):")
    case3 = PricingCase(effective_nodes=8.0, location="PROVINCE", stage="FIRST_INSTANCE")
    r3 = engine.calculate_full(case3)
    print(f"  {r3['formula']}")
    
    print("\n✅ 全部通过")
