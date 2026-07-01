# Semantic Boundary Checklist

Use this checklist before changing JC runtime behavior. Its purpose is to decide whether the change can be made in JC or must first be resolved in legal-math-modeling.

## Route Back to legal-math-modeling When

The change affects:

- `DecisionStatus`;
- checker acceptance standards;
- `verified_fact` eligibility;
- Horn closure semantics;
- attack graph semantics;
- exception handling;
- permission interpretation;
- priority ordering;
- certificate acceptance;
- fail-closed behavior.

These are specification-level decisions. Do not patch them locally in JC as implementation convenience.

## Safe to Handle in JC When

The change is limited to:

- manifest exposure of already-defined public tools;
- response envelope formatting without changing semantics;
- deterministic report generation;
- documentation or disclosure wording;
- fixture expansion that preserves existing expected semantics;
- runtime bug fixes that restore the documented specification.

## Required Questions

Before implementation, answer:

1. Does this change make a previously rejected item accepted?
2. Does this change let candidate material enter reasoning?
3. Does this change alter attack, exception, permission, or priority ordering?
4. Does this change weaken certificate checking?
5. Does this change hide a red-light failure?
6. Does this change require new canonical Lean types or theorems upstream?

If any answer is yes, stop and route upstream first.

## Evidence After Change

At minimum, run the targeted test and record:

- command;
- result;
- affected boundary;
- whether legal-math-modeling was required;
- remaining risk.

For public surface changes, also run MCP manifest-dispatch tests and `python mcp_server.py --test`.
