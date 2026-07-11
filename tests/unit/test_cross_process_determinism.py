"""规范ID跨进程、hash seed和时区保持稳定。"""

import json
import os
from pathlib import Path
import subprocess
import sys

from compiler_core.canonical_serialization import content_id
from compiler_core.evidence_checklist import build_enhanced_checklist


ROOT = Path(__file__).resolve().parents[2]


def _public_ids():
    """只检查仍有正式消费者的内容寻址ID。"""

    facts = ["fact::b", "fact::a"]
    return {
        "case": content_id("case", {"facts": sorted(facts)}),
        "checklist": build_enhanced_checklist([], facts, []).case_id,
    }


def test_public_ids_are_content_based_and_input_order_invariant():
    """输入排列不得改变公开内容ID。"""

    reversed_facts = ["fact::a", "fact::b"]
    assert _public_ids()["case"] == content_id("case", {"facts": sorted(reversed_facts)})
    assert _public_ids()["checklist"] == build_enhanced_checklist([], reversed_facts, []).case_id


def test_public_ids_are_stable_across_hash_seed_timezone_and_process():
    """不同进程环境不得改变规范ID。"""

    script = (
        "import json; "
        "from compiler_core.canonical_serialization import content_id; "
        "from compiler_core.evidence_checklist import build_enhanced_checklist; "
        "facts=['fact::b','fact::a']; "
        "ids={'case':content_id('case',{'facts':sorted(facts)}),"
        "'checklist':build_enhanced_checklist([],facts,[]).case_id}; "
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
