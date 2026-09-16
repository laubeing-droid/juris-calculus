"""C06 math-export adapter over the pinned legal-math-modeling subject.

This package is the JC consumer side of the LMM full-release export
contract (EXPORT_CONTRACT.json, run 34797682659, subject
5084f25e69ae27332404dc9f341a61d46ef0fc53). It provides:

- the pinned subject identity and the eleven required export interfaces
  (:mod:`compiler_core.math_export.pins`);
- validation and canonical fingerprints of the completion documents
  (:mod:`compiler_core.math_export.subject`);
- the B07-shaped cache/certificate fingerprint that invalidates whenever
  the mathematics subject changes (:mod:`compiler_core.math_export.fingerprint`);
- public-entry run witnesses with the pinned status mapping
  (:mod:`compiler_core.math_export.witness`);
- a fail-closed subprocess gateway to the LMM independent checker, which
  never imports or invokes the JC main solver
  (:mod:`compiler_core.math_export.checker_gateway`);
- cross-entry semantic consistency for witnesses produced through the
  CLI, ``JCClient`` and MCP entries (:mod:`compiler_core.math_export.consistency`).

Honesty boundary: nothing here claims E01 empirical validation, legal
source review, external factual truth, or any approval or signature that
does not already exist. The pinned ``not_established`` list is carried
verbatim by every witness and by the integration evidence.
"""
from __future__ import annotations

from compiler_core.math_export.checker_gateway import (
    IndependentCheckerError,
    materialize_expected,
    verify_receipt,
)
from compiler_core.math_export.consistency import (
    CrossEntryInconsistency,
    assert_cross_entry_consistency,
)
from compiler_core.math_export.fingerprint import (
    SubjectCacheKeyV1,
    cache_entry,
    cache_entry_valid,
    subject_fingerprint,
    version_change_invalidates,
)
from compiler_core.math_export.pins import (
    ATTEMPT,
    EXPORT_INTERFACES,
    LAKE_MANIFEST_SHA256,
    LEAN_TOOLCHAIN_SHA256,
    LATEST_EVIDENCE,
    LATEST_EVIDENCE_RUN_ID,
    REPOSITORY,
    REQUIRED_INTERFACES,
    RUNTIME_REF_COMMIT,
    RUN_ID,
    SUBJECT_COMMIT,
    SUBJECT_TREE,
)
from compiler_core.math_export.subject import (
    contract_fingerprint,
    math_completion_fingerprint,
    validate_export_contract,
    validate_math_completion,
)
from compiler_core.math_export.witness import (
    DECISION_STATUS_MAPPING,
    DECISION_STATUS_MAPPING_V1,
    LEGACY_WITNESS_SCHEMA,
    RUN_GLOBAL_FAILURE_DECISIONS,
    WITNESS_SCHEMA,
    build_run_witness,
    validate_witness,
)

__all__ = (
    "ATTEMPT",
    "CrossEntryInconsistency",
    "DECISION_STATUS_MAPPING",
    "DECISION_STATUS_MAPPING_V1",
    "EXPORT_INTERFACES",
    "IndependentCheckerError",
    "LAKE_MANIFEST_SHA256",
    "LEAN_TOOLCHAIN_SHA256",
    "LEGACY_WITNESS_SCHEMA",
    "LATEST_EVIDENCE",
    "LATEST_EVIDENCE_RUN_ID",
    "REQUIRED_INTERFACES",
    "REPOSITORY",
    "RUNTIME_REF_COMMIT",
    "RUN_ID",
    "RUN_GLOBAL_FAILURE_DECISIONS",
    "SUBJECT_COMMIT",
    "SUBJECT_TREE",
    "SubjectCacheKeyV1",
    "WITNESS_SCHEMA",
    "assert_cross_entry_consistency",
    "build_run_witness",
    "cache_entry",
    "cache_entry_valid",
    "contract_fingerprint",
    "materialize_expected",
    "math_completion_fingerprint",
    "subject_fingerprint",
    "validate_export_contract",
    "validate_math_completion",
    "validate_witness",
    "verify_receipt",
    "version_change_invalidates",
)
