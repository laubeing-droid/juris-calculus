# Runtime Refinement Rules (juris-calculus)

- The production path is the subject of refinement.
- Horn evaluation is positive and monotone.
- Exceptions, rebuttals, and priority effects belong to argumentation.
- RuleId, ClaimId, and ArgumentId are distinct.
- One claim may have multiple arguments.
- Do not add SyntheticClaim.
- Do not manually inject expected attacks.
- The certificate checker must be independent of the production evaluator.
- Do not modify expected tests to accept incorrect runtime behavior.
- All changes must be verified by `pytest tests/ -v` before completion.
