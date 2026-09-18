"""Production pricing core (Z-v1-default).

Restored scope per mother plan §3.3.1/§3.3.2: the v1.0.3 baseline
(``legalos_services`` at tag ``c2acea3589d14f25f5b8285117ce01276e87860b``,
extracted to ``.local/pricing-baseline/<pin>/``) supplies the historical
constants and legacy branches; this module is the new production home and
does not revive the old platform or a second reasoner.

Frozen behaviors:

- ``BillingTier`` constants (partner 1.8 / senior 1.3 / associate 1.0 /
  paralegal 0.5) are the historical ``Billable Hours`` lever vector. The
  historical H vector is a billable-hours multiplier that was never wired
  into the price formula; production keeps the field and the history on
  display but does not multiply it in (``h_policy="unwired-v1"``).
- Single-case multi-factor estimate: ``effective_nodes × alpha ×
  location_factor × stage_factor + overhead_hours``, batch decay
  ``batch_position ** -0.65`` applied to the variable part only.
- Money is integer minor (cents) with ROUND_HALF_UP applied to the
  unrounded hours × rate product — never to the displayed 0.1h figure.
- ``guarantee_level`` and ``delta`` do not exist and stay ``None``; no
  sourced 0.92 fallback is adopted.
- Legacy baseline comparisons are labeled ``model_version="v1.0.3-baseline"``
  and never mix into ``Z-v1-default`` receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext

D = Decimal

MODEL_VERSION_Z_V1 = "Z-v1-default"
H_POLICY_UNWIRED_V1 = "unwired-v1"
BASELINE_MODEL_VERSION = "v1.0.3-baseline"
FACTOR_SET_ZH_DEFAULT = "zh-default/1"


def canonical_decimal_text(value: Decimal) -> str:
    """Canonical decimal text: plain notation, no exponent, no trailing zeros.

    This is the JC-side realization of the frozen ``DecimalText`` wire type
    (registered in the 0b freeze): integers render without a decimal point,
    fractions render with the shortest exact decimal expansion, no scientific
    notation, no plus sign, ``0``/``-0`` collapse to ``"0"``.
    """

    if not isinstance(value, Decimal):
        raise ValueError("decimal_text_requires_decimal")
    if value == 0:
        return "0"
    normalized = value.normalize()
    sign, digits, exponent = normalized.as_tuple()
    if exponent > 0:
        normalized = normalized.quantize(D(1))
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def decimal_text(value: str) -> Decimal:
    """Parse canonical decimal text produced by :func:`canonical_decimal_text`."""

    try:
        parsed = D(str(value))
    except Exception as error:  # noqa: BLE001 - typed error below
        raise ValueError(f"decimal_text_invalid:{value!r}") from error
    if canonical_decimal_text(parsed) != str(value):
        raise ValueError(f"decimal_text_not_canonical:{value!r}")
    return parsed


@dataclass(frozen=True)
class BillingTier:
    """Historical v1.0.3 billable-hours tier vector (display only)."""

    partner: Decimal = D("1.8")
    senior_associate: Decimal = D("1.3")
    associate: Decimal = D("1.0")
    paralegal: Decimal = D("0.5")


def _to_decimal(value: str | Decimal, field: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        parsed = D(str(value))
    except Exception as error:  # noqa: BLE001 - typed error below
        raise ValueError(f"pricing_decimal_invalid:{field}") from error
    return parsed


def estimate_default(
    *,
    effective_nodes: int,
    alpha: str,
    location_factor: str,
    stage_factor: str,
    overhead_hours: str,
    batch_position: int,
    rate_minor: int,
    alpha_status: str,
    factor_set_version: str = FACTOR_SET_ZH_DEFAULT,
) -> dict[str, object]:
    """One Z-v1-default estimate. Amounts are integer minor, half-up."""
    if effective_nodes < 0 or batch_position < 1 or rate_minor < 0:
        raise ValueError("pricing_input_out_of_range")

    with localcontext() as context:
        context.prec = 40
        a = _to_decimal(alpha, "alpha")
        location = _to_decimal(location_factor, "location_factor")
        stage = _to_decimal(stage_factor, "stage_factor")
        overhead = _to_decimal(overhead_hours, "overhead_hours")
        if min(a, location, stage) <= 0 or overhead < 0:
            raise ValueError("pricing_factor_out_of_range")

        decay = D(batch_position) ** D("-0.65")
        variable = D(effective_nodes) * a * location * stage * decay
        total = variable + overhead
        variable_minor = int(
            (variable * D(rate_minor)).quantize(D(1), rounding=ROUND_HALF_UP)
        )
        total_minor = int(
            (total * D(rate_minor)).quantize(D(1), rounding=ROUND_HALF_UP)
        )
        return {
            "model_version": MODEL_VERSION_Z_V1,
            "factor_set_version": factor_set_version,
            "h_policy": H_POLICY_UNWIRED_V1,
            "variable_hours_unrounded": canonical_decimal_text(variable),
            "overhead_hours_unrounded": canonical_decimal_text(overhead),
            "total_hours_unrounded": canonical_decimal_text(total),
            "display_hours": canonical_decimal_text(
                total.quantize(D("0.1"), rounding=ROUND_HALF_UP)
            ),
            "variable_amount_minor": variable_minor,
            "overhead_amount_minor": total_minor - variable_minor,
            "amount_minor": total_minor,
            "decay_factor": canonical_decimal_text(decay),
            "calibration_status": alpha_status,
            "guarantee_level": None,
            "delta": None,
        }


def estimate_legacy_baseline(
    *,
    effective_nodes: int,
    alpha: str,
    location_factor: str,
    stage_factor: str,
    overhead_hours: str,
    rate_minor: int,
) -> dict[str, object]:
    """v1.0.3 historical comparison: single case, no batch decay.

    The legacy engine dropped the batch factor entirely (positions after
    the first reused the first-case hours); this comparison branch exists
    only to document that behavior against the production default and is
    never used for new quotes.
    """

    with localcontext() as context:
        context.prec = 40
        variable = (
            D(effective_nodes)
            * _to_decimal(alpha, "alpha")
            * _to_decimal(location_factor, "location_factor")
            * _to_decimal(stage_factor, "stage_factor")
        )
        overhead = _to_decimal(overhead_hours, "overhead_hours")
        total = variable + overhead
        return {
            "model_version": BASELINE_MODEL_VERSION,
            "h_policy": H_POLICY_UNWIRED_V1,
            "variable_hours_unrounded": canonical_decimal_text(variable),
            "total_hours_unrounded": canonical_decimal_text(total),
            "display_hours": canonical_decimal_text(
                total.quantize(D("0.1"), rounding=ROUND_HALF_UP)
            ),
            "amount_minor": int(
                (total * D(rate_minor)).quantize(D(1), rounding=ROUND_HALF_UP)
            ),
            "guarantee_level": None,
            "delta": None,
        }


# ---------------------------------------------------------------------------
# Calibration (mother plan §3.3.3). Feature definitions and the estimator are
# versioned separately; one alpha never crosses feature definitions.
# ---------------------------------------------------------------------------

FEATURE_DEFINITION_RAW_COUNT = "facts-claims-raw-count/1"
FEATURE_DEFINITION_LEGACY_DTH = "legacy-dth-explicit/1"
ESTIMATOR_VERSION = "theilsen-legacy-branches/1"
ALPHA_CLAMP_LOW = D("0.05")
ALPHA_CLAMP_HIGH = D("2.0")
INSUFFICIENT_SAMPLES_ALPHA = D("1.0")
MIN_FIT_SAMPLES = 3


@dataclass(frozen=True)
class CalibrationSample:
    """One time-entry observation offered to the estimator.

    ``durationSeconds`` feeds the fit as ``durationSeconds / 3600`` exactly
    (Decimal, context precision 40); the 0.1h display quantum is presentation
    only. Old records that only carry 0.1h precision declare
    ``sourceResolutionSeconds=360`` and are never passed off as second-level.
    """

    entry_ref: str
    feature_definition_version: str
    duration_seconds: int
    effective_nodes: int
    attributed: bool = True
    source_resolution_seconds: int = 1


def fit_alpha(
    samples: list[CalibrationSample],
    *,
    feature_definition_version: str,
) -> dict[str, object]:
    """Fit one alpha with the retained legacy Theil-Sen branches.

    Frozen estimator branches (mother plan §3.3.3):

    - pairwise slopes over distinct node counts, upper median;
    - a negative median slope is gated through ``abs`` (preserved legacy
      branch, not silently rejected);
    - the result is clamped to ``[0.05, 2.0]`` at the frozen precision;
    - fewer than three samples keep the median candidate but production
      uses ``alpha=1.0`` with status ``insufficient_data``;
    - no sourced 0.92 fallback, no delta — the snapshot carries
      ``guaranteeLevel=None`` and ``delta=None``;
    - unattributed entries are excluded from the fit with a recorded reason;
    - samples from another feature definition are rejected outright (one
      alpha never crosses feature definitions).
    """

    with localcontext() as context:
        context.prec = 40
        excluded: list[dict[str, str]] = []
        kept: list[tuple[Decimal, Decimal]] = []
        for sample in samples:
            if sample.feature_definition_version != feature_definition_version:
                raise ValueError(
                    "calibration_feature_version_mismatch:"
                    f"{sample.entry_ref}"
                )
            if sample.duration_seconds % sample.source_resolution_seconds:
                raise ValueError(
                    f"calibration_resolution_mismatch:{sample.entry_ref}"
                )
            if not sample.attributed:
                excluded.append({
                    "entryRef": sample.entry_ref,
                    "reason": "unattributed_seconds",
                })
                continue
            if sample.effective_nodes <= 0 or sample.duration_seconds <= 0:
                excluded.append({
                    "entryRef": sample.entry_ref,
                    "reason": "non_positive_observation",
                })
                continue
            kept.append((
                D(sample.effective_nodes),
                D(sample.duration_seconds) / D(3600),
            ))

        used = len(kept)
        candidate: Decimal | None = None
        if used >= 2:
            slopes: list[Decimal] = []
            for i in range(used):
                for j in range(i + 1, used):
                    delta_nodes = kept[j][0] - kept[i][0]
                    if delta_nodes == 0:
                        continue
                    slopes.append((kept[j][1] - kept[i][1]) / delta_nodes)
            if slopes:
                slopes.sort()
                candidate = slopes[len(slopes) // 2]

        if used < MIN_FIT_SAMPLES or candidate is None:
            return {
                "feature_definition_version": feature_definition_version,
                "estimator_version": ESTIMATOR_VERSION,
                "alpha": canonical_decimal_text(INSUFFICIENT_SAMPLES_ALPHA),
                "candidate_alpha": (
                    canonical_decimal_text(candidate)
                    if candidate is not None and candidate > 0 else None
                ),
                "status": "insufficient_data",
                "samples_used": used,
                "excluded": excluded,
                "guarantee_level": None,
                "delta": None,
            }

        # Legacy branch: a negative slope is gated through abs, not dropped.
        if candidate < 0:
            candidate = -candidate
        clamped = min(max(candidate, ALPHA_CLAMP_LOW), ALPHA_CLAMP_HIGH)
        status = "fitted"
        return {
            "feature_definition_version": feature_definition_version,
            "estimator_version": ESTIMATOR_VERSION,
            "alpha": canonical_decimal_text(clamped),
            "candidate_alpha": canonical_decimal_text(clamped),
            "status": status,
            "samples_used": used,
            "excluded": excluded,
            "guarantee_level": None,
            "delta": None,
        }
