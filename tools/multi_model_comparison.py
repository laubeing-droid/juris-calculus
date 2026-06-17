"""Multi-model comparison — Horn vs AAF vs full pipeline."""
import time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.stratified_evaluator import StratifiedEvaluator
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.config_paths import rules_path


def compare_models(facts_dict):
    rules = load_rules_from_yaml(rules_path("zh_CN"))
    config = DomainConfig(domain=LegalDomain.CIVIL)

    results = {}

    # Model 1: Horn only
    state1 = IRState()
    for k, v in facts_dict.items():
        state1.facts[k] = LegalFact(id=k, description=v)
    ev1 = FixpointEvaluator(rules, config)
    t0 = time.time()
    r1 = ev1.evaluate_horn(state1)
    t1 = time.time()
    results['horn_only'] = {
        'claims': len(r1.claims),
        'avg_conf': round(sum(c.confidence for c in r1.claims.values()) / max(len(r1.claims), 1), 3),
        'time_ms': round((t1 - t0) * 1000, 1),
    }

    # Model 2: Full pipeline (StratifiedEvaluator)
    state2 = IRState()
    for k, v in facts_dict.items():
        state2.facts[k] = LegalFact(id=k, description=v)
    se = StratifiedEvaluator(rules_path("zh_CN"))
    t0 = time.time()
    r2 = se.evaluate(state2)
    t1 = time.time()
    results['full_pipeline'] = {
        'claims': len(r2),
        'avg_conf': round(sum(c.confidence for c in r2) / max(len(r2), 1), 3),
        'time_ms': round((t1 - t0) * 1000, 1),
    }

    return results


if __name__ == '__main__':
    test_cases = [
        {"breach_of_contract": "Defendant failed to deliver goods by deadline"},
        {"negligence": "Traffic accident causing injury", "damages": "Medical expenses 50000"},
        {"administrative_penalty": "Illegal construction ordered to demolish"},
    ]
    for i, case in enumerate(test_cases):
        print(f"\n=== Case {i+1} ===")
        result = compare_models(case)
        for model, metrics in result.items():
            print(f"  {model}: {metrics['claims']} claims, conf={metrics['avg_conf']}, {metrics['time_ms']}ms")
