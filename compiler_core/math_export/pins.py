"""Pinned identity of the legal-math-modeling full-release subject.

The values in this module are the single authoritative copy for runtime
logic. ``proofs/lmm-fullmath/BINDINGS_EXTRACT.json`` carries the same
values as data; ``tests/contract/test_c06_math_export.py`` asserts the two
copies never drift. The subject is fixed and must never move: the C06
correspondence claim is valid exactly for this mathematics version.
"""
from __future__ import annotations

SUBJECT_COMMIT = "5084f25e69ae27332404dc9f341a61d46ef0fc53"
SUBJECT_TREE = "184a766a2d22b1c4be31bb119e4b82b76f0be540"
REPOSITORY = "laubeing-droid/legal-math-modeling"
RUN_ID = "34797682659"
ATTEMPT = "1"
LEAN_TOOLCHAIN_SHA256 = (
    "54727eec5cba149c18842e6deb5c41b369d66455c93ce135d7d5347c782b2325"
)
LAKE_MANIFEST_SHA256 = (
    "7230ea7eeaf37899cdf17d1c878e853e3650d276e6ec6b7f1d2f4c841952963e"
)

# The JC producer commit the LMM runtime-refinement receipts were bound to.
# Cross-repo receipts must keep citing this fixed runtime_ref; drifting to
# an unpinned producer SHA invalidates the bound receipt evidence.
RUNTIME_REF_COMMIT = "c79e03b8d0cfed85c43cc013bf8a0b50326bc858"

# B-01 (math-downstream 2026-09-17): the same mathematics subject
# observed under a second GitHub Actions run. The semantic subject
# four-tuple above is unchanged; this run is additional evidence for the
# identical subject, never a repin. The original RUN_ID record and its
# historical receipts keep their bytes untouched. The artifact archive
# bytes were observed through the run/job APIs and logs, not
# independently re-downloaded in the review that recorded them.
LATEST_EVIDENCE_RUN_ID = "35124268367"
LATEST_EVIDENCE = {
    "repository": REPOSITORY,
    "run_id": LATEST_EVIDENCE_RUN_ID,
    "attempt": "1",
    "completed_at_utc": "2026-09-16T16:56:34Z",
    "completion_log": "MATH_BUILD_COMPLETE; errors=0",
    "final_gate_log": (
        "PASS: retained obligations + fixed typed seven-axis root. "
        "Not production, legal, or empirical acceptance."
    ),
    "artifact": {
        "name": "full-math-completion-35124268367-1",
        "id": "10458606882",
        "zip_sha256": (
            "d6b571a8a538ed9f6b03813b107bab3d44b62a0a81c3a62cffe9486a"
            "c745e3cf"
        ),
        "bytes_independently_downloaded": False,
    },
    "evidence_sources": (
        "run API",
        "job summaries",
        "mathematics-completion job log",
        "final-gate job log",
    ),
    "action": "record_new_evidence_separately_no_semantic_repin",
}

# EXPORT_CONTRACT.json /contract/required — the eleven export interfaces.
REQUIRED_INTERFACES = (
    "formal_input_types",
    "canonical_codec_and_proof",
    "reference_checker_entry",
    "exact_inner_outer_and_statistical_contracts",
    "supported_grammar",
    "scope_assumptions",
    "certified_names_and_subject",
    "law_policy_inputs",
    "model_data_inputs",
    "counterexamples",
    "deferred_production_adapters",
)

# MATH_COMPLETION.json /not_established — carried verbatim, never closed by
# this integration.
NOT_ESTABLISHED = (
    "actual_JC_Harness_integration",
    "E01_real_data_validation",
    "truth_of_external_facts",
    "unrestricted_natural_language_or_entire_legal_system",
)

# EXPORT_CONTRACT.json /contract/do_not_run_now — preserved verbatim.
DO_NOT_RUN_NOW = (
    "modify_jc",
    "modify_harness",
    "request_external_approvals",
    "train_on_private_records_without_inputs",
)

# EXPORT_CONTRACT.json /external/items ids — the deferred production
# obligations this integration must not mark closed.
EXTERNAL_ITEM_IDS = (
    "C06-PRODUCTION",
    "ROOT07-PRODUCTION",
    "E01-EMPIRICAL",
    "B-LEGAL-REVIEW",
    "X-EXTERNAL-TRUTH",
)

# Per-interface adapter records: where the interface lives on the LMM side
# (carrier, as of the pinned subject) and what JC installed for it.
EXPORT_INTERFACES = (
    {
        "name": "formal_input_types",
        "lmm_carriers": ("theory/spec/canonical_semantics.py",),
        "jc_adapter": "compiler_core/contracts.py CaseInputBundleV4 intake; "
                      "probe packs express the canonical rule/fact shapes",
        "status": "ADAPTED",
    },
    {
        "name": "canonical_codec_and_proof",
        "lmm_carriers": (
            "proofs/lean/juris_lean/JurisLean/FullMath/Core/IdentityCodec.lean",
        ),
        "jc_adapter": "compiler_core/canonical_serialization.py canonical bytes; "
                      "witness input/result digests",
        "status": "ADAPTED",
    },
    {
        "name": "reference_checker_entry",
        "lmm_carriers": (
            "scripts/verify_runtime_refinement_receipt.py",
            "theory/spec/runtime_differential.py",
        ),
        "jc_adapter": "compiler_core/math_export/checker_gateway.py subprocess "
                      "gateway; tools/generate_c06_entry_receipts.py producer",
        "status": "ADAPTED",
    },
    {
        "name": "exact_inner_outer_and_statistical_contracts",
        "lmm_carriers": (
            "proofs/lean/juris_lean/JurisLean/FullMath/Representation/"
            "SymbolicRepresentation.lean",
            "tools/full_math/implementation/probability_ref.py",
        ),
        "jc_adapter": "no JC consumption route in this integration; statuses "
                      "carried by the pinned mapping only",
        "status": "CARRIED_NOT_CONSUMED",
    },
    {
        "name": "supported_grammar",
        "lmm_carriers": (
            "proofs/lean/juris_lean/JurisLean/FullMath/Document/ByteSyntax.lean",
        ),
        "jc_adapter": "local rule-pack byte syntax for probe packs; delivery "
                      "grammar remains a LMM-side contract",
        "status": "PARTIAL_PROBE_ONLY",
    },
    {
        "name": "scope_assumptions",
        "lmm_carriers": ("tools/full_math/spec/SCOPE.json",),
        "jc_adapter": "compiler_core/math_export/subject.py validates scope "
                      "fields; honesty boundaries carried verbatim",
        "status": "ADAPTED",
    },
    {
        "name": "certified_names_and_subject",
        "lmm_carriers": ("tools/full_math/spec/BINDINGS.json",),
        "jc_adapter": "proofs/lmm-fullmath/BINDINGS_EXTRACT.json bound rows; "
                      "compiler_core/math_export/pins.py subject pin",
        "status": "ADAPTED",
    },
    {
        "name": "law_policy_inputs",
        "lmm_carriers": ("tools/full_math/spec/LEGAL_FAMILIES_14.json",),
        "jc_adapter": "probe packs are engineering-test material only; real "
                      "family policies stay with B-LEGAL-REVIEW (open)",
        "status": "DEFERRED_EXTERNAL",
    },
    {
        "name": "model_data_inputs",
        "lmm_carriers": ("tools/full_math/reference/extended_algorithms.py",),
        "jc_adapter": "no JC consumption route; E01 real data calibration "
                      "remains open",
        "status": "DEFERRED_EXTERNAL",
    },
    {
        "name": "counterexamples",
        "lmm_carriers": (
            "tools/full_math/spec/BINDINGS.json negative_test_ids",
            "docs/audit/counterexample_registry.json",
        ),
        "jc_adapter": "tampered-bundle probe exercises the fail-closed "
                      "rejection direction; full negative suite stays in LMM",
        "status": "PARTIAL_PROBE_ONLY",
    },
    {
        "name": "deferred_production_adapters",
        "lmm_carriers": ("tools/full_math/spec/DEFERRED_EXTERNAL.json",),
        "jc_adapter": "this integration is the C06-PRODUCTION route; ROOT07, "
                      "E01, B-LEGAL-REVIEW and X-EXTERNAL-TRUTH stay open",
        "status": "ADAPTED_C06_ONLY",
    },
)
