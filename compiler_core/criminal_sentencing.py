"""Criminal sentencing prediction."""
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SentencingFactors:
    statutory_range_months: Tuple[int, int]
    mitigating_factors: List[str] = field(default_factory=list)
    aggravating_factors: List[str] = field(default_factory=list)

    def predict_range(self) -> Tuple[int, int]:
        base_min, base_max = self.statutory_range_months
        adjustment = len(self.aggravating_factors) * 2 - len(self.mitigating_factors) * 3
        return (max(0, base_min + adjustment), max(0, base_max + adjustment))
