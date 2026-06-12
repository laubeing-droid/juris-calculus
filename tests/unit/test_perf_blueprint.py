"""Tests for performance knowledge graph enhancement (Section 7.1)."""
from pathlib import Path
from tools.perf_to_blueprint import extract_patterns


def test_patterns_extracted_from_baseline():
    result = extract_patterns("reports/perf/baseline1.json")

    assert result["status"] == "PASS"
    assert result["pattern_count"] >= 4
    assert Path("configs/perf_patterns.yaml").exists()
