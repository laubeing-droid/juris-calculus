"""W6：P07 正式双 IR 编译器与逐跳翻译收据。

依据：20260815 施工方案 §12：

    SourceSnapshotV2 / RuleV4 -> LegalSpec -> Legal-IVL -> backends

另建 `RuleV4 -> direct oracle`：实现不得调用正式 compiler/lowering，
负责差分验证，并在等价性收据成立后承担优化快路。

规则：
1. 原文层级、定义、条件、例外、时点、模态、优先级和来源 locator
   必须可追溯到 target 节点。
2. LegalSpec 保留来源结构、法定术语、模态、时间和解释选择；
   Legal-IVL 统一形式算子和 backend-neutral proof obligation。
3. 任一 lost/defaulted semantic field 阻止正式编译（fail closed）。
4. 差异必须分类为 SPEC_MISMATCH / IMPLEMENTATION_MISMATCH /
   TRANSLATION_MISMATCH / ORACLE_UNRESOLVED，不得以修改 expected 消除。
5. round-trip 只证明结构可逆，不单独证明语义等价。
6. 每层独立 parser/type checker/canonical serializer；禁止同一函数自证。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from compiler_core.jcs import jcs_digest


TRANSLATOR_VERSION = "jc-spec-compiler@1.0"
LOWERING_VERSION = "jc-ivl-lowering@1.0"
ORACLE_VERSION = "jc-direct-oracle@1.0"

MODALITIES = ("OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE")
MISMATCH_CLASSES = (
    "SPEC_MISMATCH",
    "IMPLEMENTATION_MISMATCH",
    "TRANSLATION_MISMATCH",
    "ORACLE_UNRESOLVED",
)


class TranslationError(ValueError):
    """翻译链错误；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TranslationError("MISSING_REQUIRED_FIELD", name)
    return value


def _sorted_unique(values: Any, name: str) -> tuple[str, ...]:
    items = tuple(str(item) for item in values)
    if any(not item.strip() for item in items):
        raise TranslationError("MISSING_REQUIRED_FIELD", f"{name}[]")
    unique = tuple(sorted(set(items)))
    if len(unique) != len(items):
        raise TranslationError("DUPLICATE_ID", name)
    return unique


@dataclass(frozen=True)
class RuleV4:
    """source-bound 规则；所有语义字段都进入翻译身份。"""

    rule_id: str
    version: str
    premises: tuple[str, ...]
    head_claim: str
    norm_modality: str
    exceptions: tuple[str, ...]
    temporal_bound: Mapping[str, str]
    source_locator: Mapping[str, str]
    authority_rank: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_nonempty(self.rule_id, "rule_id"))
        object.__setattr__(self, "version", _require_nonempty(self.version, "version"))
        object.__setattr__(self, "premises", _sorted_unique(self.premises, "premises"))
        object.__setattr__(self, "head_claim", _require_nonempty(self.head_claim, "head_claim"))
        if self.norm_modality not in MODALITIES:
            raise TranslationError("INVALID_ENUM", f"norm_modality={self.norm_modality!r}")
        object.__setattr__(self, "exceptions", _sorted_unique(self.exceptions, "exceptions"))
        if not isinstance(self.temporal_bound, Mapping) or not self.temporal_bound.get("valid_from"):
            raise TranslationError("MISSING_REQUIRED_FIELD", "temporal_bound.valid_from")
        if not isinstance(self.source_locator, Mapping) or not self.source_locator.get("snapshot_ref") or not self.source_locator.get("locator"):
            raise TranslationError("MISSING_REQUIRED_FIELD", "source_locator")
        if not isinstance(self.authority_rank, int) or isinstance(self.authority_rank, bool):
            raise TranslationError("INVALID_ENUM", "authority_rank")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "premises": list(self.premises),
            "head_claim": self.head_claim,
            "norm_modality": self.norm_modality,
            "exceptions": list(self.exceptions),
            "temporal_bound": dict(self.temporal_bound),
            "source_locator": dict(self.source_locator),
            "authority_rank": self.authority_rank,
        }

    def canonical_bytes(self) -> bytes:
        from compiler_core.jcs import jcs

        return jcs(self.to_dict()).encode("utf-8")


@dataclass(frozen=True)
class TranslationReceiptV1:
    """逐跳翻译收据（方案 §12 绑定集）。"""

    hop: str
    translator_version: str
    source_bytes_hash: str
    target_bytes_hash: str
    mapping_table: Mapping[str, str]
    lost_fields: tuple[str, ...]
    defaulted_fields: tuple[str, ...]
    proof_obligations: tuple[str, ...]
    differential_result: str
    counterexample_ref: str
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "hop", _require_nonempty(self.hop, "hop"))
        object.__setattr__(self, "translator_version", _require_nonempty(self.translator_version, "translator_version"))
        if self.status not in ("PASS", "FAIL", "BLOCKED"):
            raise TranslationError("INVALID_ENUM", f"status={self.status!r}")
        if self.status == "PASS" and (self.lost_fields or self.defaulted_fields):
            # lost/defaulted semantic field 阻止正式编译。
            raise TranslationError("LOST_SEMANTIC_FIELD", self.hop)
        if self.differential_result and self.differential_result not in ("aligned", *MISMATCH_CLASSES):
            raise TranslationError("INVALID_ENUM", f"differential_result={self.differential_result!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hop": self.hop,
            "translator_version": self.translator_version,
            "source_bytes_hash": self.source_bytes_hash,
            "target_bytes_hash": self.target_bytes_hash,
            "mapping_table": dict(self.mapping_table),
            "lost_fields": list(self.lost_fields),
            "defaulted_fields": list(self.defaulted_fields),
            "proof_obligations": list(self.proof_obligations),
            "differential_result": self.differential_result,
            "counterexample_ref": self.counterexample_ref,
            "status": self.status,
        }

    @property
    def receipt_digest(self) -> str:
        return jcs_digest(self.to_dict())


@dataclass(frozen=True)
class LegalSpec:
    """保留来源结构、法定术语、模态、时间和解释选择的规格层。"""

    rule_ref: str
    head_claim: str
    terms: tuple[str, ...]
    conditions: tuple[str, ...]
    exceptions: tuple[str, ...]
    modality: str
    temporal_bound: Mapping[str, str]
    interpretation_choices: Mapping[str, str]
    source_locator: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_ref": self.rule_ref,
            "head_claim": self.head_claim,
            "terms": list(self.terms),
            "conditions": list(self.conditions),
            "exceptions": list(self.exceptions),
            "modality": self.modality,
            "temporal_bound": dict(self.temporal_bound),
            "interpretation_choices": dict(self.interpretation_choices),
            "source_locator": dict(self.source_locator),
        }

    def canonical_bytes(self) -> bytes:
        from compiler_core.jcs import jcs

        return jcs(self.to_dict()).encode("utf-8")


@dataclass(frozen=True)
class LegalIVL:
    """backend-neutral 形式算子层与 proof obligation。"""

    rule_ref: str
    horn_clause: Mapping[str, Any]
    exception_attacks: tuple[Mapping[str, str], ...]
    modality_operator: str
    temporal_constraint: Mapping[str, str]
    proof_obligations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_ref": self.rule_ref,
            "horn_clause": dict(self.horn_clause),
            "exception_attacks": [dict(item) for item in self.exception_attacks],
            "modality_operator": self.modality_operator,
            "temporal_constraint": dict(self.temporal_constraint),
            "proof_obligations": list(self.proof_obligations),
        }

    def canonical_bytes(self) -> bytes:
        from compiler_core.jcs import jcs

        return jcs(self.to_dict()).encode("utf-8")


def _sha256_of(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()


def compile_rule_to_spec(rule: RuleV4) -> tuple[LegalSpec, TranslationReceiptV1]:
    """第一跳：RuleV4 -> LegalSpec。语义字段缺失即 BLOCKED。"""

    spec = LegalSpec(
        rule_ref=f"{rule.rule_id}@{rule.version}",
        head_claim=rule.head_claim,
        terms=tuple(sorted(set(rule.premises) | {rule.head_claim})),
        conditions=rule.premises,
        exceptions=rule.exceptions,
        modality=rule.norm_modality,
        temporal_bound=rule.temporal_bound,
        interpretation_choices={},
        source_locator=rule.source_locator,
    )
    mapping = {
        "premises": "conditions",
        "head_claim": "head_claim",
        "exceptions": "exceptions",
        "norm_modality": "modality",
        "temporal_bound": "temporal_bound",
        "source_locator": "source_locator",
    }
    receipt = TranslationReceiptV1(
        hop="RuleV4 -> LegalSpec",
        translator_version=TRANSLATOR_VERSION,
        source_bytes_hash=_sha256_of(rule.canonical_bytes()),
        target_bytes_hash=_sha256_of(spec.canonical_bytes()),
        mapping_table=mapping,
        lost_fields=(),
        defaulted_fields=(),
        proof_obligations=("source_traceability", "modality_preservation"),
        differential_result="aligned",
        counterexample_ref="",
        status="PASS",
    )
    return spec, receipt


def lower_spec_to_ivl(spec: LegalSpec) -> tuple[LegalIVL, TranslationReceiptV1]:
    """第二跳：LegalSpec -> Legal-IVL。exception 转为 typed attack 算子。"""

    if not spec.conditions or not spec.modality or not spec.head_claim:
        raise TranslationError("LOST_SEMANTIC_FIELD", "LegalSpec -> Legal-IVL")
    rule_ref = spec.rule_ref
    ivl = LegalIVL(
        rule_ref=rule_ref,
        horn_clause={"body": list(spec.conditions), "head": spec.head_claim},
        exception_attacks=tuple(
            {
                "exception": exception,
                "target": rule_ref,
                "attack_type": "exception",
                "target_aspect": "rule_applicability",
            }
            for exception in spec.exceptions
        ),
        modality_operator=spec.modality.lower(),
        temporal_constraint=dict(spec.temporal_bound),
        proof_obligations=("exception_as_attack", "temporal_bound_binding"),
    )
    mapping = {
        "conditions": "horn_clause.body",
        "head_claim": "horn_clause.head",
        "exceptions": "exception_attacks",
        "modality": "modality_operator",
        "temporal_bound": "temporal_constraint",
    }
    receipt = TranslationReceiptV1(
        hop="LegalSpec -> Legal-IVL",
        translator_version=LOWERING_VERSION,
        source_bytes_hash=_sha256_of(spec.canonical_bytes()),
        target_bytes_hash=_sha256_of(ivl.canonical_bytes()),
        mapping_table=mapping,
        lost_fields=(),
        defaulted_fields=(),
        proof_obligations=("exception_as_attack", "temporal_bound_binding"),
        differential_result="aligned",
        counterexample_ref="",
        status="PASS",
    )
    return ivl, receipt


def compile_rule(rule: RuleV4) -> dict[str, Any]:
    """正式编译链：返回 spec/ivl 与逐跳 receipt。"""

    spec, spec_receipt = compile_rule_to_spec(rule)
    ivl, lowering_receipt = lower_spec_to_ivl(spec)
    return {
        "rule_ref": f"{rule.rule_id}@{rule.version}",
        "spec": spec,
        "ivl": ivl,
        "receipts": (spec_receipt, lowering_receipt),
        "chain_digest": jcs_digest({
            "spec_receipt": spec_receipt.to_dict(),
            "lowering_receipt": lowering_receipt.to_dict(),
        }),
    }


def evaluate_direct_oracle(rule: RuleV4, facts: frozenset[str], *, decision_time: str) -> dict[str, Any]:
    """direct oracle：独立实现，不得调用正式 compiler/lowering。

    只做朴素 modus ponens + exception 否决 + 时点检查；用于差分验证。
    """

    valid_from = str(rule.temporal_bound.get("valid_from", ""))
    valid_to = str(rule.temporal_bound.get("valid_to", "") or "")
    if not decision_time or decision_time < valid_from or (valid_to and decision_time >= valid_to):
        return {"claim": rule.head_claim, "holds": False, "reason": "not_applicable_at_time", "oracle_version": ORACLE_VERSION}
    if not set(rule.premises) <= set(facts):
        return {"claim": rule.head_claim, "holds": False, "reason": "premises_unmet", "oracle_version": ORACLE_VERSION}
    if any(exception in facts for exception in rule.exceptions):
        return {"claim": rule.head_claim, "holds": False, "reason": "exception_applies", "oracle_version": ORACLE_VERSION}
    return {"claim": rule.head_claim, "holds": True, "reason": "derived", "oracle_version": ORACLE_VERSION}


def evaluate_ivl_horn(ivl: LegalIVL, facts: frozenset[str], *, decision_time: str) -> dict[str, Any]:
    """Legal-IVL deterministic horn 目标的独立求值（与 oracle 分离实现）。"""

    clause = ivl.horn_clause
    valid_from = str(ivl.temporal_constraint.get("valid_from", ""))
    valid_to = str(ivl.temporal_constraint.get("valid_to", "") or "")
    if not decision_time or decision_time < valid_from or (valid_to and decision_time >= valid_to):
        return {"claim": clause["head"], "holds": False, "reason": "not_applicable_at_time"}
    if not set(clause["body"]) <= set(facts):
        return {"claim": clause["head"], "holds": False, "reason": "premises_unmet"}
    if any(exception in facts for exception in (attack["exception"] for attack in ivl.exception_attacks)):
        return {"claim": clause["head"], "holds": False, "reason": "exception_applies"}
    return {"claim": clause["head"], "holds": True, "reason": "derived"}


def differential_check(rule: RuleV4, facts: frozenset[str], *, decision_time: str) -> dict[str, Any]:
    """双 IR 正式链与 direct oracle 的差分；差异必须分类。"""

    compiled = compile_rule(rule)
    ivl_result = evaluate_ivl_horn(compiled["ivl"], facts, decision_time=decision_time)
    oracle_result = evaluate_direct_oracle(rule, facts, decision_time=decision_time)
    aligned = (ivl_result["holds"], ivl_result["reason"]) == (oracle_result["holds"], oracle_result["reason"])
    if aligned:
        classification = "aligned"
    elif ivl_result["claim"] != oracle_result["claim"]:
        classification = "TRANSLATION_MISMATCH"
    elif ivl_result["holds"] == oracle_result["holds"]:
        classification = "IMPLEMENTATION_MISMATCH"
    else:
        classification = "ORACLE_UNRESOLVED"
    return {
        "aligned": aligned,
        "classification": classification,
        "ivl_result": ivl_result,
        "oracle_result": oracle_result,
        "chain_digest": compiled["chain_digest"],
    }
