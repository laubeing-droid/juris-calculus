# Rule packs and rule schema

A rule-pack manifest binds pack ID, version, jurisdiction, kind, status, governing dates, resource hashes, source commit, content digest, and inventory. Query current state; do not copy inventory counts into prose.

```powershell
jc packs list --json
jc packs verify --all --json
jc rules audit <pack-id> --json
```

## Admission

JC keeps two sets:

- **corpus:** retained material for cleaning, lookup, governance, and training export;
- **reasoning-eligible:** rules with explicit source anchors that pass integrity and admission checks.

Rules without a verified authority remain `UNVERIFIED` and `CANDIDATE_ONLY`. JC never infers a source anchor from a rule name or description. Governance may report blockers; it never promotes a rule automatically.

`cn-official` is intentionally blocked until official first-party source snapshots exist. Legacy CN, HK, and US corpora are not formal fallbacks.

## Rule fields

A rule requires a stable ID, modality, conclusion, premises, source metadata, and admission metadata. Optional attack, exception, permission, priority, dates, and jurisdiction fields must be structurally valid when present. Duplicate IDs, invalid modality, invalid dates, missing required source anchors for admission, and dangling references fail validation.

The authoritative machine schema is the packaged `schemas/jc-v3.schema.json`; the runtime contracts and validation tests are the implementation authority.
