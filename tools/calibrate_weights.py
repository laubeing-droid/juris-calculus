"""Weight calibration via grid search.

Four-dimensional weight grid: (depth, horn, concept, mechanical)
Objective: maximize coverage x (1 - false_positive_rate)
Reference: domain_config.example.yaml weights: [0.25, 0.15, 0.35, 0.25]
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.domain_config import DomainConfig, get_domain_config
from compiler_core.types import LegalDomain, IRState, LegalFact
import itertools


def run_benchmark_with_weights(rules, config, test_cases):
    results = []
    for case in test_cases:
        state = IRState()
        for fid, desc in case.get("facts", {}).items():
            state.facts[fid] = LegalFact(id=fid, description=desc)
        ev = FixpointEvaluator(rules, config)
        try:
            result = ev.evaluate(state)
            converged = result.iteration_count < result.max_iterations
            claims = len(result.claims)
            results.append({"converged": converged, "claims": claims})
        except Exception:
            results.append({"converged": False, "claims": 0})
    return results


def grid_search_weights(rules_path: str, test_cases: list):
    rules = load_rules_from_yaml(rules_path)
    best_weights = (0.2, 0.2, 0.4, 0.2)
    best_score = 0.0

    for w1 in [0.15, 0.20, 0.25, 0.30]:
        for w2 in [0.10, 0.15, 0.20]:
            for w3 in [0.30, 0.35, 0.40, 0.45]:
                w4 = round(1.0 - w1 - w2 - w3, 2)
                if w4 < 0.05 or w4 > 0.35:
                    continue
                config = DomainConfig(
                    domain=LegalDomain.CIVIL,
                    weights=(w1, w2, w3, w4),
                )
                results = run_benchmark_with_weights(rules, config, test_cases)
                converged = sum(1 for r in results if r["converged"])
                avg_claims = sum(r["claims"] for r in results) / max(len(results), 1)
                score = converged * 0.7 + min(avg_claims / 10, 1.0) * 0.3
                if score > best_score:
                    best_score = score
                    best_weights = (w1, w2, w3, w4)

    return best_weights, best_score


if __name__ == "__main__":
    rules_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'rules.yaml')
    test_cases = [
        {"facts": {"fact_a": "breach of contract"}},
        {"facts": {"fact_b": "negligence causing harm"}},
        {"facts": {"fact_c": "administrative penalty"}},
    ]
    weights, score = grid_search_weights(rules_path, test_cases)
    print(f"Best weights: {weights}")
    print(f"Best score: {score:.3f}")
