#!/usr/bin/env python3
"""v2.0 MoE Rule Router - 14 domains from blueprint."""
from typing import List, Dict
from compiler_core.trust_labels import TrustLabel

EXPERT_SHARDS = {
    "刑事": ["刑事","犯罪","刑罚","故意","过失","自首","强奸","杀人","抢劫","盗窃","诈骗","贪污","受贿","毒品"],
    "行政": ["行政","国家赔偿","许可","处罚","复议","拆迁","征用"],
    "公司": ["公司","股东","股权","董事","破产","清算","章程","出资","法人"],
    "知产": ["知识产权","专利","商标","著作权","商业秘密","植物新品种"],
    "环境资源": ["环境","污染","生态","自然资源","保护区"],
    "海事": ["海事","海上","船舶","提单","运输","承运人"],
    "金融": ["金融","借贷","担保","票据","信用证","保险","证券","信托"],
    "劳动": ["劳动","工伤","解雇","工资","社保","竞业限制","劳动合同"],
    "婚姻家庭": ["婚姻","继承","抚养","赡养","离婚","夫妻","亲子","遗产"],
    "合同": ["合同","违约","定金","要约","承诺","买卖","租赁","借贷","购销","承揽","赠与"],
    "侵权": ["侵权","损害","赔偿","过错","消费者","医疗","人身","机动车"],
    "执行": ["执行","强制","拍卖","查封","冻结"],
    "程序": ["管辖","时效","证据","回避","再审","涉外","仲裁","港澳","送达"],
    "房地产": ["房地产","房屋","建设工程","土地","物业","开发商"],
}

CROSS_RULES = [
    ("合同","侵权","违约责任与侵权责任竞合"),
    ("合同","行政","行政合同特殊规则"),
    ("公司","刑事","单位犯罪排除"),
    ("劳动","行政","工伤认定行政程序优先"),
    ("婚姻家庭","合同","夫妻财产约定"),
    ("金融","合同","借贷合同特殊规则"),
    ("执行","程序","执行程序衔接"),
    ("海事","合同","海上货物运输合同"),
    ("刑事","行政","刑事附带行政赔偿"),
]

class RuleRouter:
    def __init__(self):
        self.shards = EXPERT_SHARDS
        self.cross = CROSS_RULES
    def route(self, fact_texts: List[str], top_k: int = 2) -> Dict:
        scores: Dict[str, int] = {}
        for domain, keywords in self.shards.items():
            score = 0
            for kw in keywords:
                for text in fact_texts:
                    if kw in text:
                        score += 1
            if score > 0:
                scores[domain] = score
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        if len(ranked) > top_k and ranked[top_k-1][1] == ranked[top_k][1]:
            tie_score = ranked[top_k-1][1]
            ranked = [(d,s) for d,s in ranked if s >= tie_score]
        else:
            ranked = ranked[:top_k]
        selected = [d for d, _ in ranked]
        cross_experts = []
        for a, b, note in self.cross:
            if a in selected and b in selected:
                cross_experts.append({"pair": (a, b), "note": note})
        return {"selected_experts": selected, "cross_expert_conflicts": cross_experts, "all_scores": dict(ranked), "trust_label": TrustLabel.ENGINEERING_BASELINE.value}
    @property
    def domain_count(self) -> int: return len(self.shards)
    @property
    def cross_count(self) -> int: return len(self.cross)
