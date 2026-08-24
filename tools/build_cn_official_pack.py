#!/usr/bin/env python3
"""Build a deterministic cn-official candidate from explicit first-party source data."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    ContentRefV4,
    RuleV4,
    SourceSnapshotV4,
)
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    RULE_AUTHORITY_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_CONCLUSION_KIND,
    RULE_DEFINED_TERM_KIND,
    RULE_EXCEPTION_KIND,
    RULE_INTERPRETATION_KIND,
    RULE_KIND,
    RULE_NUMERIC_KIND,
    RULE_PERMISSION_KIND,
    RULE_PREMISE_KIND,
    RULE_PRIORITY_KIND,
    RULE_TEMPORAL_KIND,
    RULE_VARIABLE_KIND,
)
from compiler_core.source_service import (
    SOURCE_NORMALIZATION_PROFILE,
    SOURCE_NORMALIZED_KIND,
    SOURCE_PROVENANCE_KIND,
    SOURCE_RAW_KIND,
    SOURCE_SNAPSHOT_KIND,
    SOURCE_STRUCTURE_MAP_KIND,
    normalize_source_bytes,
    source_snapshot_ref,
)


SOURCE_PATH = ROOT / "tests/fixtures/cn_official/first-method-source.json"
OUTPUT_PATH = ROOT / "tests/fixtures/cn_official/candidate-pack.json"
PACK_ID = "cn-first-method-test-candidate"
OFFICIAL_CANDIDATE_PACK_ID = "cn-official-candidate"
_CANDIDATE_AUTHORITY_TIERS = {
    "constitution", "law", "administrative_regulation", "judicial_interpretation",
    "department_rule", "local_regulation",
}
_CANDIDATE_LICENSE_STATUSES = {
    "official-publication", "public-domain", "permission-recorded",
}
_CANDIDATE_DISTRIBUTION_STATUSES = {"redistributable", "locator-only"}
_SOURCE_FIELDS = {
    "schema_version", "scope", "formal_source_claimed", "source_id",
    "jurisdiction", "authority_tier", "issuer", "title", "canonical_locator",
    "publication_time", "effective_from", "effective_to", "retrieved_at",
    "license_status", "distribution_status", "raw_text", "normative_units",
}
_UNIT_FIELDS = {
    "unit_id", "text", "state", "omission_reason", "modality", "premise",
    "conclusion", "exception", "priority_over", "permission", "temporal",
    "numeric",
}
_MODALITIES = {"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE"}
_BANNED = (
    b"configs/zh_CN/rules.yaml",
    b"cn-legacy-corpus",
    b"032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44",
    b"8f51fdfd1db3e343812e8f35a321418fa854f4f7",
    b"1c43bcc41579820c283eaf3a02ede928b61121aed5a089314a865e204189384d",
    b"21144",
)


class CandidatePackError(ValueError):
    """The test-only source or candidate bundle violates its closed contract."""


def _fail(detail: str) -> None:
    raise CandidatePackError(detail)


def _closed(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"{label} fields are not closed")
    return value


def _time(value: object) -> CanonicalTimeV4 | None:
    return None if value is None else CanonicalTimeV4(str(value))


def _record(
    artifacts: dict[tuple[str, str], dict[str, object]],
    kind: str,
    content: dict[str, object] | list[object] | str,
    *,
    media_type: str = JSON_MEDIA_TYPE,
    scope: str = "test-only",
) -> ContentRefV4:
    raw = content.encode("utf-8") if isinstance(content, str) else canonical_bytes(content)
    reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
    key = (kind, str(reference.digest))
    candidate = {
        "artifact_kind": kind,
        "content_ref": reference.to_dict(),
        "media_type": media_type,
        "scope": scope,
        "content": content,
    }
    existing = artifacts.get(key)
    if existing is not None and existing != candidate:
        _fail(f"artifact collision: {kind}")
    artifacts[key] = candidate
    return reference


def _component(
    artifacts: dict[tuple[str, str], dict[str, object]],
    kind: str,
    rule_id: str,
    **values: object,
) -> ContentRefV4:
    return _record(
        artifacts,
        kind,
        {"schema_version": f"jc/{kind}/1.0", "rule_id": rule_id, **values},
        scope=RULE_COMPONENT_SCOPE,
    )


def _validate_source(document: object) -> tuple[dict[str, Any], bool]:
    source = _closed(document, _SOURCE_FIELDS, "source")
    test_only = source["schema_version"] == "jc/first-method-test-source/1.0"
    if test_only and (
        source["scope"] != "test-only"
        or source["formal_source_claimed"] is not False
        or source["jurisdiction"] != "TEST-CN"
        or source["authority_tier"] != "synthetic_test_only"
        or source["license_status"] != "test-fixture"
        or source["distribution_status"] != "test-only"
    ):
        _fail("source identity or test-only boundary drifted")
    if not test_only and (
        source["schema_version"] != "jc/cn-official-source-candidate/1.0"
        or source["scope"] != "candidate"
        or source["formal_source_claimed"] is not False
        or source["jurisdiction"] != "CN"
        or source["authority_tier"] not in _CANDIDATE_AUTHORITY_TIERS
        or source["license_status"] not in _CANDIDATE_LICENSE_STATUSES
        or source["distribution_status"] not in _CANDIDATE_DISTRIBUTION_STATUSES
    ):
        _fail("source identity or candidate boundary drifted")
    CanonicalLocatorV4.from_dict(source["canonical_locator"])
    publication = _time(source["publication_time"])
    effective_from = _time(source["effective_from"])
    effective_to = _time(source["effective_to"])
    retrieved = _time(source["retrieved_at"])
    if (
        publication is None or effective_from is None or retrieved is None
        or not publication < effective_from
        or effective_to is not None and not effective_from < effective_to
    ):
        _fail("source temporal contract drifted")
    if not isinstance(source["raw_text"], str) or not source["raw_text"].strip():
        _fail("source raw text is empty")
    anchored_text = "".join(source["raw_text"].split())
    units = source["normative_units"]
    if not isinstance(units, list) or len(units) < 2:
        _fail("source normative units are missing")
    ids: list[str] = []
    for raw_unit in units:
        unit = _closed(raw_unit, _UNIT_FIELDS, "normative unit")
        if not isinstance(unit["unit_id"], str) or not unit["unit_id"]:
            _fail("normative unit id is empty")
        ids.append(unit["unit_id"])
        if not isinstance(unit["text"], str) or not unit["text"].strip():
            _fail(f"normative unit text is empty: {unit['unit_id']}")
        if "".join(unit["text"].split()) not in anchored_text:
            _fail(f"normative unit text is not anchored in source: {unit['unit_id']}")
        if unit["state"] == "omitted":
            if not isinstance(unit["omission_reason"], str) or not unit["omission_reason"]:
                _fail(f"omitted unit lacks a reason: {unit['unit_id']}")
            if any(unit[name] is not None for name in (
                "modality", "premise", "conclusion", "exception", "priority_over",
                "permission", "temporal", "numeric",
            )):
                _fail(f"omitted unit contains candidate semantics: {unit['unit_id']}")
            continue
        if (
            unit["state"] != "in_scope"
            or unit["omission_reason"] is not None
            or unit["modality"] not in _MODALITIES
            or not isinstance(unit["premise"], str)
            or not isinstance(unit["conclusion"], str)
        ):
            _fail(f"in-scope unit contract drifted: {unit['unit_id']}")
        if unit["temporal"] is not None:
            temporal = _closed(unit["temporal"], {"start", "end"}, "temporal")
            if not CanonicalTimeV4(str(temporal["start"])) < CanonicalTimeV4(str(temporal["end"])):
                _fail(f"temporal range is invalid: {unit['unit_id']}")
        if unit["numeric"] is not None:
            numeric = _closed(unit["numeric"], {"operator", "value", "unit"}, "numeric")
            if (
                numeric["operator"] not in {"<", "<=", "=", ">=", ">"}
                or not isinstance(numeric["value"], str)
                or not numeric["value"].replace(".", "", 1).isdigit()
                or not isinstance(numeric["unit"], str)
                or not numeric["unit"]
            ):
                _fail(f"numeric constraint is invalid: {unit['unit_id']}")
    if len(ids) != len(set(ids)):
        _fail("normative unit ids are duplicated")
    if any(token in canonical_bytes(source) for token in _BANNED):
        _fail("source depends on a retired corpus identity")
    return source, test_only


def build_document(source_document: object) -> dict[str, object]:
    """Build a deterministic candidate bundle without issuing any approval."""

    source, test_only = _validate_source(source_document)
    artifact_scope = "test-only" if test_only else "candidate"
    coverage_kind = "test-candidate-coverage" if test_only else "candidate-coverage"
    review_kind = (
        "test-candidate-review-subject" if test_only else "candidate-review-subject"
    )
    pack_kind = "test-candidate-pack" if test_only else "candidate-pack"
    pack_id = PACK_ID if test_only else OFFICIAL_CANDIDATE_PACK_ID
    artifacts: dict[tuple[str, str], dict[str, object]] = {}
    raw = source["raw_text"].encode("utf-8")
    normalized = normalize_source_bytes(raw)
    raw_ref = _record(
        artifacts, SOURCE_RAW_KIND, source["raw_text"],
        media_type="text/plain", scope=artifact_scope,
    )
    normalized_ref = _record(
        artifacts,
        SOURCE_NORMALIZED_KIND,
        normalized.decode("utf-8"),
        media_type="text/plain", scope=artifact_scope,
    )
    unit_ids = [item["unit_id"] for item in source["normative_units"]]
    structure_ref = _record(artifacts, SOURCE_STRUCTURE_MAP_KIND, {
        "schema_version": "jc/source-structure/1.0",
        "normative_unit_ids": unit_ids,
    }, scope="source-provenance")
    provenance_ref = _record(artifacts, SOURCE_PROVENANCE_KIND, {
        "schema_version": "jc/source-provenance/1.0",
        "scope": artifact_scope,
        "formal_source_claimed": False,
        "method": (
            "user-authored-first-method-test-fixture"
            if test_only else "explicit-first-party-source-intake"
        ),
    }, scope="source-provenance")
    pending_authenticity_ref = _record(artifacts, "source-authenticity-pending", {
        "schema_version": "jc/source-authenticity-pending/1.0",
        "scope": artifact_scope,
        "status": "NOT_CLAIMED",
    }, scope="source-authenticity")
    snapshot = SourceSnapshotV4(
        source_id=source["source_id"],
        jurisdiction=source["jurisdiction"],
        authority_tier=source["authority_tier"],
        issuer=source["issuer"],
        title=source["title"],
        publication_time=CanonicalTimeV4(source["publication_time"]),
        effective_from=CanonicalTimeV4(source["effective_from"]),
        effective_to=_time(source["effective_to"]),
        retrieved_at=CanonicalTimeV4(source["retrieved_at"]),
        canonical_locator=CanonicalLocatorV4.from_dict(source["canonical_locator"]),
        raw_digest=raw_ref.digest,
        normalization_profile=SOURCE_NORMALIZATION_PROFILE,
        normalized_digest=normalized_ref.digest,
        structure_map_ref=structure_ref,
        authenticity_receipt_ref=pending_authenticity_ref,
        provenance_refs=(provenance_ref,),
        acquisition_method=(
            "user-authored-test-fixture" if test_only else "explicit-source-intake"
        ),
        license_status=source["license_status"],
        distribution_status=source["distribution_status"],
    )
    snapshot_ref = source_snapshot_ref(snapshot)
    if _record(
        artifacts, SOURCE_SNAPSHOT_KIND, snapshot.to_dict(), scope="source-authenticity"
    ) != snapshot_ref:
        _fail("source snapshot reference is not canonical")

    rules: list[RuleV4] = []
    rule_refs: list[ContentRefV4] = []
    omissions: list[dict[str, str]] = []
    for unit in source["normative_units"]:
        if unit["state"] == "omitted":
            omissions.append({
                "unit_id": unit["unit_id"],
                "reason": unit["omission_reason"],
            })
            continue
        rule_id = unit["unit_id"]
        authority_ref = _component(
            artifacts, RULE_AUTHORITY_KIND, rule_id, tier=source["authority_tier"]
        )
        variable_ref = _component(
            artifacts, RULE_VARIABLE_KIND, rule_id, name="test-subject"
        )
        premise_ref = _component(
            artifacts, RULE_PREMISE_KIND, rule_id,
            fact_key=unit["premise"], required=True,
        )
        conclusion_ref = _component(
            artifacts, RULE_CONCLUSION_KIND, rule_id, value=unit["conclusion"]
        )
        interpretation_ref = _component(
            artifacts, RULE_INTERPRETATION_KIND, rule_id,
            choice="literal-test-fixture" if test_only else "candidate-authored",
        )
        term_ref = _component(
            artifacts, RULE_DEFINED_TERM_KIND, rule_id, term="test-subject"
        )
        exception_refs = () if unit["exception"] is None else (_component(
            artifacts, RULE_EXCEPTION_KIND, rule_id,
            attacker=rule_id, target=rule_id, attack_type="exception",
            target_aspect="applicability", condition_fact_key=unit["exception"],
        ),)
        priority_refs = () if unit["priority_over"] is None else (_component(
            artifacts, RULE_PRIORITY_KIND, rule_id,
            source=rule_id, target=unit["priority_over"],
            condition=f"{rule_id}.priority-condition",
        ),)
        permission_ref = None if unit["permission"] is None else _component(
            artifacts, RULE_PERMISSION_KIND, rule_id,
            permission_id=f"{rule_id}.permission", permits=unit["permission"],
            relation_to=rule_id, relation_kind="exception",
        )
        temporal_refs = () if unit["temporal"] is None else (_component(
            artifacts, RULE_TEMPORAL_KIND, rule_id,
            start=unit["temporal"]["start"], end=unit["temporal"]["end"],
            target_rule_id=rule_id,
        ),)
        numeric_refs = () if unit["numeric"] is None else (_component(
            artifacts, RULE_NUMERIC_KIND, rule_id, **unit["numeric"],
        ),)
        body = {
            "rule_id": rule_id,
            "jurisdiction": source["jurisdiction"],
            "governing_law": (
                "fictional-first-method-test-specification"
                if test_only else source["title"]
            ),
            "authority_ref": authority_ref.to_dict(),
            "variable_declaration_refs": [variable_ref.to_dict()],
            "premise_refs": [premise_ref.to_dict()],
            "conclusion_ref": conclusion_ref.to_dict(),
            "modality": unit["modality"],
            "permission_ref": permission_ref.to_dict() if permission_ref else None,
            "exception_refs": [item.to_dict() for item in exception_refs],
            "priority_refs": [item.to_dict() for item in priority_refs],
            "attack_refs": [],
            "temporal_constraint_refs": [item.to_dict() for item in temporal_refs],
            "numeric_constraint_refs": [item.to_dict() for item in numeric_refs],
            "source_snapshot_ref": snapshot_ref.to_dict(),
            "source_locator": snapshot.canonical_locator.to_dict(),
            "source_structure_ref": structure_ref.to_dict(),
            "interpretation_choice_refs": [interpretation_ref.to_dict()],
            "defined_term_refs": [term_ref.to_dict()],
            "promotion_receipt_refs": [],
            "effective_from": snapshot.effective_from.to_dict(),
            "effective_to": (
                {"wire": unit["temporal"]["end"]}
                if unit["temporal"] is not None else None
            ),
        }
        rule = RuleV4.from_dict({**body, "rule_digest": str(digest_value(body))})
        rule_ref = _record(
            artifacts, RULE_KIND, rule.digest_body(), scope=artifact_scope
        )
        if rule_ref.digest != rule.rule_digest:
            _fail(f"rule reference drifted: {rule_id}")
        rules.append(rule)
        rule_refs.append(rule_ref)

    coverage_body = {
        "schema_version": (
            "jc/test-candidate-coverage/1.0"
            if test_only else "jc/candidate-coverage/1.0"
        ),
        "status": "COMPLETE_FOR_TEST_FIXTURE" if test_only else "CANDIDATE_COMPLETE",
        "source_snapshot_ref": snapshot_ref.to_dict(),
        "denominator_unit_ids": unit_ids,
        "candidate_unit_ids": [rule.rule_id for rule in rules],
        "omissions": omissions,
    }
    coverage_ref = _record(
        artifacts, coverage_kind, coverage_body, scope=artifact_scope,
    )
    review_body = {
        "schema_version": (
            "jc/test-candidate-review-subject/1.0"
            if test_only else "jc/candidate-review-subject/1.0"
        ),
        "scope": artifact_scope,
        "status": "AWAITING_EXTERNAL_REVIEW",
        "formal_source_claimed": False,
        "source_snapshot_ref": snapshot_ref.to_dict(),
        "coverage_ref": coverage_ref.to_dict(),
        "rule_subject_digests": [str(rule.promotion_subject_digest()) for rule in rules],
        "required_roles": [
            "legal_reviewer_1", "legal_reviewer_2", "engineering_reviewer",
        ],
    }
    review_ref = _record(artifacts, review_kind, review_body, scope=artifact_scope)
    pack_body = {
        "schema_version": (
            "jc/test-candidate-pack/1.0" if test_only else "jc/candidate-pack/1.0"
        ),
        "pack_id": pack_id,
        "pack_version": "0.0.0-test" if test_only else "0.0.0-candidate",
        "state": "CANDIDATE",
        "scope": artifact_scope,
        "production_allowed": False,
        "formal_source_claimed": False,
        "source_snapshot_ref": snapshot_ref.to_dict(),
        "rule_refs": [item.to_dict() for item in rule_refs],
        "coverage_ref": coverage_ref.to_dict(),
        "review_subject_ref": review_ref.to_dict(),
        "promotion_receipt_refs": [],
        "signature_ref": None,
    }
    pack_ref = _record(artifacts, pack_kind, pack_body, scope=artifact_scope)
    document = {
        "schema_version": (
            "jc/first-method-test-candidate-bundle/1.0"
            if test_only else "jc/cn-official-candidate-bundle/1.0"
        ),
        "scope": artifact_scope,
        "production_allowed": False,
        "formal_source_claimed": False,
        "source": {
            "snapshot": snapshot.to_dict(),
            "snapshot_ref": snapshot_ref.to_dict(),
            "raw_ref": raw_ref.to_dict(),
            "normalized_ref": normalized_ref.to_dict(),
        },
        "candidate_rules": [rule.to_dict() for rule in rules],
        "coverage": {**coverage_body, "coverage_digest": str(coverage_ref.digest)},
        "review_subject": {**review_body, "subject_digest": str(review_ref.digest)},
        "candidate_pack": {**pack_body, "pack_digest": str(pack_ref.digest)},
        "artifacts": [artifacts[key] for key in sorted(artifacts)],
    }
    assert_valid_document(document)
    return document


def _artifact_bytes(record: dict[str, Any]) -> bytes:
    content = record["content"]
    if record["media_type"] == "text/plain" and isinstance(content, str):
        return content.encode("utf-8")
    if record["media_type"] == JSON_MEDIA_TYPE and isinstance(content, (dict, list)):
        return canonical_bytes(content)
    _fail("artifact media type and content disagree")


def validate_document(document: object) -> list[str]:
    """Return closed-contract problems for a generated candidate bundle."""

    problems: list[str] = []
    try:
        value = _closed(document, {
            "schema_version", "scope", "production_allowed", "formal_source_claimed",
            "source", "candidate_rules", "coverage", "review_subject",
            "candidate_pack", "artifacts",
        }, "candidate bundle")
        encoded = canonical_bytes(value)
        if any(token in encoded for token in _BANNED):
            _fail("candidate bundle contains a retired corpus identity")
        test_only = value["schema_version"] == "jc/first-method-test-candidate-bundle/1.0"
        candidate = value["schema_version"] == "jc/cn-official-candidate-bundle/1.0"
        expected_scope = "test-only" if test_only else "candidate"
        if (
            not (test_only or candidate)
            or value["scope"] != expected_scope
            or value["production_allowed"] is not False
            or value["formal_source_claimed"] is not False
        ):
            _fail("candidate bundle non-promotion boundary drifted")
        coverage_kind = "test-candidate-coverage" if test_only else "candidate-coverage"
        review_kind = (
            "test-candidate-review-subject" if test_only else "candidate-review-subject"
        )
        pack_kind = "test-candidate-pack" if test_only else "candidate-pack"
        records = value["artifacts"]
        if not isinstance(records, list):
            _fail("candidate artifacts are not a list")
        artifact_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
        for raw_record in records:
            record = _closed(raw_record, {
                "artifact_kind", "content_ref", "media_type", "scope", "content",
            }, "candidate artifact")
            reference = ContentRefV4.from_dict(record["content_ref"])
            if (
                reference.kind != record["artifact_kind"]
                or record["scope"] not in {
                    expected_scope, "source-provenance", "source-authenticity",
                    RULE_COMPONENT_SCOPE,
                }
                or DigestV4.from_bytes(_artifact_bytes(record)) != reference.digest
            ):
                _fail("candidate artifact identity drifted")
            key = (reference.kind, str(reference.digest))
            if key in artifact_by_ref:
                _fail("candidate artifact reference is duplicated")
            artifact_by_ref[key] = record

        def bind(reference: ContentRefV4) -> dict[str, Any]:
            record = artifact_by_ref.get((reference.kind, str(reference.digest)))
            if record is None:
                _fail(f"candidate artifact is missing: {reference.kind}")
            return record

        source = _closed(value["source"], {
            "snapshot", "snapshot_ref", "raw_ref", "normalized_ref",
        }, "candidate source")
        snapshot = SourceSnapshotV4.from_dict(source["snapshot"])
        snapshot_ref = ContentRefV4.from_dict(source["snapshot_ref"])
        raw_ref = ContentRefV4.from_dict(source["raw_ref"])
        normalized_ref = ContentRefV4.from_dict(source["normalized_ref"])
        if source_snapshot_ref(snapshot) != snapshot_ref:
            _fail("candidate source snapshot reference drifted")
        raw_bytes = _artifact_bytes(bind(raw_ref))
        normalized_bytes = _artifact_bytes(bind(normalized_ref))
        if (
            snapshot.raw_digest != raw_ref.digest
            or snapshot.normalized_digest != normalized_ref.digest
            or normalize_source_bytes(raw_bytes) != normalized_bytes
            or (
                test_only and (
                    snapshot.authority_tier != "synthetic_test_only"
                    or snapshot.license_status != "test-fixture"
                    or snapshot.distribution_status != "test-only"
                )
            )
            or (
                candidate and (
                    snapshot.jurisdiction != "CN"
                    or snapshot.authority_tier not in _CANDIDATE_AUTHORITY_TIERS
                    or snapshot.license_status not in _CANDIDATE_LICENSE_STATUSES
                    or snapshot.distribution_status not in _CANDIDATE_DISTRIBUTION_STATUSES
                )
            )
        ):
            _fail("candidate source snapshot bytes or boundary drifted")
        expected_refs = {
            (reference.kind, str(reference.digest))
            for reference in (
                raw_ref, normalized_ref, snapshot.structure_map_ref,
                snapshot.authenticity_receipt_ref, *snapshot.provenance_refs, snapshot_ref,
            )
        }
        for reference in (
            snapshot.structure_map_ref, snapshot.authenticity_receipt_ref,
            *snapshot.provenance_refs, snapshot_ref,
        ):
            bind(reference)

        raw_rules = value["candidate_rules"]
        if not isinstance(raw_rules, list) or not raw_rules:
            _fail("candidate rules are missing")
        rules = [RuleV4.from_dict(item) for item in raw_rules]
        if any(
            rule.promotion_receipt_refs
            or rule.jurisdiction != snapshot.jurisdiction
            or rule.source_snapshot_ref != snapshot_ref
            for rule in rules
        ):
            _fail("candidate rule gained formal eligibility or another source")
        if test_only and (
            {rule.modality for rule in rules} != _MODALITIES
            or not any(rule.exception_refs for rule in rules)
            or not any(rule.priority_refs for rule in rules)
            or not any(rule.permission_ref for rule in rules)
            or not any(rule.temporal_constraint_refs for rule in rules)
            or not any(rule.numeric_constraint_refs for rule in rules)
        ):
            _fail("candidate semantic feature coverage drifted")
        rule_refs: list[ContentRefV4] = []
        for rule in rules:
            rule_ref = ContentRefV4(RULE_KIND, rule.rule_digest)
            bind(rule_ref)
            rule_refs.append(rule_ref)
            references = (
                rule.authority_ref, *rule.variable_declaration_refs, *rule.premise_refs,
                rule.conclusion_ref, *rule.exception_refs, *rule.priority_refs,
                *rule.attack_refs, *rule.temporal_constraint_refs,
                *rule.numeric_constraint_refs, *rule.interpretation_choice_refs,
                *rule.defined_term_refs,
            )
            if rule.permission_ref is not None:
                references = (*references, rule.permission_ref)
            for reference in references:
                bind(reference)
            expected_refs.update((ref.kind, str(ref.digest)) for ref in (rule_ref, *references))

        coverage = _closed(value["coverage"], {
            "schema_version", "status", "source_snapshot_ref", "denominator_unit_ids",
            "candidate_unit_ids", "omissions", "coverage_digest",
        }, "candidate coverage")
        coverage_body = {key: coverage[key] for key in coverage if key != "coverage_digest"}
        coverage_ref = ContentRefV4(coverage_kind, digest_value(coverage_body))
        if (
            coverage["coverage_digest"] != str(coverage_ref.digest)
            or coverage["status"] != (
                "COMPLETE_FOR_TEST_FIXTURE" if test_only else "CANDIDATE_COMPLETE"
            )
            or coverage["source_snapshot_ref"] != snapshot_ref.to_dict()
            or set(coverage["candidate_unit_ids"]) != {rule.rule_id for rule in rules}
            or set(coverage["denominator_unit_ids"]) != (
                set(coverage["candidate_unit_ids"])
                | {item["unit_id"] for item in coverage["omissions"]}
            )
            or len(coverage["denominator_unit_ids"]) != len(set(coverage["denominator_unit_ids"]))
            or any(not item.get("reason") for item in coverage["omissions"])
        ):
            _fail("candidate coverage denominator or omission register drifted")
        bind(coverage_ref)
        expected_refs.add((coverage_ref.kind, str(coverage_ref.digest)))

        review = _closed(value["review_subject"], {
            "schema_version", "scope", "status", "formal_source_claimed",
            "source_snapshot_ref", "coverage_ref", "rule_subject_digests",
            "required_roles", "subject_digest",
        }, "candidate review subject")
        review_body = {key: review[key] for key in review if key != "subject_digest"}
        review_ref = ContentRefV4(review_kind, digest_value(review_body))
        if (
            review["subject_digest"] != str(review_ref.digest)
            or review["scope"] != expected_scope
            or review["status"] != "AWAITING_EXTERNAL_REVIEW"
            or review["formal_source_claimed"] is not False
            or review["source_snapshot_ref"] != snapshot_ref.to_dict()
            or review["coverage_ref"] != coverage_ref.to_dict()
            or review["rule_subject_digests"] != [
                str(rule.promotion_subject_digest()) for rule in rules
            ]
            or review["required_roles"] != [
                "legal_reviewer_1", "legal_reviewer_2", "engineering_reviewer",
            ]
        ):
            _fail("candidate review subject drifted or claims approval")
        bind(review_ref)
        expected_refs.add((review_ref.kind, str(review_ref.digest)))

        pack = _closed(value["candidate_pack"], {
            "schema_version", "pack_id", "pack_version", "state", "scope",
            "production_allowed", "formal_source_claimed", "source_snapshot_ref",
            "rule_refs", "coverage_ref", "review_subject_ref",
            "promotion_receipt_refs", "signature_ref", "pack_digest",
        }, "candidate pack")
        pack_body = {key: pack[key] for key in pack if key != "pack_digest"}
        pack_ref = ContentRefV4(pack_kind, digest_value(pack_body))
        if (
            pack["pack_digest"] != str(pack_ref.digest)
            or pack["pack_id"] != (
                PACK_ID if test_only else OFFICIAL_CANDIDATE_PACK_ID
            )
            or pack["pack_version"] != (
                "0.0.0-test" if test_only else "0.0.0-candidate"
            )
            or pack["state"] != "CANDIDATE"
            or pack["scope"] != expected_scope
            or pack["production_allowed"] is not False
            or pack["formal_source_claimed"] is not False
            or pack["source_snapshot_ref"] != snapshot_ref.to_dict()
            or pack["rule_refs"] != [item.to_dict() for item in rule_refs]
            or pack["coverage_ref"] != coverage_ref.to_dict()
            or pack["review_subject_ref"] != review_ref.to_dict()
            or pack["promotion_receipt_refs"] != []
            or pack["signature_ref"] is not None
        ):
            _fail("candidate pack state, provenance, or non-promotion boundary drifted")
        bind(pack_ref)
        expected_refs.add((pack_ref.kind, str(pack_ref.digest)))
        if set(artifact_by_ref) != expected_refs:
            _fail("candidate artifact closure has missing or unreferenced nodes")
    except (CandidatePackError, KeyError, TypeError, ValueError) as exc:
        problems.append(str(exc))
    return problems


def assert_valid_document(document: object) -> None:
    problems = validate_document(document)
    if problems:
        _fail("; ".join(problems))


def build_fixture_bytes(source_path: Path = SOURCE_PATH) -> bytes:
    source = parse_json_document(Path(source_path).read_bytes())
    return canonical_bytes(build_document(source))


def render_review_markdown(
    source_document: object,
    candidate_document: object,
) -> bytes:
    """Render the exact candidate review subject without recording a decision."""

    source, _ = _validate_source(source_document)
    candidate = build_document(source)
    if candidate_document != candidate:
        _fail("review source and candidate bundle do not match")
    rules = candidate["candidate_rules"]
    review = candidate["review_subject"]
    pack = candidate["candidate_pack"]
    coverage = candidate["coverage"]
    source_snapshot = candidate["source"]["snapshot"]
    locator = source_snapshot["canonical_locator"]["value"]
    rule_by_id = {rule["rule_id"]: rule for rule in rules}
    subject_by_id = {
        rule["rule_id"]: digest
        for rule, digest in zip(rules, review["rule_subject_digests"], strict=True)
    }
    lines = [
        "# cn-official 候选规则人工复核件",
        "",
        f"- 法源：{source_snapshot['title']}",
        f"- 发布机关：{source_snapshot['issuer']}",
        f"- 正式来源：{locator}",
        f"- 生效时间：{source_snapshot['effective_from']['wire']}",
        f"- 候选规则：{len(rules)} 条；遗漏：{len(coverage['omissions'])} 条",
        f"- 候选状态：{pack['state']}（production_allowed=false）",
        f"- 法源快照：`{candidate['source']['snapshot_ref']['digest']}`",
        f"- 覆盖摘要：`{coverage['coverage_digest']}`",
        f"- 规则包摘要：`{pack['pack_digest']}`",
        f"- 本次复核对象：`{review['subject_digest']}`",
        f"- 所需角色：{', '.join(review['required_roles'])}",
        "",
        "复核对象仅为下列法源切分和规则语义；本文不记录批准，也不使候选包获得生产资格。",
    ]
    number = 0
    for unit in source["normative_units"]:
        if unit["state"] == "omitted":
            continue
        number += 1
        rule = rule_by_id[unit["unit_id"]]
        lines.extend([
            "",
            f"## {number}. {unit['unit_id']}",
            "",
            f"- 原文：{unit['text']}",
            f"- 模态：`{unit['modality']}`",
            f"- 前提：`{unit['premise']}`",
            f"- 结论：`{unit['conclusion']}`",
            f"- 例外：`{unit['exception'] or '-'}`",
            f"- 优先于：`{unit['priority_over'] or '-'}`",
            f"- 许可：`{unit['permission'] or '-'}`",
            f"- 时间约束：`{unit['temporal'] or '-'}`",
            f"- 数值约束：`{unit['numeric'] or '-'}`",
            f"- 规则摘要：`{rule['rule_digest']}`",
            f"- 晋级对象摘要：`{subject_by_id[unit['unit_id']]}`",
        ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--review-output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = parse_json_document(args.source.read_bytes())
        document = build_document(source)
        expected = canonical_bytes(document)
        review_expected = (
            render_review_markdown(source, document)
            if args.review_output is not None else None
        )
    except (OSError, CandidatePackError, TypeError, ValueError) as exc:
        print(f"candidate pack build failed: {exc}", file=sys.stderr)
        return 1
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            print("candidate pack fixture drifted", file=sys.stderr)
            return 1
        if review_expected is not None and (
            not args.review_output.is_file()
            or args.review_output.read_bytes() != review_expected
        ):
            print("candidate review document drifted", file=sys.stderr)
            return 1
        print(f"candidate pack fixture OK: {len(expected)} bytes")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    if review_expected is not None:
        args.review_output.parent.mkdir(parents=True, exist_ok=True)
        args.review_output.write_bytes(review_expected)
    print(f"candidate pack fixture written: {args.output} ({len(expected)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
