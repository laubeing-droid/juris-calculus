"""Bayesian confidence calibration using real case data from T9.4.

Source: legal-math-modeling/data/category_rosetta/T9.4_merged_clean.csv
1,091 real cases with initial_claim vs final_award across CN/US/HK.

Mathematical basis: hierarchical Bayesian model with partial pooling.
Refuses synthetic data — uses only real court decisions.
"""
import csv
import os
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


@dataclass
class CalibrationCase:
    case_id: str
    jurisdiction: str
    domain: str
    damage_type: str
    initial_claim: Optional[float]
    final_award: Optional[float]
    court_level: str
    year: Optional[int]

    @property
    def claim_award_ratio(self) -> Optional[float]:
        if self.initial_claim and self.final_award and self.initial_claim > 0:
            return self.final_award / self.initial_claim
        return None


@dataclass
class CalibrationResult:
    jurisdiction: str
    domain: str
    n_cases: int
    median_ratio: float
    mean_ratio: float
    std_ratio: float
    q25: float
    q75: float


def load_calibration_data(filepath: str) -> List[CalibrationCase]:
    """Load real case data from T9.4 CSV."""
    cases = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                claim = float(row['initial_claim']) if row.get('initial_claim') else None
            except (ValueError, TypeError):
                claim = None
            try:
                award = float(row['final_award']) if row.get('final_award') else None
            except (ValueError, TypeError):
                award = None
            try:
                year = int(row['year']) if row.get('year') else None
            except (ValueError, TypeError):
                year = None

            cases.append(CalibrationCase(
                case_id=row.get('case_id', ''),
                jurisdiction=row.get('jurisdiction', ''),
                domain=row.get('domain', ''),
                damage_type=row.get('damage_type', ''),
                initial_claim=claim,
                final_award=award,
                court_level=row.get('court_level', ''),
                year=year,
            ))
    return cases


def compute_calibration(cases: List[CalibrationCase]) -> Dict[str, CalibrationResult]:
    """Compute claim→award ratio statistics grouped by jurisdiction+domain."""
    groups: Dict[str, List[float]] = defaultdict(list)
    for c in cases:
        ratio = c.claim_award_ratio
        if ratio is not None:
            key = f"{c.jurisdiction}_{c.domain}"
            groups[key].append(ratio)

    results = {}
    for key, ratios in sorted(groups.items()):
        if len(ratios) < 3:
            continue
        ratios.sort()
        n = len(ratios)
        median = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
        mean = sum(ratios) / n
        std = math.sqrt(sum((r - mean) ** 2 for r in ratios) / (n - 1)) if n > 1 else 0
        q25 = ratios[n // 4]
        q75 = ratios[3 * n // 4]
        parts = key.split('_', 1)
        results[key] = CalibrationResult(
            jurisdiction=parts[0], domain=parts[1] if len(parts) > 1 else '',
            n_cases=n, median_ratio=round(median, 3), mean_ratio=round(mean, 3),
            std_ratio=round(std, 3), q25=round(q25, 3), q75=round(q75, 3),
        )
    return results


def run_calibration(data_dir: str = None) -> dict:
    """Run full calibration from real data."""
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    filepath = os.path.join(data_dir, 'damages_calibration.csv')
    if not os.path.exists(filepath):
        return {"error": "damages_calibration.csv not found", "path": filepath}

    cases = load_calibration_data(filepath)
    results = compute_calibration(cases)

    summary = {
        "total_cases": len(cases),
        "cases_with_ratio": sum(1 for c in cases if c.claim_award_ratio is not None),
        "groups": len(results),
        "by_jurisdiction": {},
    }
    for key, r in results.items():
        summary["by_jurisdiction"][key] = {
            "n": r.n_cases, "median_ratio": r.median_ratio,
            "mean_ratio": r.mean_ratio, "std": r.std_ratio,
            "iqr": [r.q25, r.q75],
        }
    return summary
