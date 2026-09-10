"""Verify-only two-file delivery checking for the business principal profile.

Production port of the retained LMM reference delivery bundle
(``tools/business_relations/reference/delivery_bundle.py``; and the closed
text grammar of ``reference/business.py`` render/verify_document;
legal-math-modeling @ 88644bc, MIT License).

This module never evaluates: it re-parses the actual txt/JSON bytes against
the sealed run's input and result. A closed grammar rejects extra paragraphs
rather than claiming free-text entailment, and it is NOT a generic
DOCX/PDF/Markdown semantic verifier.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Mapping

from compiler_core.business_root.analytics import Analytics, check_analytics
from compiler_core.business_root.checker import check
from compiler_core.business_root.codec import (
    BUSINESS_REQUIREMENT_V1,
    BusinessContextKey,
    BusinessRootError,
    closed_keys,
    exact_rational,
)
from compiler_core.business_root.solver import Outcome, Result
from compiler_core.business_root.spec import (
    PrincipalSpec,
    decode_model,
    decode_world,
    encode_world,
)

SCHEMA = "br/reference-two-file-delivery/1"
REQUIREMENT = BUSINESS_REQUIREMENT_V1
FILES = ("conditional_principal.txt", "calculation.json")
SCOPE = "SYNTHETIC_CONDITIONAL_MODEL_NOT_LITIGATION_FORECAST"
NOTICE = (
    "本文件只核对已选合成模型的条件本金、概率和行动格；"
    "不构成事实认定、机构批准、真实胜率校准或任意法律业务验收。"
)
WARNING = "本文件为明确假设下的条件计算，不表示法院认定、真实胜率或最终返还请求已经成立。"
FOOTER = "范围仅限本输入指定的本金余额；利息、其他抗辩、法律审核和实际裁判另行处理。"


# ---------------------------------------------------------------------------
# Protected text projection and its closed readback.
# ---------------------------------------------------------------------------


def _wire(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else (
        f"{value.numerator}/{value.denominator}"
    )


def render_document(spec: PrincipalSpec, result: Result) -> str:
    if not check(spec, result):
        raise BusinessRootError(
            "UNCHECKED_RESULT", "rendering requires an independently checked result",
            stage="delivery",
        )
    lines = [
        "# 条件性本金分析",
        WARNING,
        "案件：" + _json_text(spec.context.request),
        "争点：" + _json_text(spec.context.issue),
        "权利人：" + _json_text(spec.creditor),
        "义务人：" + _json_text(spec.debtor),
        "债项：" + _json_text(spec.debt_id),
        "依据：" + _json_text([source.source_id for source in spec.sources]),
        "到期日：" + spec.due_day.isoformat(),
        "观察日：" + spec.asof_day.isoformat(),
        "假设：" + _json_text(list(spec.context.assumptions)),
        "共同语境：" + spec.context.canonical_json(),
        "结论状态：" + result.mode,
    ]
    for outcome in result.outcomes:
        lines.append(
            "情景：" + _json_text(dict(outcome.world))
            + "；本金余额：" + _wire(outcome.principal_balance)
            + " 元；超付残差：" + _wire(outcome.overpayment_residual)
            + " 元；性质：条件计算"
        )
    for world in result.pending:
        lines.append("待求情景：" + _json_text(dict(world)))
    lines.append(FOOTER)
    return "\n".join(lines) + "\n"


def _json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load_unique(text: str) -> object:
    def pairs(items):
        decoded = {}
        for key, value in items:
            if key in decoded:
                raise ValueError("DUPLICATE_JSON_KEY")
            decoded[key] = value
        return decoded

    return json.loads(text, object_pairs_hook=pairs)


def verify_document(spec: PrincipalSpec, result: Result, text: object) -> bool:
    """Read the actual UTF-8 text; no reliance on an invisible sidecar."""

    if not check(spec, result) or type(text) is not str:
        return False
    try:
        lines = text.splitlines()
        if len(lines) < 14 or lines[0] != "# 条件性本金分析" or lines[1] != WARNING or (
            lines[-1] != FOOTER
        ):
            return False
        labels = (
            "案件", "争点", "权利人", "义务人", "债项", "依据", "到期日", "观察日",
            "假设", "共同语境", "结论状态",
        )
        observed = {}
        for line, key in zip(lines[2:13], labels):
            prefix = key + "："
            if not line.startswith(prefix):
                return False
            observed[key] = line[len(prefix):]
        if tuple(
            _load_unique(observed[key]) for key in labels[:5]
        ) != (spec.context.request, spec.context.issue, spec.creditor, spec.debtor,
              spec.debt_id):
            return False
        if _load_unique(observed["依据"]) != [
            source.source_id for source in spec.sources
        ]:
            return False
        if observed["到期日"] != spec.due_day.isoformat() or observed["观察日"] != (
            spec.asof_day.isoformat()
        ):
            return False
        if _load_unique(observed["假设"]) != list(spec.context.assumptions):
            return False
        if BusinessContextKey.from_json(observed["共同语境"]) != spec.context or (
            observed["结论状态"]
        ) != result.mode:
            return False
        got, pending = [], []
        for line in lines[13:-1]:
            if line.startswith("待求情景："):
                world = _load_unique(line[len("待求情景："):])
                if type(world) is not dict or any(
                    type(value) is not bool for value in world.values()
                ):
                    return False
                pending.append(tuple(sorted(world.items())))
                continue
            match = _SCENARIO_LINE.fullmatch(line)
            if match is None:
                return False
            world = _load_unique(match[1])
            if type(world) is not dict or any(
                type(value) is not bool for value in world.values()
            ):
                return False
            got.append((tuple(sorted(world.items())), Fraction(match[2]),
                        Fraction(match[3])))
        expected = [
            (tuple(sorted(outcome.world)), outcome.principal_balance,
             outcome.overpayment_residual)
            for outcome in result.outcomes
        ]
        return sorted(got) == sorted(expected) and sorted(pending) == sorted(
            tuple(sorted(world)) for world in result.pending
        )
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError):
        return False


_SCENARIO_LINE = re.compile(
    r"情景：(.+)；本金余额：(-?\d+(?:/\d+)?) 元；超付残差：(-?\d+(?:/\d+)?) 元；性质：条件计算"
)


# ---------------------------------------------------------------------------
# calculation.json projection and its strict readback.
# ---------------------------------------------------------------------------


def _analytics_wire(row: Analytics) -> dict:
    payload = {}
    for item in fields(row):
        value = getattr(row, item.name)
        if item.name == "context":
            payload[item.name] = value.to_dict()
        elif item.name == "weights":
            payload[item.name] = [
                {"world": encode_world(world), "probability": _wire(weight)}
                for world, weight in value
            ]
        elif item.name in ("legal_options", "mutually_acceptable"):
            payload[item.name] = [_wire(option) for option in value]
        else:
            payload[item.name] = None if value is None else _wire(value)
    return payload


def render_calculation_json(
    spec: PrincipalSpec,
    result: Result,
    model: object,
    analytics: Analytics,
) -> str:
    if not check_analytics(spec, result, model, analytics):
        raise BusinessRootError(
            "UNCHECKED_ANALYTICS", "calculation.json requires checked analytics",
            stage="delivery",
        )
    payload = {
        "schema": SCHEMA,
        "requirement": REQUIREMENT,
        "scope": SCOPE,
        "warning": NOTICE,
        "context": spec.context.to_dict(),
        "principal_document": FILES[0],
        "basis": [
            {
                "source_id": source.source_id,
                "version": source.version,
                "start": source.start,
                "end": source.end,
                "quoted": source.quoted,
            }
            for source in spec.sources
        ],
        "relation": {
            "relation_id": spec.relation_id,
            "creditor": spec.creditor,
            "debtor": spec.debtor,
            "debt_id": spec.debt_id,
            "principal": _wire(spec.principal),
            "due_day": spec.due_day.isoformat(),
            "asof_day": spec.asof_day.isoformat(),
        },
        "result": {
            "mode": result.mode,
            "pending": [encode_world(world) for world in result.pending],
            "outcomes": [
                {
                    "world": encode_world(outcome.world),
                    "principal_balance": _wire(outcome.principal_balance),
                    "overpayment_residual": _wire(outcome.overpayment_residual),
                }
                for outcome in result.outcomes
            ],
        },
        "decision_inputs": {
            "model_version": model.context.model_version,
            "basis": model.basis,
            "weights": [
                {"world": encode_world(world), "probability": _wire(weight)}
                for world, weight in model.weights
            ],
            "threshold": _wire(model.threshold),
            "costs": [_wire(cost) for cost in model.costs],
            "legal_options": [_wire(option) for option in model.legal_options],
        },
        "analytics": _analytics_wire(analytics),
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ) + "\n"


def _reject_constant(_token: str) -> None:
    raise ValueError("NONFINITE_JSON_CONSTANT")


def _unique_pairs(items) -> dict:
    decoded = {}
    for key, value in items:
        if key in decoded:
            raise ValueError("DUPLICATE_JSON_KEY")
        decoded[key] = value
    return decoded


def _rational(value: object) -> Fraction:
    return exact_rational(value, label="calculation field")


def _array(value: object) -> list:
    if type(value) is not list:
        raise ValueError("ARRAY_REQUIRED")
    return value


def verify_calculation_json(
    spec: PrincipalSpec,
    result: Result,
    model: object,
    analytics: Analytics,
    text: object,
) -> bool:
    """Parse actual JSON and reconstruct typed objects. Never renders."""

    try:
        if type(text) is not str or not check_analytics(spec, result, model, analytics):
            return False
        payload = json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
        closed_keys(
            payload,
            {
                "schema", "requirement", "scope", "warning", "context",
                "principal_document", "basis", "relation", "result",
                "decision_inputs", "analytics",
            },
            label="calculation document",
        )
        assert isinstance(payload, dict)
        if (
            payload["schema"], payload["requirement"], payload["scope"],
            payload["warning"], payload["principal_document"],
        ) != (SCHEMA, REQUIREMENT, SCOPE, NOTICE, FILES[0]):
            return False
        context = BusinessContextKey.from_dict(payload["context"])
        if context != spec.context:
            return False
        source_rows = _array(payload["basis"])
        if len(source_rows) != len(spec.sources):
            return False
        for row, source in zip(source_rows, spec.sources):
            closed_keys(
                row, {"source_id", "version", "start", "end", "quoted"},
                label="basis row",
            )
            assert isinstance(row, dict)
            if type(row["start"]) is not int or type(row["end"]) is not int:
                return False
            if (
                row["source_id"], row["version"], row["start"], row["end"],
                row["quoted"],
            ) != (
                source.source_id, source.version, source.start, source.end,
                source.quoted,
            ):
                return False
        relation = closed_keys(
            payload["relation"],
            {
                "relation_id", "creditor", "debtor", "debt_id", "principal",
                "due_day", "asof_day",
            },
            label="relation",
        )
        assert isinstance(relation, dict)
        if (
            relation["relation_id"], relation["creditor"], relation["debtor"],
            relation["debt_id"], _rational(relation["principal"]), relation["due_day"],
            relation["asof_day"],
        ) != (
            spec.relation_id, spec.creditor, spec.debtor, spec.debt_id,
            spec.principal, spec.due_day.isoformat(), spec.asof_day.isoformat(),
        ):
            return False
        result_row = closed_keys(
            payload["result"], {"mode", "pending", "outcomes"}, label="result"
        )
        assert isinstance(result_row, dict)
        outcomes = []
        for row in _array(result_row["outcomes"]):
            closed_keys(
                row, {"world", "principal_balance", "overpayment_residual"},
                label="outcome row",
            )
            assert isinstance(row, dict)
            outcomes.append(Outcome(
                context, spec.relation_id, spec.creditor, spec.debtor, spec.debt_id,
                tuple(source.source_id for source in spec.sources), spec.asof_day,
                decode_world(row["world"]), _rational(row["principal_balance"]),
                _rational(row["overpayment_residual"]),
            ))
        parsed_result = Result(
            context, result_row["mode"], tuple(outcomes),
            tuple(decode_world(world) for world in _array(result_row["pending"])),
        )
        if (
            not check(spec, parsed_result)
            or parsed_result.mode != result.mode
            or frozenset(parsed_result.outcomes) != frozenset(result.outcomes)
            or frozenset(parsed_result.pending) != frozenset(result.pending)
        ):
            return False
        model_row = closed_keys(
            payload["decision_inputs"],
            {
                "model_version", "basis", "weights", "threshold", "costs",
                "legal_options",
            },
            label="decision inputs",
        )
        assert isinstance(model_row, dict)
        if model_row["model_version"] != spec.context.model_version:
            return False
        parsed_model = decode_model(
            {key: value for key, value in model_row.items() if key != "model_version"},
            context,
        )
        if parsed_model != model:
            return False
        analytics_row = closed_keys(
            payload["analytics"], {item.name for item in fields(Analytics)},
            label="analytics",
        )
        assert isinstance(analytics_row, dict)
        values = {}
        for item in fields(Analytics):
            raw = analytics_row[item.name]
            if item.name == "context":
                values[item.name] = BusinessContextKey.from_dict(raw)
            elif item.name == "weights":
                decoded = []
                for entry in _array(raw):
                    closed_keys(entry, {"world", "probability"}, label="weight")
                    assert isinstance(entry, dict)
                    decoded.append((
                        decode_world(entry["world"]), _rational(entry["probability"]),
                    ))
                values[item.name] = tuple(decoded)
            elif item.name in ("legal_options", "mutually_acceptable"):
                values[item.name] = tuple(
                    _rational(option) for option in _array(raw)
                )
            elif item.name == "selected" and raw is None:
                values[item.name] = None
            else:
                values[item.name] = _rational(raw)
        parsed_analytics = Analytics(**values)
        return parsed_analytics == analytics and check_analytics(
            spec, parsed_result, model, parsed_analytics
        )
    except (
        ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError,
        OverflowError,
    ):
        return False


# ---------------------------------------------------------------------------
# The whole two-file verdict over one sealed run's I0 and result.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleVerdict:
    accepted: bool
    status: str
    scope: str
    reason: str
    checked_artifacts: tuple[tuple[str, str], ...] = ()


def check_business_bundle(
    spec: PrincipalSpec,
    result: Result,
    model: object,
    analytics: Analytics | None,
    artifact_bytes: Mapping[str, bytes],
) -> BundleVerdict:
    """Verify both actual files against the run's sealed input and result.

    The caller has already bound the stored I0 (selection ref and content
    check live in the application layer); this function rejects any mismatch
    between the two files, the sealed result, and the model — and it never
    trusts submitter-supplied expected values or checker callbacks.
    """

    def reject(reason: str) -> BundleVerdict:
        return BundleVerdict(False, "REJECT_REFERENCE_BUNDLE", SCOPE, reason)

    try:
        if type(artifact_bytes) is not dict or set(artifact_bytes) != set(FILES):
            return reject("EXACT_ARTIFACT_SET")
        raw = {name: artifact_bytes[name] for name in FILES}
        if any(type(payload) is not bytes for payload in raw.values()):
            return reject("ARTIFACT_BYTES_REQUIRED")
        if not check(spec, result):
            return reject("PRINCIPAL_CHECK")
        if result.mode != "EXACT_FINITE_SCENARIOS":
            return reject("REQUIREMENT_NOT_COMPLETE")
        text = raw[FILES[0]].decode("utf-8", errors="strict")
        calculation = raw[FILES[1]].decode("utf-8", errors="strict")
        if not verify_document(spec, result, text):
            return reject("PRINCIPAL_FILE_READBACK")
        if analytics is None:
            return reject("ANALYTICS_MISSING")
        if not verify_calculation_json(spec, result, model, analytics, calculation):
            return reject("ANALYTICS_FILE_READBACK")
        return BundleVerdict(
            True,
            "ACCEPT_REFERENCE_TWO_FILE_REQUIREMENT",
            SCOPE,
            "Same selected input; both actual file snapshots checked.",
            tuple((name, sha256(raw[name]).hexdigest()) for name in FILES),
        )
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            ZeroDivisionError):
        return reject("INVALID_INPUT_OR_ENCODING")


__all__ = [
    "FILES",
    "NOTICE",
    "REQUIREMENT",
    "SCHEMA",
    "SCOPE",
    "WARNING",
    "BundleVerdict",
    "check_business_bundle",
    "render_calculation_json",
    "render_document",
    "verify_calculation_json",
    "verify_document",
]
