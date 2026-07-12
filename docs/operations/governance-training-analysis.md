# Governance, training, and advisory analysis

## Governance

`jc rules audit <pack-id>` verifies the pack before producing a governance artifact. It may identify missing sources, duplicate IDs, dangling relations, invalid dates, invalid modality, or test-coverage gaps. It cannot edit a pack or promote a candidate.

## Training export

`jc training export <pack-id> --out <dir> --seed <n>` produces deterministic JSONL splits and a manifest from a verified corpus. Candidate-only rules remain represented. The command rejects pack configuration roots and does not read case audit bundles; exported data cannot promote rules.

## Missing facts and advisory output

Canonical results can include `missing_fact_review`: affected rules/claims, reason, permitted answer types, and conditions for formal fact admission. The graph represents possible influence separately from completed inference.

`jc analyze strategy` and `jc analyze similar-cases` read only a verified completed run. Their output is `ADVISORY`, requires review, cannot change the canonical result, and cannot create a formal certificate. Similar-case comparison requires an explicit versioned index; structural similarity does not predict a court outcome.

## Tri-rail

HK/US/PRC tri-rail remains an engineering harness. Without official reasoning-ready packs, it is review-only and reports `formal_kernel_used=false`. It is not a public case-conclusion service.
