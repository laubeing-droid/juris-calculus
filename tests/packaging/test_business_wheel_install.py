"""BC12 — the business capability works from the INSTALLED wheel, off sys.path.

Builds the real wheel, installs it into an out-of-tree target directory, and
runs a driver script from a neutral working directory. The driver asserts the
import origin, then exercises the public business surface end to end. No test
double, no workspace sys.path, no reference-script bypass.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

REPO = Path(__file__).resolve().parents[2]

DRIVER = """
import json
import sys
from pathlib import Path

import compiler_core

origin = Path(compiler_core.__file__).resolve()
# The decisive assertion: compiler_core must come from the install target,
# never from the repository working tree.
assert str(origin).startswith(str(Path(env_target).resolve())), origin

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
from compiler_core.canonical_serialization import DigestV4, digest_value

SOURCE = "合成示例：已到期本金1000元；争议清偿300元；只计算条件本金余额。"
RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [
        {
            "source_id": "acceptance-statute",
            "jurisdiction": "TEST",
            "authority_tier": "official_first_party",
            "issuer": "Acceptance Test Authority",
            "title": "acceptance-statute",
            "publication_time": "2020-01-01T00:00:00Z",
            "effective_from": "2020-01-01T00:00:00Z",
            "retrieved_at": "2026-08-01T00:00:00Z",
            "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                        "page": None, "span_start": None, "span_end": None},
            "content": "验收测试规则文本：仅用于工程验证，不构成任何法律依据。",
            "structure_sections": ["第一条"],
        },
    ],
    "rules": [
        {
            "rule_id": "acc-base",
            "jurisdiction": "TEST",
            "governing_law": "acceptance-statute",
            "source_id": "acceptance-statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "acc.contract", "required": True}],
            "conclusion": {"value": "applies"},
            "effective_from": "2020-01-01T00:00:00Z",
        },
    ],
}
rules = Path(work) / "rules"
rules.mkdir(parents=True, exist_ok=True)
(rules / "jc-local-pack.json").write_text(
    json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")

context = BusinessContextV1(
    request="WHEEL-SYNTHETIC-CASE-1", jurisdiction="TEST",
    event_time="2026-08-01", decision_time="2026-09-09",
    procedure="conditional_analysis", stage="analysis", party="claimant",
    issue="principal-balance", scenario="finite-conditional-completions",
    profile="grounded", law_version="source-snapshot-example",
    interpretation="explicit-reference", rulepack_version="t",
    engine_version="reference-2.1", model_version="m", evidence_version="e",
    target="award_at_least_threshold", semantic_scope="height_bounded",
    assumptions=("仅付款认定作为分支", "示例前提：债权成立且已到期"), max_depth=2)
spec = BusinessSpecV1(
    relation_id="r", creditor="甲公司", debtor="乙公司", debt_id="D1",
    principal="1000", due_day="2026-08-01", asof_day="2026-09-09",
    sources=(BusinessSourceSpanV1("S", "1", SOURCE, 0, len(SOURCE), SOURCE),),
    payments=(BusinessPaymentV1(
        "P1", "300", "2026-08-20", "乙公司", "甲公司", "D1",
        "payment_recognized", "S"),),
    facts=(BusinessAtomStateV1("payment_recognized", None),),
    constraint=BusinessFormulaV1("true"),
    approved_policy="SYNTHETIC-CONDITIONAL-PRINCIPAL/1")
wt = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", True),))
wf = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", False),))
model = BusinessModelInputsV1(
    weights=(BusinessWorldWeightV1(wt, "2/5"), BusinessWorldWeightV1(wf, "3/5")),
    threshold="800", costs=("100", "60", "10", "10"),
    legal_options=("600", "850", "1100"), basis="SYNTHETIC-SETTLEMENT-GRID/1")
task = BusinessTaskV1(
    task_id="wheel-task-1", issue_id="principal-balance",
    requirement_id="SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1",
    profile="SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
    selection_ref=DigestV4(digest_value({"host-selection": "wheel-rev-1"})),
    input=BusinessTaskInputV1(context=context, spec=spec, model=model))

client = create_local_client(Path(work) / "state", rules)
caps = client.business_capabilities()
bundle = client.local_case_bundle(
    case_id="wheel-business-case", decision_time="2026-09-11T00:00:00Z",
    business_tasks=(task,))
result = client.evaluate_harness_bundle(
    bundle, case_id="wheel-business-case", issue_queries=[])
row = result["business_results"][0]
analytics = row["analytics"]
assert analytics["expected_balance"] == "880", analytics
assert analytics["event_probability"] == "3/5"
assert analytics["selected"] == "850"
docs = client.business_delivery_documents(
    run_identity_ref=result["run_identity_ref"], business_task_id=task.task_id)
verdict = client.verify_business_delivery(
    run_identity_ref=result["run_identity_ref"],
    business_task_id=task.task_id,
    selected_input_ref=task.selection_ref,
    artifacts=docs)
print(json.dumps({
    "origin": str(origin),
    "capability": caps["capability"],
    "completion": row["completion"],
    "delivery_status": verdict["status"],
}))
assert verdict["status"] == "ACCEPTED", verdict
"""


def test_bc12_business_capability_works_from_installed_wheel() -> None:
    with tempfile.TemporaryDirectory(prefix="jc-business-wheel-") as tmp:
        work = Path(tmp)
        dist = work / "dist"
        target = work / "install"
        build = subprocess.run(
            [sys.executable, "-B", "-m", "pip", "wheel", ".", "--no-build-isolation",
             "--no-deps", "-w", str(dist), "-q"],
            cwd=REPO, capture_output=True, text=True, timeout=600,
        )
        assert build.returncode == 0, build.stderr[-2000:]
        wheels = list(dist.glob("juris_calculus-*.whl"))
        assert wheels, "no wheel built"
        install = subprocess.run(
            [sys.executable, "-B", "-m", "pip", "install", "--no-deps", "--target",
             str(target), "-q", str(wheels[0])],
            cwd=work, capture_output=True, text=True, timeout=600,
        )
        assert install.returncode == 0, install.stderr[-2000:]

        driver = work / "driver.py"
        driver.write_text(
            "env_target = r'%s'\nwork = r'%s'\n%s\n" % (str(target), str(work), DRIVER),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(target)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-B", str(driver)],
            cwd=work, capture_output=True, text=True, timeout=600, env=environment,
        )
        assert completed.returncode == 0, (
            completed.stdout[-2000:] + "\n---\n" + completed.stderr[-2000:]
        )
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        assert report["capability"] == "jc-business-root/1"
        assert report["completion"] == "exact_finite_scenarios"
        assert report["delivery_status"] == "ACCEPTED"
        assert str(target) in report["origin"]
