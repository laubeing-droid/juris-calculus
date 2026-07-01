# Graph Similarity Contract

Current classification: bounded task-specific engineering score.

The graph similarity routine is useful for ranking and comparison. It must not be described as a mathematical metric or PSD kernel unless those properties are separately proven.

## Current Evidence

| Property | Status | Evidence |
|---|---|---|
| boundedness in `[0, 1]` | supported | finite Z3/Dafny-style bounded check |
| non-negativity | supported | follows from boundedness check |
| deterministic ranking | supported | fixed inputs and deterministic weights |
| relabeling invariance | supported by construction | graph labels do not affect score |
| strict reflexivity | refuted | empty-feature self-pair can score below 1 |
| identity of indiscernibles | refuted | follows from strict-reflexivity counterexample |
| triangle inequality | unknown | not proven |
| PSD kernel property | unknown | not proven |
| threshold stability | empirical only | requires OAT or held-out analysis |

## Allowed Wording

- "bounded graph similarity score"
- "task-specific engineering score"
- "deterministic ranking feature"
- "finite check supports range bounds"

## Prohibited Wording

- "metric"
- "kernel"
- "formally proved similarity measure"
- "distance function" unless a distance-specific proof is added

## Closure Requirement

To upgrade the claim, add:

- exact formula and domain;
- theorem target;
- proof artifact or finite bound scope;
- regression tests preserving the property;
- disclosure of counterexamples that remain unresolved.
