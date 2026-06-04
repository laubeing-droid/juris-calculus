# juris-calculus Concept Roadmap

Concepts not yet formalized. Ordered by priority for community contribution.

---

## v1.2.0 — Implemented

| Domain | Status |
|--------|:------:|
| PRC Civil Code: 13 domains, 2,117 Horn rules | v1.2.0 |
| US Federal: 81 Horn + 86 L0 constraints (UCC Art.2, Due Process, Equitable Remedies) | v1.2.0 |
| US State Threat: WI long-arm (12) + NJ punitive damages (12) FastPath signatures | v1.2.0 |
| HK: 93 Horn rules (Cap 26/32/622/571/4A) | v1.2.0 |
| PRC-US Alignment: 60 CBL blocking + 23 SPC + 10 procedural justice | v1.2.0 |
| Tri-Rail Collider: 12 cross-border conflict classes | v1.2.0 |
| MCP Server: 9 resources + 7 tools | v1.2.0 |
| Action Agent: MemoCompiler with Jinja2 templates | v1.2.0 |

---

## v2.0 — Tort & Regulatory (Priority: P1)

| Domain | Concepts | Difficulty |
|--------|---------|-----------|
| Negligence | DutyOfCare, BreachOfDuty, Causation, ActualInjury | Medium |
| Fraud | Misrepresentation, Scienter, JustifiableReliance | High |
| Employment Discrimination | AdverseAction, ProtectedClass, DisparateTreatment | High |
| Securities (Howey Test) | HoweyTest_Investment, CommonEnterprise, ProfitExpectation | Extreme |
| Antitrust (Sherman §2) | MarketPower, ExclusionaryConduct, RelevantMarket | Extreme |

---

## v3.0 — Constitutional & Procedural (Priority: P2)

| Domain | Concepts | Difficulty |
|--------|---------|-----------|
| First Amendment | ProtectedSpeech, GovernmentCoercion, StateAction | Extreme |
| Class Action (Rule 23) | ClassCertification, Commonality, Numerosity | Extreme |
| RICO | PatternOfRacketeering, Enterprise | Extreme |
| FRAND / Patent | PatentOwnership, FRANDCommitment, LicensingDispute | High |

---

## Jurisdiction Expansion

| Jurisdiction | Effort | Notes |
|-------------|--------|-------|
| UK (Sale of Goods Act) | Low | 5 candidate rules exist, needs review |
| EU (GDPR / DSA) | High | New domain: data privacy |
| Singapore | Medium | Common law + Chinese law hybrid |
| Japan | High | Civil code with unique tort framework |

---

## Contribution Guide

1. Pick a domain from the roadmap above
2. Use `tools/distill_jurisdiction.py` as a 4-stage workbench
3. Add rules to the appropriate `configs/` directory
4. Add test cases to `tests/`
5. Submit a PR with benchmark results

**Rule**: Do NOT modify `compiler_core/evaluator.py`. All rule expansion happens via configuration files.

---

## Important Notes

1. **Rule sets are config-driven**: Do not modify the evaluator core. Use YAML configuration files.
2. **Alpha calibration**: `alpha=1.0` is a demo placeholder. Use `calibrate_theilsen()` with your historical timesheet data.
3. **Data privacy**: Sensitive data should be processed locally. The `./data/` directory is gitignored by default.
4. **Honest refusal**: Unsupported domains trigger `HONEST_REFUSAL` — this is by design, not a bug.
