# LLM Ingestion Contract

JC may use LLMs as proposal engines. It must not use LLMs as proof engines or as direct writers to reasoning-eligible facts.

## Fixed Architecture

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

This architecture is mandatory for public-kernel work.

## Allowed LLM Outputs

LLMs may propose:

- candidate facts;
- candidate rule mappings;
- candidate source anchors;
- draft explanations;
- test fixture suggestions;
- suspected inconsistencies.

Each output must remain marked as candidate material until deterministic validation promotes it.

## Prohibited LLM Outputs

LLMs must not directly produce:

- `verified_fact`;
- accepted certificates;
- checker pass results;
- formal proof claims;
- public release evidence;
- hidden changes to attack, exception, permission, or priority semantics.

## Required Gates

Before an LLM-derived item can affect reasoning, it needs the applicable deterministic gates:

| Item | Required gate |
|---|---|
| fact | schema check, source binding, verification gate |
| rule | schema check, modality check, source anchor, regression tests |
| certificate | certificate checker |
| MCP response | manifest dispatch and envelope tests |
| differential claim | spec-shadow harness |
| public report | stale-narrative and disclosure scan |

## Failure Behavior

If a gate fails or cannot run, the result stays candidate-only or is rejected. The runtime must not replace a blocked gate with an LLM explanation.

## Disclosure Language

Use precise wording:

- acceptable: "LLM-generated candidate passed deterministic verifier X"
- acceptable: "fixture differential aligned for N cases"
- prohibited: "LLM verified the fact"
- prohibited: "the system proves every runtime path"
- prohibited: "experience output is equivalent to formal proof"

`FactCoordinate` is an engineering input shape only. LLM-origin material remains candidate-only until deterministic gates promote it. `USER_ASSUMED`, `DISPUTED`, and `UNKNOWN` cannot be converted into `verified_fact`, accepted certificates, or formal-proof claims by narrative output.
