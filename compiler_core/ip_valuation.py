"""IP valuation module."""
from dataclasses import dataclass


@dataclass
class IPValuation:
    ip_type: str
    development_cost: float = 0.0
    licensing_revenue: float = 0.0
    market_value: float = 0.0
    remaining_useful_life_years: int = 0

    def estimate_value(self) -> float:
        if self.market_value > 0:
            return self.market_value
        if self.licensing_revenue > 0 and self.remaining_useful_life_years > 0:
            return self.licensing_revenue * self.remaining_useful_life_years
        return self.development_cost
