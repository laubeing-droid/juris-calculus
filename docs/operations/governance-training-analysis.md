# Governance, training, and advisory analysis boundary

The public `jc` CLI does not expose `rules`, `training`, or `analyze` commands. Its
current command surface is `capabilities`, `evaluate`, `verify`, `replay`,
`read-artifact`, and `render`.

## Non-production assets

Repository governance reports, corpus tooling, training-export experiments, advisory
analysis, and tri-rail fixtures are offline source or test assets. They are not public
runtime entrypoints and must not be described as installed CLI capabilities.

These assets may identify missing sources, duplicate identifiers, invalid relations,
coverage gaps, missing facts, or candidate similarities. They cannot edit or promote a
rule pack, change a canonical result, issue a formal certificate, or predict a court
outcome. Candidate material remains non-reasoning unless it passes the formal rule-pack
admission and promotion boundary.

## Missing facts

Canonical results may include structured missing-fact data and review-only branches.
That output records what prevents a formal conclusion; it does not silently convert
unknown, disputed, or user-assumed material into verified facts.

## Related documents

- [CLI reference](../guides/CLI.md)
- [Rule packs](../contracts/RULE_PACKS.md)
- [Input and semantic boundary](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)
- [Documentation index](../README.md)
