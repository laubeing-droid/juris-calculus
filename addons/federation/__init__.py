"""Federation — cross-jurisdiction reasoning organized by legal family.

Common Law family: pair-wise comparison between all common-law jurisdictions.
Civil Law family: each jurisdiction stands alone (no cross-comparison).

Usage:
    from addons.federation.common_law import FederatedReasoner
    fr = FederatedReasoner()
    result = fr.run({"ContractFormed": 1.0})  # auto-discovers all common-law addons
"""
