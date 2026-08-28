"""Privacy egress adapter tests: closed facts, signature verification, honest
decision wording, candidate/user-assumed facts never admitted."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from privacy_egress_adapter import (  # noqa: E402
    FORBIDDEN_PHRASES,
    PrivacyEgressError,
    decide,
    evaluate,
    load_and_verify,
)


def _make_keys(tmp_path: Path):
    private = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    key_doc = {
        "schema_version": "1.0",
        "key_id": "0123456789abcdef",
        "algorithm": "Ed25519",
        "public_key_b64": pub_b64,
    }
    key_path = tmp_path / "public.json"
    key_path.write_text(json.dumps(key_doc), encoding="utf-8")
    return private, key_path


def _canonical_bytes(document: dict) -> bytes:
    from privacy_egress_adapter import _canonical_bytes as cb

    return cb(document)


def _sign(private, document: dict) -> dict:
    sig = private.sign(_canonical_bytes(document))
    return {
        "algorithm": "Ed25519",
        "key_id": "0123456789abcdef",
        "signature": base64.b64encode(sig).decode(),
    }


def _facts(**overrides) -> dict:
    facts = {
        "RawMaterialRemainedLocal": True,
        "DirectNaturalPersonIdentifiersTransformed": True,
        "MappingStoredLocalOnly": True,
        "MappingExcludedFromExternalBundle": True,
        "MoneyPreserved": True,
        "LegalEventDatesPreserved": True,
        "HumanReviewRequired": False,
        "HumanReviewCompleted": False,
        "CriticalResidualCount": 0,
        "Purpose": "CLOUD_LEGAL_ANALYSIS",
    }
    facts.update(overrides)
    return facts


def _document(tmp_path: Path, private, facts: dict, *, sign=True) -> Path:
    doc = {
        "schema_version": "1.0",
        "matter_id": "matter-001",
        "created_at": "2026-08-29T00:00:00Z",
        "facts": facts,
        "receipt_hash": "sha256:" + "0" * 64,
    }
    if sign:
        doc["signature"] = _sign(private, doc)
    path = tmp_path / "facts.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def keys(tmp_path):
    return _make_keys(tmp_path)


class TestAdmission:
    def test_all_true_facts_allow(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        result = evaluate(doc, key_path)
        assert result["decision"]["decision"] == "ALLOW_EXTERNAL_MODEL_USE"
        assert result["decision"]["formal_result_claimed"] is False
        assert result["scope"] == "REVIEW_ONLY"  # production runtime absent: no formal claim

    def test_human_review_required(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts(HumanReviewRequired=True))
        result = evaluate(doc, key_path)
        assert result["decision"]["decision"] == "REQUIRE_HUMAN_REVIEW"

    def test_human_review_completed_ready_by_human(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(
            tmp_path, private, _facts(HumanReviewRequired=True, HumanReviewCompleted=True)
        )
        result = evaluate(doc, key_path)
        assert result["decision"]["decision"] == "ALLOW_EXTERNAL_MODEL_USE"

    def test_false_invariant_blocks(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts(MoneyPreserved=False))
        result = evaluate(doc, key_path)
        assert result["decision"]["decision"] == "CLOSED_BLOCK"

    def test_residual_blocks(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts(CriticalResidualCount=1))
        result = evaluate(doc, key_path)
        assert result["decision"]["decision"] == "CLOSED_BLOCK"


class TestFailClosed:
    def test_bad_signature_closed(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        payload = json.loads(doc.read_text(encoding="utf-8"))
        raw = bytearray(base64.b64decode(payload["signature"]["signature"]))
        raw[0] ^= 0xFF
        payload["signature"]["signature"] = base64.b64encode(bytes(raw)).decode()
        doc.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PrivacyEgressError, match="SIGNATURE_INVALID"):
            load_and_verify(doc, key_path)

    def test_unknown_signer_closed(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        # a different trust anchor must not accept the same document
        (tmp_path / "other").mkdir(exist_ok=True)
        _other_private, other_key = _make_keys(tmp_path / "other")
        with pytest.raises(PrivacyEgressError, match="SIGNATURE_INVALID"):
            load_and_verify(doc, other_key)

    def test_missing_fact_closed(self, tmp_path, keys):
        private, key_path = keys
        facts = _facts()
        del facts["MoneyPreserved"]
        doc = _document(tmp_path, private, facts)
        with pytest.raises(PrivacyEgressError, match="MISSING_FACT"):
            load_and_verify(doc, key_path)

    def test_unknown_fact_field_closed(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        payload = json.loads(doc.read_text(encoding="utf-8"))
        payload["facts"]["UserClaimsFullyAnonymous"] = True  # user self-claim
        payload.pop("signature")
        payload["signature"] = _sign(private, payload)
        doc.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(PrivacyEgressError, match="UNKNOWN_FACT"):
            load_and_verify(doc, key_path)

    def test_tampered_facts_closed(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        payload = json.loads(doc.read_text(encoding="utf-8"))
        payload["facts"]["MoneyPreserved"] = True  # unchanged value, new doc
        payload["facts"]["Purpose"] = "OTHER_PURPOSE"
        payload.pop("signature")
        payload["signature"] = _sign(private, payload)
        doc.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(PrivacyEgressError, match="PURPOSE"):
            load_and_verify(doc, key_path)


class TestWording:
    def test_no_forbidden_phrases(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        result = evaluate(doc, key_path)
        text = json.dumps(result, ensure_ascii=False)
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text

    def test_no_formal_result_claimed(self, tmp_path, keys):
        private, key_path = keys
        doc = _document(tmp_path, private, _facts())
        result = evaluate(doc, key_path)
        assert result["decision"]["formal_result_claimed"] is False
