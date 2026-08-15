"""W5：P04 多后端路由、精确时间/数值语义与 SolverReceiptV1。

依据：20260815 施工方案 §11。规则：

1. 路由只读 Legal-IVL typed rule/constraint（ProblemFeatures），
   不读自然语言标签；输出 explainable feature receipt。
2. 金额统一最小货币单位整数；比例和利率使用有理数（Fraction）；
   binary float 不得进入正式路径。
3. 舍入规则、边界包含性、日历、时区和期间起止全部进入输入身份。
4. ASP 用于离散组合/稳定模型需求；SMT 用于有界算术、时态和一致性义务。
5. timeout、资源耗尽、unsupported theory、UNKNOWN 不得转为 FALSE 或 PASS。
6. receipt 与 fixture oracle 分离：receipt 只描述一次真实 solver 运行，
   不复用生产求值函数生成预期值。
"""

from __future__ import annotations

from dataclasses import dataclass
import calendar as _calendar
from datetime import date, timedelta
from fractions import Fraction
import re
from typing import Any, Mapping

from compiler_core.jcs import jcs_digest


BACKENDS = (
    "deterministic_horn",
    "argumentation",
    "closed_form_temporal_numeric",
    "asp",
    "smt",
    "direct_oracle",
)

SOLVER_RESULTS = ("SAT", "UNSAT", "UNKNOWN", "TIMEOUT", "RESOURCE_EXHAUSTED", "UNSUPPORTED_THEORY")

_CANONICAL_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class BackendError(ValueError):
    """路由或 solver 语义错误；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProblemFeatures:
    """typed capability 特征；路由的唯一输入。"""

    conflict_structure: bool = False
    temporal_bounds: bool = False
    numeric_arithmetic: bool = False
    quantifiers: bool = False
    discrete_combinatorial: bool = False
    bounded_arithmetic_theory: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_structure": self.conflict_structure,
            "temporal_bounds": self.temporal_bounds,
            "numeric_arithmetic": self.numeric_arithmetic,
            "quantifiers": self.quantifiers,
            "discrete_combinatorial": self.discrete_combinatorial,
            "bounded_arithmetic_theory": self.bounded_arithmetic_theory,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProblemFeatures":
        if not isinstance(payload, Mapping):
            raise BackendError("MISSING_REQUIRED_FIELD", "features")
        allowed = {
            "conflict_structure", "temporal_bounds", "numeric_arithmetic",
            "quantifiers", "discrete_combinatorial", "bounded_arithmetic_theory",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise BackendError("UNKNOWN_FIELD", ", ".join(unknown))
        values = {}
        for key in allowed:
            value = payload.get(key, False)
            if not isinstance(value, bool):
                raise BackendError("INVALID_ENUM", f"{key} must be bool")
            values[key] = value
        return cls(**values)


def route_backend(features: ProblemFeatures) -> dict[str, Any]:
    """按 typed capability、复杂度和 proof obligation 选择后端。

    选择原则：后端能力全部实现；单次任务只选与其语义需求匹配的后端，
    避免无意义求解成本。路由决策完全由 features 决定（可解释 receipt）。
    """

    if features.discrete_combinatorial:
        backend = "asp"
        rationale = "discrete combinatorial / stable-model requirement"
    elif features.bounded_arithmetic_theory or features.quantifiers:
        backend = "smt"
        rationale = "bounded arithmetic / temporal / consistency obligations"
    elif features.conflict_structure:
        backend = "argumentation"
        rationale = "conflict structure requires grounded semantics"
    elif features.temporal_bounds or features.numeric_arithmetic:
        backend = "closed_form_temporal_numeric"
        rationale = "exact closed-form temporal/numeric evaluation"
    else:
        backend = "deterministic_horn"
        rationale = "conflict-free horn evaluation"

    return {
        "backend": backend,
        "features": features.to_dict(),
        "rationale": rationale,
        "receipt_digest": jcs_digest({
            "backend": backend,
            "features": features.to_dict(),
            "rationale": rationale,
        }),
    }


def require_integer_money(value: Any, *, currency: str) -> int:
    """金额必须是最小货币单位整数；binary float 一律拒绝。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise BackendError("BINARY_FLOAT_FORBIDDEN", f"money value {value!r} ({currency})")
    if not currency or not currency.strip():
        raise BackendError("MISSING_REQUIRED_FIELD", "currency")
    return value


def require_rational_ratio(value: Any, name: str) -> Fraction:
    """比例/利率使用有理数；float 拒绝。"""

    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(item, int) for item in value):
        if value[1] == 0:
            raise BackendError("INVALID_RATIO", name)
        return Fraction(value[0], value[1])
    raise BackendError("BINARY_FLOAT_FORBIDDEN", f"ratio {name}={value!r}")


def add_period_days(start: date, days: int, *, boundary_inclusive: bool, calendar_kind: str = "gregorian") -> date:
    """精确闭式期间计算；边界包含性进入结果语义。

    boundary_inclusive=True：届满日为 start + days（含当日）。
    boundary_inclusive=False：届满日为 start + days 的次日零点起失效，
    这里返回最后有效日（start + days - 1）。
    """

    if calendar_kind != "gregorian":
        raise BackendError("UNSUPPORTED_CALENDAR", calendar_kind)
    if days < 0:
        raise BackendError("INVALID_PERIOD", str(days))
    if boundary_inclusive:
        return start + timedelta(days=days)
    if days == 0:
        raise BackendError("INVALID_PERIOD", "exclusive boundary requires positive period")
    return start + timedelta(days=days - 1)


def last_day_of_month(year: int, month: int) -> date:
    """闰年/月末边界由封闭日历算术处理。"""

    return date(year, month, _calendar.monthrange(year, month)[1])


@dataclass(frozen=True)
class SolverReceiptV1:
    """一次真实 solver 运行的可复算收据（方案 §11 绑定集）。"""

    solver_kind: str
    solver_version: str
    binary_hash: str
    normalized_problem_hash: str
    options: Mapping[str, Any]
    timeout_ms: int
    seed: int
    resource_limits: Mapping[str, Any]
    result: str
    model_or_unsat_core_hash: str
    stdout_digest: str
    stderr_digest: str
    exit_status: int
    started_at: str
    finished_at: str

    def __post_init__(self) -> None:
        if not self.solver_kind.strip() or not self.solver_version.strip():
            raise BackendError("MISSING_REQUIRED_FIELD", "solver identity")
        for name in ("binary_hash", "normalized_problem_hash", "model_or_unsat_core_hash", "stdout_digest", "stderr_digest"):
            value = getattr(self, name)
            if not _SHA256_RE.fullmatch(value):
                raise BackendError("INVALID_DIGEST", name)
        if self.result not in SOLVER_RESULTS:
            raise BackendError("INVALID_ENUM", f"result={self.result!r}")
        if self.timeout_ms < 0 or not isinstance(self.timeout_ms, int):
            raise BackendError("INVALID_LIMIT", "timeout_ms")
        for name in ("started_at", "finished_at"):
            if not _CANONICAL_TIME_RE.match(getattr(self, name)):
                raise BackendError("NONCANONICAL_TIME", name)
        if self.result in ("SAT", "UNSAT") and self.exit_status != 0:
            # SAT/UNSAT 是 solver 的确定回答；exit 异常时回答不可信。
            raise BackendError("SOLVER_STATUS_INCONSISTENT", self.result)

    @property
    def decision_status(self) -> str:
        """solver 结果到下游状态的映射；UNKNOWN 家族绝不塌缩为 FALSE/PASS。"""

        if self.result == "SAT":
            return "solver_sat"
        if self.result == "UNSAT":
            return "solver_unsat"
        return "blocked_unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "solver_kind": self.solver_kind,
            "solver_version": self.solver_version,
            "binary_hash": self.binary_hash,
            "normalized_problem_hash": self.normalized_problem_hash,
            "options": dict(self.options),
            "timeout_ms": self.timeout_ms,
            "seed": self.seed,
            "resource_limits": dict(self.resource_limits),
            "result": self.result,
            "model_or_unsat_core_hash": self.model_or_unsat_core_hash,
            "stdout_digest": self.stdout_digest,
            "stderr_digest": self.stderr_digest,
            "exit_status": self.exit_status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @property
    def receipt_digest(self) -> str:
        return jcs_digest(self.to_dict())


def receipt_recomputable(receipt: SolverReceiptV1, replayed: SolverReceiptV1) -> bool:
    """同一 normalized problem 在同一 solver identity 下 receipt 可复算。"""

    identity = (receipt.solver_kind, receipt.solver_version, receipt.binary_hash,
                receipt.normalized_problem_hash, receipt.receipt_digest)
    replay_identity = (replayed.solver_kind, replayed.solver_version, replayed.binary_hash,
                       replayed.normalized_problem_hash, replayed.receipt_digest)
    return identity == replay_identity
