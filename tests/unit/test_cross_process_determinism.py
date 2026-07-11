import json
import os
from pathlib import Path
import subprocess
import sys

from compiler_core.automated_pipeline import run_automated_pipeline
from compiler_core.batch_processor import _trace_id
from compiler_core.evidence_checklist import build_enhanced_checklist
from compiler_core.litigation_renderer import LitigationChainRenderer


ROOT = Path(__file__).resolve().parents[2]


def _public_ids():
    """收集仍在v2表面出现的公共ID，证明提交3已移除进程随机hash。"""

    facts = ["fact::b", "fact::a"]
    return {
        "pipeline": run_automated_pipeline([], facts).case_id,
        "renderer": LitigationChainRenderer([], facts).evaluate().case_id,
        "checklist": build_enhanced_checklist([], facts, []).case_id,
        "trace": _trace_id("contract::1"),
    }


def test_public_ids_are_content_based_and_input_order_invariant():
    first = _public_ids()
    reversed_facts = ["fact::a", "fact::b"]

    assert first["pipeline"] == run_automated_pipeline([], reversed_facts).case_id
    assert first["renderer"] == LitigationChainRenderer([], reversed_facts).evaluate().case_id
    assert first["checklist"] == build_enhanced_checklist([], reversed_facts, []).case_id
    assert first["trace"].startswith("TRACE-")


def test_public_ids_are_stable_across_hash_seed_timezone_and_process():
    script = (
        "import json; "
        "from compiler_core.automated_pipeline import run_automated_pipeline; "
        "from compiler_core.batch_processor import _trace_id; "
        "from compiler_core.evidence_checklist import build_enhanced_checklist; "
        "from compiler_core.litigation_renderer import LitigationChainRenderer; "
        "facts=['fact::b','fact::a']; "
        "ids={'pipeline':run_automated_pipeline([],facts).case_id,"
        "'renderer':LitigationChainRenderer([],facts).evaluate().case_id,"
        "'checklist':build_enhanced_checklist([],facts,[]).case_id,"
        "'trace':_trace_id('contract::1')}; "
        "print(json.dumps(ids, sort_keys=True))"
    )
    outputs = []
    for seed, timezone in (("1", "UTC"), ("987654", "Asia/Shanghai")):
        env = dict(os.environ, PYTHONHASHSEED=seed, TZ=timezone, PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        outputs.append(json.loads(completed.stdout))

    assert outputs[0] == outputs[1] == _public_ids()
