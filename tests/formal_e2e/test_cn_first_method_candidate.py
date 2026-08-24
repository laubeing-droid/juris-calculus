"""The W8 local pipeline ends at candidate state, never at a formal pack."""

from __future__ import annotations

import pytest

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import ContractV4Error, PackManifestV4
from tools import build_cn_official_pack as builder


def test_first_method_source_reaches_complete_test_candidate_closure() -> None:
    source = parse_json_document(builder.SOURCE_PATH.read_bytes())
    document = builder.build_document(source)

    assert builder.validate_document(document) == []
    assert document["coverage"]["status"] == "COMPLETE_FOR_TEST_FIXTURE"
    assert document["review_subject"]["status"] == "AWAITING_EXTERNAL_REVIEW"
    assert document["candidate_pack"]["state"] == "CANDIDATE"


def test_candidate_bundle_is_not_a_pack_manifest_or_signed_release() -> None:
    document = parse_json_document(builder.OUTPUT_PATH.read_bytes())

    with pytest.raises(ContractV4Error):
        PackManifestV4.from_dict(document["candidate_pack"])
    assert document["candidate_pack"]["signature_ref"] is None
    assert document["candidate_pack"]["promotion_receipt_refs"] == []
