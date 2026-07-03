# LSC Boundary Absorption

## Position

JC absorbs LSC boundary mechanisms, not LSC legal tools. The absorbed layer is an engineering guardrail for fact trust, degradation, provenance, taint, renderer limits, IO contracts, conflict certificates, and review packets.

JC does not absorb LSC's 36 legal objects, business calculators, AgentSkill wrapper, CLI/API, China-law concrete rules, or P1/P2 substantive judgment.

The companion `legal-math-modeling` repository is the specification boundary and is now consolidated on `main`. Its public docs and manifest record this absorption as runtime metadata governance, not as a new Lean theorem family. JC may consume that boundary as a route-back rule, but it must not claim that Lean proves the LSC-derived runtime metadata.

## Terminology Mapping

| LSC term | JC boundary alias | Meaning in JC |
|---|---|---|
| `FactCoordinate` | Fact Trust Envelope | A value with status, source ids, alternatives, provenance, review flag, and creator metadata |
| `ADMITTED` | `checked_fact` candidate mapping | Checked but not automatically `verified_fact` |
| `VERIFIED` | `verified_fact` candidate mapping | Still must pass JC's verified-fact gate |
| `COURT_FIXED` | `verified_fact` with court provenance | Verified only when provenance states `created_by=court` or equivalent court source |
| `USER_ASSUMED` | `user_assumed` / assumption taint | May support hypothetical output only |
| `DISPUTED` | `disputed` / review packet | Blocks final formal conclusion and carries alternatives |
| `UNKNOWN` | `unknown` / missing fact review | Blocks required-fact calculation and produces review material |
| `DEGRADED_TO_AUXILIARY` | `review_only_result` | Review-only output with alternative paths/questions |
| `HYPOTHETICAL_RESULT` | `hypothetical_result` | Assumption-tainted result, not final legal advice |
| `CONFLICT` | `conflict_certificate` | Machine-readable conflict packet without priority resolution |

## P0/P1/P2 Boundary

- P0: facts and rule-closure behavior that can be handled by deterministic formal runtime gates.
- P1: fact subsumption, discretion, conflict merits, priority choice in real disputes, and legal-conclusion premises needing human or court treatment.
- P2: references, book opinions, case summaries, prompt suggestions, and explanatory hints.

P1/P2 material can appear in review packets, provenance summaries, or renderer warnings. It cannot be laundered into `verified_fact`, accepted certificates, Horn closure, attack/exception/priority/permission semantics, or formal proof claims.

## Prohibited Moves

- Do not copy LSC objects or object schemas into JC.
- Do not let renderer output final legal advice for hypothetical, disputed, unknown, conflict, or engine-error results.
- Do not treat LSC fixtures as JC jurisdictional law.
- Do not change certificate checker acceptance or verified-fact eligibility in JC. Route such work back to `D:\Codex\数学证明\legal-math-modeling`.
- Do not treat legal-math CI success as proof of JC runtime metadata. CI only proves the checked sources for the referenced commit; runtime conformance still requires JC tests and certificates.
