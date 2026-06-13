"""Tests for performance knowledge graph enhancement (Section 7.1)."""
from pathlib import Path
from tools.perf_to_blueprint import extract_patterns


def test_patterns_extracted_from_baseline():
    import tempfile, json
    tmp = Path(tempfile.mkdtemp())
    bl_path = tmp / "baseline.json"
    bl_path.write_text(json.dumps({"metrics": {"rules_load_sec": 1.0, "evaluator_fixpoint_sec": 1.5, "router_scan_sec": 0.01, "blueprint_load_sec": 0.5, "cross_jurisdiction_sec": 0.1}, "details": {"eval_claims": 3, "router_experts": ["??"], "blueprint_domains": 14}}), encoding="utf-8")
    out_path = tmp / "perf_patterns.yaml"
    result = extract_patterns(str(bl_path), out_path)

    assert result["status"] == "PASS"
    assert result["pattern_count"] >= 4
    assert out_path.exists()
