"""Stateless candidate version routing after explicit legal review inputs.

This is a preparatory adapter, not DecisionStatus or a verified_fact producer.
Date order alone never decides retroactivity, leniency, hierarchy or concepts.
Bridge integration and source authentication remain with the existing gates.
"""
from __future__ import annotations

from datetime import date
from typing import Mapping, Any


def select_applicable_law(request: Mapping[str, Any]) -> dict[str, Any]:
    """Route one normative proposition using externally reviewed premises.

    ``sources`` supply versionId/sourceRef/verified/issuer and validFrom,
    validTo (exclusive). ``basis`` supplies kind/sourceRef/ruleScope and a
    lawyer reviewRef. These inputs are assertions to authenticate upstream;
    returned CANDIDATE is not legal acceptance or a source-verification receipt.
    """
    result = {"status": "UNVERIFIED", "selectedVersionIds": [], "reasonCodes": [],
              "reviewRequired": True, "legalConclusionVerified": False,
              "retrievalPolicy": "retain_history_and_opposing_views"}
    sources = list(request.get("sources", []))
    result["consideredVersionIds"] = sorted(str(source["versionId"]) for source in sources)
    basis = request.get("basis", {})
    reasons = result["reasonCodes"]
    if not sources or any(source.get("verified") is not True or not source.get("sourceRef")
                          or not source.get("issuer") for source in sources):
        reasons.append("verified_source_and_issuer_required")
        return result
    if not basis.get("sourceRef") or not basis.get("ruleScope") or not basis.get("reviewRef"):
        reasons.append("temporal_basis_and_scope_review_required")
        return result
    ids = {source["versionId"] for source in sources}
    if len(ids) != len(sources):
        raise ValueError("duplicate_version_id")
    if request.get("conflict"):
        # Neither 'higher/newer/special' labels nor issuer equality decide a
        # conflict. Record the competent authority's resolution if available.
        resolution = request.get("conflictResolution", {})
        if not all(resolution.get(key) for key in ("authority", "sourceRef", "reviewRef", "selectedVersionId")):
            reasons.append("competent_authority_resolution_required")
            return result
        selected = resolution["selectedVersionId"]
    elif request.get("finalBeforeTransition") is True:
        selected = request.get("finalJudgmentVersionId")
        if not request.get("finalJudgmentRef"):
            reasons.append("final_judgment_record_required")
            return result
    elif basis.get("kind") in {"criminal_leniency", "civil_favorable", "civil_gap", "continuing_fact", "civil_reasoning_only"}:
        comparison = request.get("comparison", {})
        required = ("selectedVersionId", "oldOutcome", "newOutcome", "reason", "reviewRef")
        if not all(comparison.get(key) for key in required):
            reasons.append("substantive_comparison_review_required")
            return result
        selected = comparison["selectedVersionId"]
        if basis["kind"] == "civil_reasoning_only":
            result["reasoningOnlyVersionIds"] = sorted(comparison.get("reasoningOnlyVersionIds", []))
    elif basis.get("kind") in {"fact_time", "new_first_instance_acceptance"}:
        if basis["kind"] == "new_first_instance_acceptance":
            if request.get("instance") != "first" or request.get("newlyAccepted") is not True:
                reasons.append("special_acceptance_scope_not_established")
                return result
            raw_date = request.get("acceptedAt")
        else:
            raw_date = request.get("factAt")
        if not raw_date or basis.get("exceptionsReviewed") is not True:
            reasons.append("date_and_special_exceptions_review_required")
            return result
        day = date.fromisoformat(raw_date)
        matches = [source["versionId"] for source in sources
                   if date.fromisoformat(source["validFrom"]) <= day
                   and (source.get("validTo") is None or day < date.fromisoformat(source["validTo"]))]
        if len(matches) != 1:
            reasons.append("version_gap_or_overlap")
            return result
        selected = matches[0]
    else:
        reasons.append("temporal_basis_not_supported_requires_review")
        return result
    if selected not in ids:
        reasons.append("selected_version_not_in_verified_sources")
        return result
    result.update(status="CANDIDATE", selectedVersionIds=[selected])
    reasons.append("reviewed_premises_routed_not_legal_acceptance")
    return result
