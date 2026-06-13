#!/usr/bin/env python3
"""v2.0 Neural YAML Sync - dry-run gatekeeper for neural parameter promotion.

Design constraint: neural params NEVER auto-write to YAML without human review.
Default: dry_run=True generates PROMOTION_REPORT.md.
Actual write (dry_run=False) requires GPG-signed git commit + human approval.
Rollback: auto git revert if N consecutive A/B tests below baseline.
"""
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class PromotionReport:
    source_node: str
    params_changed: Dict[str, Tuple[Any, Any]]
    ab_test_results: Dict[str, float]
    recommendation: str = "PENDING_HUMAN_REVIEW"
    issues: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = ["# Neural YAML Promotion Report", ""]
        lines.append(f"**Source Node**: {self.source_node}")
        lines.append(f"**Recommendation**: {self.recommendation}")
        if self.issues:
            lines.append("")
            lines.append("## Blocking Issues")
            for issue in self.issues:
                lines.append(f"- {issue}")
        lines.append("")
        lines.append("## Parameters Changed")
        if self.params_changed:
            for key, (old, new) in self.params_changed.items():
                lines.append(f"- {key}: {old} -> {new}")
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## A/B Test Results")
        if self.ab_test_results:
            for metric, value in self.ab_test_results.items():
                lines.append(f"- {metric}: {value:.4f}")
        else:
            lines.append("- none")
        return "\n".join(lines)


class NeuralYAMLSyncer:
    rollback_conditions = {
        "min_f1_gain": 0.0,
        "consecutive_failures_for_revert": 50,
        "auto_revert": False,
    }

    def __init__(self, dry_run: bool = True, report_dir: str | Path | None = None):
        self.dry_run = dry_run
        self.report_dir = Path(report_dir) if report_dir else None
        self.last_report: Optional[PromotionReport] = None

    def promote(
        self,
        node_id: str,
        params: Dict[str, Tuple[Any, Any]],
        ab_results: Dict[str, float],
    ) -> PromotionReport:
        issues = self._validate_inputs(node_id, params, ab_results)
        if not self.dry_run:
            issues.append("AUTOMATIC_YAML_WRITE_FORBIDDEN")

        if issues:
            recommendation = "REJECTED"
        elif self._meets_baseline(ab_results):
            recommendation = "PENDING_HUMAN_REVIEW"
        else:
            recommendation = "REJECTED_BELOW_BASELINE"

        report = PromotionReport(
            source_node=node_id,
            params_changed=params,
            ab_test_results=ab_results,
            recommendation=recommendation,
            issues=issues,
        )
        self.last_report = report
        if self.report_dir:
            self.write_report(report)
        return report

    def write_report(self, report: PromotionReport, filename: str = "PROMOTION_REPORT.md") -> Path:
        if self.report_dir is None:
            raise ValueError("report_dir is required to write a promotion report")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / filename
        path.write_text(report.to_markdown(), encoding="utf-8")
        return path

    def should_rollback(self, consecutive_failures: int, f1_gain: float) -> bool:
        return (
            bool(self.rollback_conditions["auto_revert"])
            and consecutive_failures >= int(self.rollback_conditions["consecutive_failures_for_revert"])
            and f1_gain < float(self.rollback_conditions["min_f1_gain"])
        )

    @staticmethod
    def _validate_inputs(
        node_id: str,
        params: Dict[str, Tuple[Any, Any]],
        ab_results: Dict[str, float],
    ) -> List[str]:
        issues: List[str] = []
        if not node_id or not str(node_id).strip():
            issues.append("SOURCE_NODE_REQUIRED")
        if not isinstance(params, dict) or not params:
            issues.append("PARAMS_CHANGED_REQUIRED")
        else:
            for key, value in params.items():
                if not isinstance(key, str) or not key.strip():
                    issues.append("INVALID_PARAM_NAME")
                if not isinstance(value, tuple) or len(value) != 2:
                    issues.append(f"INVALID_PARAM_CHANGE: {key}")
        if not isinstance(ab_results, dict) or not ab_results:
            issues.append("AB_RESULTS_REQUIRED")
        else:
            for metric, value in ab_results.items():
                if not isinstance(metric, str) or not metric.strip():
                    issues.append("INVALID_METRIC_NAME")
                if not isinstance(value, (int, float)) or not isfinite(float(value)):
                    issues.append(f"INVALID_METRIC_VALUE: {metric}")
        return issues

    @classmethod
    def _meets_baseline(cls, ab_results: Dict[str, float]) -> bool:
        f1_gain = float(ab_results.get("f1_gain", 0.0))
        return f1_gain >= float(cls.rollback_conditions["min_f1_gain"])
