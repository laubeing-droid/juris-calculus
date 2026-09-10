"""jc-business-root/1: finite conditional principal production capability.

Responsibility split inside this package (ROUTE1_JC_PLAN_20260910 section 3):

* :mod:`codec` — exact rationals, the 20-dimension context, closed decode.
* :mod:`spec` — the typed I0 (spec/model) authority and lossless wire form.
* :mod:`solver` — the solver side: compiled guards, own enumeration, max clips.
* :mod:`checker` — the independent checker: structural denotation, bitmask
  enumeration, conservation rows C>=0, U>=0, C*U=0, C-U+paid==principal.
* :mod:`analytics` — E[C]/E[U]/E[R], threshold events, settlement grid.
* :mod:`delivery_checker` — verify-only two-file readback; never evaluates.

Everything is a conditional model analysis; no court finding, win rate, or
institutional approval is implied. See the retained LMM reference for the
mathematical authority (legal-math-modeling, MIT License).
"""

from compiler_core.business_root.codec import (
    BUSINESS_CHECKER_VERSION,
    BUSINESS_EMPIRICAL_STATUS_V1,
    BUSINESS_FORMAL_EVIDENCE_V1,
    BUSINESS_LEGAL_BASIS_STATUS_V1,
    BUSINESS_MODEL_BASIS_V1,
    BUSINESS_PROFILE_V1,
    BUSINESS_REQUIREMENT_V1,
    BUSINESS_ROOT_CAPABILITY,
    BusinessContextKey,
    BusinessRootError,
    exact_rational,
    rational_wire,
)
from compiler_core.business_root.spec import (
    DecisionInputs,
    Formula,
    PrincipalSpec,
    World,
    decode_model,
    decode_spec,
    encode_model,
    encode_spec,
)

__all__ = (
    "BUSINESS_CHECKER_VERSION",
    "BUSINESS_EMPIRICAL_STATUS_V1",
    "BUSINESS_FORMAL_EVIDENCE_V1",
    "BUSINESS_LEGAL_BASIS_STATUS_V1",
    "BUSINESS_MODEL_BASIS_V1",
    "BUSINESS_PROFILE_V1",
    "BUSINESS_REQUIREMENT_V1",
    "BUSINESS_ROOT_CAPABILITY",
    "BusinessContextKey",
    "BusinessRootError",
    "DecisionInputs",
    "Formula",
    "PrincipalSpec",
    "World",
    "decode_model",
    "decode_spec",
    "encode_model",
    "encode_spec",
    "exact_rational",
    "rational_wire",
)
