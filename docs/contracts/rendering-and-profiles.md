# Rendering and neutral output

`jc evaluate` writes machine output and `graph.json`. Human-facing output is explicit:

```powershell
jc render --input artifact-handle.json --format markdown --audience agent --json
jc render --input artifact-handle.json --format mermaid --audience agent --json
jc render --input artifact-handle.json --format html --audience lawyer --json
```

Render first verifies the completed bundle. It consumes the canonical result and graph only; it does not load rules, construct an evaluator, or re-evaluate.

Rendered files live under `renders/<run>/<result-digest>/<profile-hash>/` with sidecar metadata binding renderer ID/version, profile hash, audience, format, content hash, warnings, and artifact references. They never modify the original bundle.

The public kernel ships one fixed neutral profile. Command-line, environment, and private-directory overrides are rejected. Profiles cannot hide or change status, claims, branches, sources, facts, certificates, checker state, risks, taint, review flags, or missing facts.

Mermaid maps existing graph nodes and edges only. HTML is opt-in, escapes content, and uses a local CSP without scripts or network resources. Personal lawyer style is not a JC core feature; any future implementation belongs downstream and cannot modify canonical output.

## Related documents

- [Audit bundle and replay](AUDIT_BUNDLE.md)
- [CLI reference](../guides/CLI.md)
- [Input and semantic boundary](INPUT_AND_SEMANTIC_BOUNDARY.md)
- [Documentation index](../README.md)
