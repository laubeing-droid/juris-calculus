"""Sample 2/3: same-case add-only follow-up reusing the parent Horn state.

Run:  python examples/harness/sample_incremental.py
Read: the parent request completes with a full recompute and seals a
reusable Horn subject state; the child carries incremental_parent_v5, the
sealed state is recovered from the shared persistent audit store, and the
second run reports mode=incremental with the delta-only solver workload.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _adapter import human_projection, run_incremental_pair
from tests.contract.test_v5_profile_chain import EXCEPTION_FACTS

PARENT_FACTS = EXCEPTION_FACTS + ("synthetic-horn.a",)
CHILD_FACTS = EXCEPTION_FACTS + ("synthetic-horn.a", "synthetic-horn.c")


def main() -> int:
    parent, child = run_incremental_pair(
        parent_facts=PARENT_FACTS, child_facts=CHILD_FACTS,
    )
    summary = {
        "parent": {
            "run_status": parent.run_status,
            "horn_mode": parent.horn_mode,
            "solver_rule_evaluations": parent.horn_solver_work,
            "checker_rule_evaluations": parent.horn_checker_work,
        },
        "child": {
            "run_status": child.run_status,
            "horn_mode": child.horn_mode,
            "horn_fallback_reason": child.horn_fallback_reason,
            "solver_rule_evaluations": child.horn_solver_work,
            "checker_rule_evaluations": child.horn_checker_work,
        },
        "child_issues": [
            {
                "issue_id": item.issue_id,
                "conclusion_status": item.conclusion_status(),
            }
            for item in child.issues
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("---- harness display ----")
    print(human_projection(child))
    assert parent.horn_mode == "full_recompute"
    assert child.horn_mode == "incremental", child.horn_fallback_reason
    assert child.horn_solver_work < child.horn_checker_work
    print("sample-incremental: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
