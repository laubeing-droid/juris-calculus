"""Sample 1/3: a normal Harness -> JC -> Harness request (synthetic).

Run:  python examples/harness/sample_normal.py
Read: the JSON payload is exactly HarnessRunResultV5.to_dict(); the final
line is the lawyer-facing projection the Harness may display.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _adapter import human_projection, run_case
from tests.contract.test_v5_profile_chain import EXCEPTION_FACTS


def main() -> int:
    result, _store, _harness, _run_ref = run_case(
        case_suffix="normal",
        fact_keys=EXCEPTION_FACTS,
        profiles=("grounded",),
    )
    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("---- harness display ----")
    print(human_projection(result))
    assert payload["run_status"] == "success"
    assert payload["issues"][0]["conclusion_status"] == "accepted"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
