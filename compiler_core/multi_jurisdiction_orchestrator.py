#!/usr/bin/env python3
"""Multi-Jurisdiction Orchestrator — runs evaluation across multiple jurisdictions.

When a case involves CN + HK + US, this module:
  1. Selects the governing jurisdiction via conflict_of_laws
  2. Runs the primary jurisdiction's evaluator
  3. Optionally runs bridge evaluations for cross-reference
  4. Merges all ProofTrees with source jurisdiction labels

Design: Gemini audit — "MultiJurisdictionOrchestrator that merges proof trees"
"""
from typing import Dict, List, Optional
from compiler_core.types import LegalFact, IRState
from compiler_core.proof_tree import ProofTree, ProofNode
from compiler_core.conflict_of_laws import select_jurisdiction
from compiler_core.plugin_registry import registry


class MultiJurisdictionOrchestrator:
    """Run evaluation across multiple jurisdictions and merge results."""

    def __init__(self):
        pass

    def run(
        self,
        facts: Dict[str, LegalFact],
        jurisdictions: Optional[List[str]] = None,
        primary_jurisdiction: Optional[str] = None,
    ) -> ProofTree:
        """Run multi-jurisdiction evaluation.

        Args:
            facts: input facts
            jurisdictions: list of jurisdiction codes to evaluate (e.g., ["CN", "HK", "US"])
            primary_jurisdiction: override primary jurisdiction (otherwise auto-detected)

        Returns:
            Merged ProofTree with source labels
        """
        # Auto-detect primary jurisdiction
        primary = primary_jurisdiction or select_jurisdiction(facts)
        if jurisdictions is None:
            jurisdictions = [primary]

        merged = ProofTree(jurisdiction=primary)
        merged.bridge_health = {"primary": primary, "evaluated": jurisdictions}

        for code in jurisdictions:
            adapter = registry.get(code.lower())
            if not adapter:
                continue

            try:
                evaluator = adapter.load_evaluator()
                state = IRState(facts=dict(facts))
                result = evaluator.evaluate(state)

                # Merge claims with source label
                for cid, claim in result.claims.items():
                    prefixed_id = f"{code}:{cid}"
                    node = ProofNode(
                        node_id=prefixed_id,
                        kind="statute",
                        head_claim=cid,
                        confidence=claim.confidence,
                        children=[],
                        source_anchor=claim.source_anchor or "",
                    )
                    merged.add_node(node)
                    merged.cn_claims.append(prefixed_id)

                # Merge blocked claims
                for bc in getattr(result, "blocked_claims", []):
                    merged.blocked_claims.append(f"{code}:{bc}")

            except Exception as e:
                merged.bridge_health[f"{code}_error"] = str(e)

        return merged
