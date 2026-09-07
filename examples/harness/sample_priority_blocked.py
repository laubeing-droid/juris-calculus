"""Sample 3/3: an admitted priority relation the policy cannot explain.

Run:  python examples/harness/sample_priority_blocked.py
Read: the run succeeds, but the requested issue may NOT be presented as
completely solved: the projection reports status=incomplete with a formal
priority_policy_missing obligation, partial completeness, openObligations
assurance, and no certificate. The harness display states this in the open.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _adapter import human_projection, run_case
from tests.contract.test_v5_profile_chain import EXCEPTION_FACTS
from tests.contract.test_v5_final_remediation import PRIORITY_CONDITION_FACT


def main() -> int:
    result, _store, _harness, _run_ref = run_case(
        case_suffix="priority-blocked",
        fact_keys=EXCEPTION_FACTS + (PRIORITY_CONDITION_FACT,),
    )
    payload = result.to_dict()
    print(json.dumps({
        "run_status": payload["run_status"],
        "decision_status": payload["decision_status"],
        "completeness": payload["completeness"],
        "issues": [
            {
                "issue_id": item["issue_id"],
                "conclusion_status": item["conclusion_status"],
                "mapping_complete": item["mapping_complete"],
            }
            for item in payload["issues"]
        ],
        "open_obligations": payload["open_obligations"],
        "assurance_specs": payload["assurance_specs"],
        "horn": payload["horn"],
    }, ensure_ascii=False, indent=2))
    print("---- harness display ----")
    print(human_projection(result))
    assert payload["run_status"] == "success"
    assert payload["completeness"] == "partial"
    assert payload["issues"][0]["conclusion_status"] == "incomplete"
    assert any(
        item["code"] == "priority_policy_missing"
        for item in payload["open_obligations"]
    )
    print("sample-priority-blocked: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
