# juris-calculus Concept Roadmap

Concepts not yet formalized in the rule registry. Ordered by priority for community contribution.

**Contributor Guidelines**: Contributions that propose a symbolic logic representation for any item in the Roadmap are welcome. Please ensure your rule set is unit-tested against at least 5 court-filed complaints, with benchmark results included in the PR.

---

---

## v1.0 Core (Supported)

| Domain | Concepts | Status |
|--------|---------|--------|
| UCC Article 2 (Sales) | ContractFormed, GoodsDelivered, PaymentDue, Breach, Damages, ForceMajeure | ✅ Implemented |

## v1.1 Equitable Remedies (Priority: P0)

| Domain | Concepts | Difficulty | Community |
|--------|---------|-----------|-----------|
| Specific Performance | SpecificPerformanceClause, IrreparableHarm, InadequateLegalRemedy | Medium | Open for PR |
| Material Adverse Effect | MAE_Clause, MAE_Triggered, MAE_Duration | Medium | Open for PR |
| Pretextual Termination | PretextualTermination, BadFaith, SubjectiveIntent | High | Research needed |

*Target: configs/en_US/equitable_remedies.yaml*

---

## v2.0 Tort & Civil Wrongs (Priority: P1)

| Domain | Case | Concepts | Difficulty |
|--------|------|---------|-----------|
| Negligence | US-REAL-002 | DutyOfCare, BreachOfDuty, Causation, ActualInjury, ConstructiveNotice | Medium |
| Fraud | US-REAL-008 | Misrepresentation, Scienter, JustifiableReliance, FraudulentScheme | High |
| Trade Secrets | US-REAL-006 | TradeSecretExists, ConfidentialityObligation, Misappropriation | Medium |

---

## v2.0 Regulatory & Statutory (Priority: P1)

| Domain | Case | Concepts | Difficulty |
|--------|------|---------|-----------|
| Employment Discrimination | US-REAL-003 | AdverseAction, ProtectedClass, DisparateTreatment, PretextAlleged | High |
| Securities (Howey Test) | US-REAL-005 | HoweyTest_Investment, HoweyTest_CommonEnterprise, HoweyTest_ProfitExpectation | Extreme |
| Antitrust (Sherman §2) | US-REAL-007 | MarketPower, ExclusionaryConduct, AnticompetitiveEffects, RelevantMarket | Extreme |

---

## v3.0 Constitutional & Equitable (Priority: P2)

| Domain | Case | Concepts | Difficulty |
|--------|------|---------|-----------|
| First Amendment | US-REAL-010 | ProtectedSpeech, GovernmentCoercion, ChillingEffect, StateAction | Extreme |
| Class Action (Rule 23) | US-REAL-004 | DataBreach, ClassCertification, Commonality, Numerosity | Extreme |
| RICO | US-REAL-008 | PatternOfRacketeering, Enterprise | Extreme |
| FRAND / Patent | US-REAL-009 | PatentOwnership, FRANDCommitment, LicensingDispute | High |
| Fiduciary Duty | US-REAL-004 | FiduciaryRelationship, DutyBreached | Medium |

---

## Contribution Guide

1. Pick a concept from the roadmap above
2. Create a ruleset YAML in `configs/en_US/`
3. Add corresponding test cases to `tests/us_complaints/roadmap/`
4. Submit a PR with the benchmark result diff

**Rule**: Do NOT modify `compiler_core/evaluator.py`. All rule expansion happens via configuration files.
