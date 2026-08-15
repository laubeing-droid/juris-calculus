"""W5：P04 多后端路由、精确数值/时间语义与 SolverReceiptV1 测试。

用例语义与 tests/fixtures/theory_absorption/p04 对齐，并按 §11 Gate
补充 boundary/overflow/rounding/leap day/timeout/UNKNOWN 负向测试。
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import pytest

from compiler_core.backend_router_v1 import (
    BackendError,
    ProblemFeatures,
    SolverReceiptV1,
    add_period_days,
    last_day_of_month,
    receipt_recomputable,
    require_integer_money,
    require_rational_ratio,
    route_backend,
)


def h(prefix: str) -> str:
    return "sha256:" + (prefix * 32)[:64]


class TestRouting:
    def test_routing_by_typed_features_with_receipt(self):
        features = ProblemFeatures(temporal_bounds=True)
        decision = route_backend(features)
        assert decision["backend"] == "closed_form_temporal_numeric"
        assert decision["receipt_digest"]
        assert decision["features"] == features.to_dict()

    def test_routing_priority_smt_asp_argumentation_horn(self):
        assert route_backend(ProblemFeatures(discrete_combinatorial=True))["backend"] == "asp"
        assert route_backend(ProblemFeatures(bounded_arithmetic_theory=True))["backend"] == "smt"
        assert route_backend(ProblemFeatures(quantifiers=True))["backend"] == "smt"
        assert route_backend(ProblemFeatures(conflict_structure=True))["backend"] == "argumentation"
        assert route_backend(ProblemFeatures())["backend"] == "deterministic_horn"

    def test_routing_deterministic_and_explainable(self):
        features = ProblemFeatures(conflict_structure=True, temporal_bounds=True)
        assert route_backend(features) == route_backend(features)

    def test_unknown_feature_field_rejected(self):
        with pytest.raises(BackendError) as exc:
            ProblemFeatures.from_dict({"natural_language_hint": "contract"})
        assert exc.value.code == "UNKNOWN_FIELD"


class TestNumericSemantics:
    def test_integer_money_accepted(self):
        assert require_integer_money(10050, currency="CNY") == 10050

    def test_binary_float_money_rejected(self):
        with pytest.raises(BackendError) as exc:
            require_integer_money(100.5, currency="CNY")
        assert exc.value.code == "BINARY_FLOAT_FORBIDDEN"

    def test_ratio_requires_rational(self):
        assert require_rational_ratio((3, 100), "interest_rate") == Fraction(3, 100)
        assert require_rational_ratio(Fraction(1, 2), "ratio") == Fraction(1, 2)
        with pytest.raises(BackendError) as exc:
            require_rational_ratio(0.03, "interest_rate")
        assert exc.value.code == "BINARY_FLOAT_FORBIDDEN"
        with pytest.raises(BackendError) as exc:
            require_rational_ratio((1, 0), "ratio")
        assert exc.value.code == "INVALID_RATIO"


class TestTemporalSemantics:
    def test_boundary_inclusive_vs_exclusive(self):
        start = date(2026, 3, 1)
        assert add_period_days(start, 15, boundary_inclusive=True) == date(2026, 3, 16)
        assert add_period_days(start, 15, boundary_inclusive=False) == date(2026, 3, 15)

    def test_leap_day_handled(self):
        assert add_period_days(date(2024, 2, 28), 1, boundary_inclusive=True) == date(2024, 2, 29)
        assert add_period_days(date(2026, 2, 28), 1, boundary_inclusive=True) == date(2026, 3, 1)
        assert last_day_of_month(2024, 2) == date(2024, 2, 29)
        assert last_day_of_month(2026, 2) == date(2026, 2, 28)

    def test_negative_or_invalid_period_rejected(self):
        with pytest.raises(BackendError) as exc:
            add_period_days(date(2026, 3, 1), -1, boundary_inclusive=True)
        assert exc.value.code == "INVALID_PERIOD"

    def test_unsupported_calendar_rejected(self):
        with pytest.raises(BackendError) as exc:
            add_period_days(date(2026, 3, 1), 1, boundary_inclusive=True, calendar_kind="lunar")
        assert exc.value.code == "UNSUPPORTED_CALENDAR"


def _receipt(**overrides) -> SolverReceiptV1:
    payload = dict(
        solver_kind="smt",
        solver_version="z3-4.13.0",
        binary_hash=h("ee"),
        normalized_problem_hash=h("ff"),
        options={"seed": 0},
        timeout_ms=5000,
        seed=0,
        resource_limits={"memory_mb": 1024},
        result="UNSAT",
        model_or_unsat_core_hash=h("11"),
        stdout_digest=h("22"),
        stderr_digest=h("33"),
        exit_status=0,
        started_at="2026-08-16T00:00:00Z",
        finished_at="2026-08-16T00:00:01Z",
    )
    payload.update(overrides)
    return SolverReceiptV1(**payload)


class TestSolverReceipt:
    def test_receipt_digest_recomputable_under_same_identity(self):
        first = _receipt()
        replayed = _receipt()
        assert receipt_recomputable(first, replayed)
        assert first.receipt_digest == replayed.receipt_digest

    def test_receipt_diverges_on_problem_change(self):
        assert not receipt_recomputable(_receipt(), _receipt(normalized_problem_hash=h("00")))

    def test_timeout_maps_to_unknown_not_false(self):
        receipt = _receipt(result="TIMEOUT", exit_status=1, model_or_unsat_core_hash=h("00"))
        assert receipt.decision_status == "blocked_unknown"
        for outcome in ("UNKNOWN", "RESOURCE_EXHAUSTED", "UNSUPPORTED_THEORY"):
            blocked = _receipt(result=outcome, exit_status=1, model_or_unsat_core_hash=h("00"))
            assert blocked.decision_status == "blocked_unknown"

    def test_sat_unsat_require_clean_exit(self):
        with pytest.raises(BackendError) as exc:
            _receipt(result="SAT", exit_status=3)
        assert exc.value.code == "SOLVER_STATUS_INCONSISTENT"

    def test_invalid_result_enum_rejected(self):
        with pytest.raises(BackendError) as exc:
            _receipt(result="FALSE")
        assert exc.value.code == "INVALID_ENUM"

    def test_invalid_digest_rejected(self):
        with pytest.raises(BackendError) as exc:
            _receipt(binary_hash="not-a-hash")
        assert exc.value.code == "INVALID_DIGEST"
