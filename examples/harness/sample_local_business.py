"""Runnable first-batch sample: synthetic conditional principal over the
public local surface (ROUTE1 J15, BC12/BC13).

Run inside an installed wheel environment (or the repository):

    python examples/harness/sample_local_business.py <state-dir> <rules-dir>

The sample builds a typed jc-business-root/1 task with a synthetic I0,
evaluates it once through ``evaluate_harness_bundle``, exports the protected
two-file view, and verifies the actual bytes through the verify-only
``verify_business_delivery`` method. Nothing here touches real case data.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.client import create_local_client
from compiler_core.contracts import (
    BusinessAtomPairV1,
    BusinessAtomStateV1,
    BusinessContextV1,
    BusinessFormulaV1,
    BusinessModelInputsV1,
    BusinessPaymentV1,
    BusinessSpecV1,
    BusinessSourceSpanV1,
    BusinessTaskInputV1,
    BusinessTaskV1,
    BusinessWorldV1,
    BusinessWorldWeightV1,
)


SOURCE = "合成示例：已到期本金1000元；争议清偿300元；只计算条件本金余额。"
REQUIREMENT = "SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1"
PROFILE = "SYNTHETIC-CONDITIONAL-PRINCIPAL/1"


def build_task() -> BusinessTaskV1:
    context = BusinessContextV1(
        request="SAMPLE-SYNTHETIC-PRINCIPAL-1",
        jurisdiction="TEST",
        event_time="2026-08-01",
        decision_time="2026-09-09",
        procedure="conditional_analysis",
        stage="analysis",
        party="claimant",
        issue="principal-balance",
        scenario="finite-conditional-completions",
        profile="grounded",
        law_version="source-snapshot-example",
        interpretation="explicit-reference",
        rulepack_version="sample-1",
        engine_version="reference-2.1",
        model_version="synthetic-model-1",
        evidence_version="sample-evidence-1",
        target="award_at_least_threshold",
        semantic_scope="height_bounded",
        assumptions=("仅付款认定作为分支", "示例前提：债权成立且已到期"),
        max_depth=2,
    )
    spec = BusinessSpecV1(
        relation_id="principal-claim",
        creditor="甲公司",
        debtor="乙公司",
        debt_id="DEBT-1",
        principal="1000",
        due_day="2026-08-01",
        asof_day="2026-09-09",
        sources=(BusinessSourceSpanV1(
            "SYNTHETIC-BASIS", "1", SOURCE, 0, len(SOURCE), SOURCE,
        ),),
        payments=(BusinessPaymentV1(
            "P1", "300", "2026-08-20", "乙公司", "甲公司", "DEBT-1",
            "payment_recognized", "SYNTHETIC-BASIS",
        ),),
        facts=(BusinessAtomStateV1("payment_recognized", None),),
        constraint=BusinessFormulaV1("true"),
        approved_policy=PROFILE,
    )
    world_true = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", True),))
    world_false = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", False),))
    model = BusinessModelInputsV1(
        weights=(
            BusinessWorldWeightV1(world_true, "2/5"),
            BusinessWorldWeightV1(world_false, "3/5"),
        ),
        threshold="800",
        costs=("100", "60", "10", "10"),
        legal_options=("600", "850", "1100"),
        basis="SYNTHETIC-SETTLEMENT-GRID/1",
    )
    return BusinessTaskV1(
        task_id="sample-task-1",
        issue_id="principal-balance",
        requirement_id=REQUIREMENT,
        profile=PROFILE,
        selection_ref=DigestV4(digest_value({"host-selection": "sample-rev-1"})),
        input=BusinessTaskInputV1(context=context, spec=spec, model=model),
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    state_root, rules_root = Path(sys.argv[1]), Path(sys.argv[2])
    client = create_local_client(state_root, rules_root)
    capabilities = client.business_capabilities()
    task = build_task()
    bundle = client.local_case_bundle(
        case_id="sample-business-case",
        decision_time="2026-09-11T00:00:00Z",
        business_tasks=(task,),
    )
    result = client.evaluate_harness_bundle(
        bundle, case_id="sample-business-case", issue_queries=[],
    )
    row = result["business_results"][0]
    if row["completion"] != "exact_finite_scenarios":
        raise SystemExit(f"sample run did not complete exactly: {row}")
    documents = client.business_delivery_documents(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
    )
    out_dir = state_root / "delivery"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in documents.items():
        (out_dir / name).write_bytes(payload)
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
        selected_input_ref=task.selection_ref,
        artifacts=documents,
    )
    report = {
        "capability": capabilities["capability"],
        "checker_version": row["checker_version"],
        "formal_evidence": row["formal_evidence"],
        "analytics": row["analytics"],
        "delivery_status": verdict["status"],
        "delivery_record_ref": verdict["verification_record_ref"],
        "files_written": [out_dir / name for name in documents],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if verdict["status"] == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
