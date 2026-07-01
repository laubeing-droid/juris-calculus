# JC Spec Shadow Differential Report

Report type: runtime differential evidence.

This report summarizes the current spec-shadow fixture comparison. It is a runtime evidence artifact, not machine-checked coverage for every Python execution path.

## Summary

| Field | Value |
|---|---|
| status | PASS |
| fixture_count | 10 |
| aligned_count | 10 |
| diverged_count | 0 |

## Fixtures

| Fixture | Result |
|---|---|
| `contract_breach::plain` | ALIGNED |
| `contract_breach::force_majeure` | ALIGNED |
| `license_permission_priority::priority_on` | ALIGNED |
| `license_permission_priority::priority_off` | ALIGNED |
| `tort_breach::plain` | ALIGNED |
| `tort_breach::with_negligence` | ALIGNED |
| `criminal_breach::plain` | ALIGNED |
| `criminal_breach::self_defense` | ALIGNED |
| `admin_breach::priority_on` | ALIGNED |
| `admin_breach::priority_off` | ALIGNED |

## Interpretation

Aligned fixtures show that the selected JC runtime cases match the upstream specification boundary expectations for those fixtures. They do not prove the entire runtime.

Any future divergence must remain visible in this report or its generated successor.
