# Rule packs and rule schema

A signed V4 rule-pack manifest binds pack identity, jurisdiction, governing dates,
source snapshots, exact rule/config references, release evidence, and signature.
Pack admission occurs inside the V4 application; the CLI has no separate mutable
pack-management command.

```powershell
python -B tools/build_cn_official_pack.py --source source-candidate.json --output candidate-bundle.json
```

## Admission

JC keeps two sets:

- **corpus:** retained material for cleaning, lookup, governance, and training export;
- **reasoning-eligible:** rules with explicit source anchors that pass integrity and admission checks.

Rules without a verified authority remain `UNVERIFIED` and `CANDIDATE_ONLY`. JC never infers a source anchor from a rule name or description. Governance may report blockers; it never promotes a rule automatically.

The builder can emit an unsigned `cn-official` candidate bundle from explicit
first-party source input. It cannot sign or promote that bundle. Legacy corpora are
absent from the current runtime and are not formal fallbacks.

## Rule fields

A rule requires a stable ID, modality, conclusion, premises, source metadata, and admission metadata. Optional attack, exception, permission, priority, dates, and jurisdiction fields must be structurally valid when present. Duplicate IDs, invalid modality, invalid dates, missing required source anchors for admission, and dangling references fail validation.

The authoritative machine schema is the packaged `schemas/jc-v4.schema.json`; the
runtime contracts and validation tests are the implementation authority.
