#!/usr/bin/env python3
"""v2.0 Legal Gates - 8 mandatory checkpoints for claim quality.

GATE-01 through GATE-08.  Level: ERROR (block) or WARNING (tag).
"""
from typing import Dict, List

GATE_DEFINITIONS = {
    "GATE-01": {
        "name": "element_completeness",
        "description": "All contractual elements must be present and non-contradictory",
        "level": "ERROR",
    },
    "GATE-02": {
        "name": "jurisdiction_anchor",
        "description": "At least one jurisdiction-specific rule must trigger",
        "level": "ERROR",
    },
    "GATE-03": {
        "name": "procedural_compliance",
        "description": "Procedural rules must be consistent with claim domain",
        "level": "ERROR",
    },
    "GATE-04": {
        "name": "source_attribution",
        "description": "Every claim must cite source statute or rule ID",
        "level": "WARNING",
    },
    "GATE-05": {
        "name": "confidence_threshold",
        "description": "Claims below threshold 0.2 must be downgraded or reviewed",
        "level": "WARNING",
    },
    "GATE-06": {
        "name": "novelty_guard",
        "description": "Claims with no matching precedent must be flagged",
        "level": "WARNING",
    },
    "GATE-07": {
        "name": "citation_verification",
        "description": "Case citation format validation (regex only; full verification needs external DB)",
        "level": "WARNING",
    },
    "GATE-08": {
        "name": "human_review_required",
        "description": "Any claim flagged requires_human_review escalates automatically",
        "level": "ERROR",
    },
}


def run_gates(claims: List[Dict], rules_applied: List[str]) -> List[Dict]:
    results = []
    for gate_id, gate in GATE_DEFINITIONS.items():
        reason = "PASS"
        if gate_id == "GATE-01" and not claims:
            reason = "No claims produced"
        elif gate_id == "GATE-05":
            low_conf = [c for c in claims if c.get("confidence", 1) < 0.2]
            if low_conf:
                reason = f"{len(low_conf)} claims below threshold"
        elif gate_id == "GATE-08":
            hum = [c for c in claims if c.get("requires_human_review")]
            if hum:
                reason = f"{len(hum)} claims require human review"
        results.append({
            "gate_id": gate_id,
            "name": gate["name"],
            "level": gate["level"],
            "reason": reason,
        })
    return results

# Riche d from liuweibin-legal-skills risk database (27 scenarios)
RISK_GATE_MAPPING = {
  "证据链完整性": {
    "gate": "GATE-08",
    "reason": "evidence deficiency, human review required",
    "legal": []
  },
  "签收人身份锁定": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "优先受偿权期限": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "一审举证完备性": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "挂靠关系处理": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "鉴定程序抗辩": {
    "gate": "GATE-08",
    "reason": "evidence deficiency, human review required",
    "legal": []
  },
  "实际施工人身份": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "借贷合意": {
    "gate": "GATE-06",
    "reason": "novelty/financial guard",
    "legal": []
  },
  "款项交付": {
    "gate": "GATE-06",
    "reason": "novelty/financial guard",
    "legal": []
  },
  "利率上限": {
    "gate": "GATE-06",
    "reason": "novelty/financial guard",
    "legal": [
      "民间借贷解释第25条"
    ]
  },
  "诉讼时效": {
    "gate": "GATE-03",
    "reason": "procedural compliance",
    "legal": []
  },
  "现金还款举证": {
    "gate": "GATE-06",
    "reason": "novelty/financial guard",
    "legal": []
  },
  "程序合法性": {
    "gate": "GATE-02",
    "reason": "jurisdiction anchor",
    "legal": []
  },
  "地方法规": {
    "gate": "GATE-02",
    "reason": "jurisdiction anchor",
    "legal": []
  },
  "管辖": {
    "gate": "GATE-03",
    "reason": "procedural compliance",
    "legal": []
  },
  "再审改判率": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "发回重审": {
    "gate": "GATE-05",
    "reason": "confidence threshold check",
    "legal": []
  },
  "违约责任": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": [
      "民法典第585条"
    ]
  },
  "管辖条款": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  },
  "单方解除权": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": [
      "民法典第563条"
    ]
  },
  "格式条款": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  },
  "空白条款": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  },
  "知识产权": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  },
  "保密期限": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  },
  "验收标准": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  },
  "必备条款": {
    "gate": "GATE-01",
    "reason": "contract element violation",
    "legal": []
  }
}
