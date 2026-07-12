import json

from compiler_core.shadow_state import ShadowCandidate, ShadowState, compare_shadow_to_official
from tools.shadow_divergence_report import build_report, build_report_from_json, write_jsonl_example


def test_shadow_state_does_not_accept_candidates_by_default():
    state = ShadowState(world_id="w1")
    state.add_candidate(ShadowCandidate(
        candidate_id="cand-1",
        candidate_type="FactCandidate",
        payload={"fact": "Payment_Missing"},
        confidence=0.8,
    ))

    assert state.accepted_candidates() == []
    assert state.to_dict()["candidate_count"] == 1


def test_shadow_divergence_report_marks_differences():
    report = build_report(["Breach_Established"], ["No_Breach"], world_id="w1")

    assert report["status"] == "DIVERGED"
    assert report["official_only"] == ["Breach_Established"]
    assert report["shadow_only"] == ["No_Breach"]


def test_shadow_divergence_report_reads_json(tmp_path):
    path = tmp_path / "shadow.json"
    path.write_text(json.dumps({
        "world_id": "w-json",
        "official_claims": ["A"],
        "shadow_claims": ["B"],
    }), encoding="utf-8")

    report = build_report_from_json(path)

    assert report["world_id"] == "w-json"
    assert report["status"] == "DIVERGED"


def test_shadow_divergence_jsonl_export(tmp_path):
    report = build_report(["A"], ["B"], "w-jsonl")
    out = tmp_path / "divergence.jsonl"

    write_jsonl_example(report, out)

    assert "w-jsonl" in out.read_text(encoding="utf-8")


def test_shadow_compare_aligned():
    report = compare_shadow_to_official(["A", "B"], ["B", "A"])

    assert report["divergence"] is False

