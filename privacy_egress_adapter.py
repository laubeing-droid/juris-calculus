"""Privacy egress consumer adapter: JC side of the anonymizer consumer chain.

JC never reads case files and never sees the mapping. It receives a signed
`jc-privacy-facts-v1` document (closed fields only), verifies the Ed25519
signature against a pinned public key, validates the exact-copy schema, and
emits a review decision with honest wording.

Decision semantics (no weakening of V4 formal semantics; this adapter runs
OUTSIDE the formal kernel and never fabricates a formal accepted result):

- All invariants present and true, HumanReviewRequired false
    -> ALLOW_EXTERNAL_MODEL_USE (声明范围内前置条件已满足)
- Any invariant false / residual count > 0 / missing facts / bad signature
    -> CLOSED_BLOCK
- HumanReviewRequired true and HumanReviewCompleted false, facts otherwise ok
    -> REQUIRE_HUMAN_REVIEW

When the V4 production runtime is not configured (no packs/trust/identity),
formal evaluation cannot run in this environment; the adapter therefore never
claims a formal accepted result and reports REVIEW_ONLY scope instead. That is
recorded as CLOSED_BLOCK_EXTERNAL in the construction status.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "1.0"
ALLOWED_FACT_KEYS = {
    "RawMaterialRemainedLocal", "DirectNaturalPersonIdentifiersTransformed",
    "MappingStoredLocalOnly", "MappingExcludedFromExternalBundle",
    "MoneyPreserved", "LegalEventDatesPreserved", "HumanReviewRequired",
    "HumanReviewCompleted", "CriticalResidualCount", "Purpose",
}
REQUIRED_FACT_KEYS = ALLOWED_FACT_KEYS - {"CriticalResidualCount", "Purpose"}
BOOLEAN_FACT_KEYS = REQUIRED_FACT_KEYS
PURPOSES = {"CLOUD_LEGAL_ANALYSIS"}
REQUIRED_INVARIANTS_TRUE = {
    "RawMaterialRemainedLocal",
    "DirectNaturalPersonIdentifiersTransformed",
    "MappingStoredLocalOnly",
    "MappingExcludedFromExternalBundle",
    "MoneyPreserved",
    "LegalEventDatesPreserved",
}
FORBIDDEN_PHRASES = ("已经完全匿名", "绝无泄露风险", "绝无个人信息泄露",
                     "100% ANONYMIZED", "ZERO RISK")
APPROVAL_PHRASE = "已满足本次声明范围内的去标识化与外发前置条件"
REVIEW_PHRASE = "需要人工复核后方可继续"
BLOCK_PHRASE = "现有事实不足，关闭阻断"


class PrivacyEgressError(ValueError):
    """Fail-closed adapter error."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass
class EgressDecision:
    decision: str  # ALLOW_EXTERNAL_MODEL_USE | REQUIRE_HUMAN_REVIEW | CLOSED_BLOCK
    phrase: str
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": "jc/privacy-egress-decision/1.0",
            "decision": self.decision,
            "statement": self.phrase,
            "reason": self.reason,
            "formal_result_claimed": False,
        }


def _canonical_bytes(document: dict) -> bytes:
    """Canonical bytes identical to the anonymizer's canonical profile."""
    import hashlib

    def canonical(value):
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in sorted(value.items())}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        if isinstance(value, float):
            raise PrivacyEgressError("FACT_VALUE_TYPE", "float is forbidden")
        return value

    return json.dumps(
        canonical(document), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def load_and_verify(document_path: Path, public_key_path: Path) -> dict:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    document = json.loads(Path(document_path).read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise PrivacyEgressError("SCHEMA_VERSION", str(document.get("schema_version")))
    signature = document.get("signature")
    if not isinstance(signature, dict) or "signature" not in signature:
        raise PrivacyEgressError("SIGNATURE_MISSING")
    body = {k: v for k, v in document.items() if k != "signature"}

    key_doc = json.loads(Path(public_key_path).read_text(encoding="utf-8"))
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(key_doc["public_key_b64"])
        )
        pub.verify(base64.b64decode(signature["signature"]), _canonical_bytes(body))
    except (InvalidSignature, Exception) as exc:  # noqa: BLE001
        if isinstance(exc, PrivacyEgressError):
            raise
        raise PrivacyEgressError("SIGNATURE_INVALID") from None

    # closed-field validation (exact-copy schema semantics)
    facts = document.get("facts")
    if not isinstance(facts, dict):
        raise PrivacyEgressError("FACTS_MISSING")
    for key in facts:
        if key not in ALLOWED_FACT_KEYS:
            raise PrivacyEgressError("UNKNOWN_FACT", key)
    for key in REQUIRED_FACT_KEYS:
        if key not in facts:
            raise PrivacyEgressError("MISSING_FACT", key)
    for key in BOOLEAN_FACT_KEYS:
        if not isinstance(facts[key], bool):
            raise PrivacyEgressError("FACT_VALUE_TYPE", key)
    residual = facts.get("CriticalResidualCount")
    if residual is not None and (not isinstance(residual, int) or isinstance(residual, bool) or residual < 0):
        raise PrivacyEgressError("FACT_VALUE_TYPE", "CriticalResidualCount")
    purpose = facts.get("Purpose")
    if purpose is not None and purpose not in PURPOSES:
        raise PrivacyEgressError("PURPOSE", str(purpose))
    return document


def decide(document: dict) -> EgressDecision:
    facts = document["facts"]
    invariants_ok = all(facts[k] for k in REQUIRED_INVARIANTS_TRUE)
    residual = facts.get("CriticalResidualCount", 0)
    if not invariants_ok or (isinstance(residual, int) and residual > 0):
        return EgressDecision("CLOSED_BLOCK", BLOCK_PHRASE,
                              "invariant false or critical residual present")
    if facts["HumanReviewRequired"] and not facts["HumanReviewCompleted"]:
        return EgressDecision("REQUIRE_HUMAN_REVIEW", REVIEW_PHRASE,
                              "human review required and not completed")
    if facts["HumanReviewCompleted"] or not facts["HumanReviewRequired"]:
        return EgressDecision("ALLOW_EXTERNAL_MODEL_USE", APPROVAL_PHRASE)
    return EgressDecision("REQUIRE_HUMAN_REVIEW", REVIEW_PHRASE,
                          "review receipt required for current artifact set")


def evaluate(document_path: Path, public_key_path: Path) -> dict:
    document = load_and_verify(document_path, public_key_path)
    decision = decide(document)
    return {
        "matter_id": document.get("matter_id"),
        "facts_digest": _canonical_bytes(document["facts"]).hex()[:16],
        "decision": decision.to_dict(),
        "scope": "REVIEW_ONLY" if decision.decision != "CLOSED_BLOCK" else "CLOSED_BLOCK",
        "formal_evaluation_attempted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jc-privacy-egress")
    parser.add_argument("--input", required=True, help="jc-privacy-facts-v1 JSON")
    parser.add_argument("--public-key", required=True, help="pinned signer public key JSON")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        result = evaluate(Path(args.input), Path(args.public_key))
    except PrivacyEgressError as exc:
        print(json.dumps({"decision": "CLOSED_BLOCK", "statement": BLOCK_PHRASE,
                          "reason": exc.code}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
