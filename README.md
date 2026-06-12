# juris-calculus v2.0.0

Symbolic legal reasoning engine for Chinese law, with addon-based cross-jurisdiction support.

## Architecture

```
  Layer 0: juris_blueprint.json (14 CN MoE domains)
  Layer 1: Trust labels (epistemic status)
  Layer 2: Horn clause fixpoint evaluator (2,117 CN rules)
  Layer 3: MoE rule router + stratified evaluator
  Layer 4: Adversarial pipeline (Reasoner/Auditor/Verifier)
  Layer 5: Dung AAF argumentation + step verifier (EVM)
  Layer 6: Neural leaf nodes (kill switch + cold start)

  addons/             <-- optional jurisdiction plugins
    hk/               Hong Kong SAR (Cap 26, 364 Horn rules)
    us/               United States (UCC, 53 Title index, 266 courts, 419 federal terms)
    federation/       Common-law pair-wise comparison engine
```

## Core vs Addons

The core engine is **China-law only**. All other jurisdictions are optional addons
loaded via `plugin_registry.discover()`. No HK/US code is imported by core modules.

```python
from compiler_core.plugin_registry import registry
registry.discover()  # auto-scans addons/ directory
adapter = registry.get("hk")  # None if addon not installed
```

## Jurisdiction Coverage

| Jurisdiction | Rules | Legal Family | Status |
|-------------|-------|-------------|--------|
| CN (PRC) | 2,117 Horn rules, 14 MoE domains | Civil Law | Core (always loaded) |
| HK | 364 Horn rules (Cap 26/32/33/4A/571/6/622) | Common Law | Addon |
| US | 53 Title index + 266 courts + 419 federal terms | Common Law | Addon |

## MCP Tools (v2.0.0 manifest)

| Tool | Description |
|------|-------------|
| `trirail_collide` | HK x US x PRC collision detection |
| `check_threat` | FastPathInterceptor gateway |
| `generate_memo` | Partner-ready cross-border memo |
| `route_state` | Jurisdiction router |
| `get_citation` | Legal citation lookup |
| `stratified_evaluate` | 4-stage Horn + AAF pipeline |
| `claims_detail` | Claims with trust labels |
| `blueprint_query` | Query juris_blueprint.json |
| `neural_status` | Cold-start status report |
| `adversarial_audit` | Reasoner/Auditor/Verifier pipeline |

## Quick Start

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
pytest tests/          # 43 tests
python mcp_server.py   # MCP stdio server
```

## Personal YAML (Multi-Lawyer Sharing)

Set `JURIS_CONFIG_DIR` to point at your personal YAML library.
Same algorithm code, different per-lawyer rule distillation.

```bash
export JURIS_CONFIG_DIR=/path/to/my-yaml
```

## Development

```bash
pytest tests/ -v              # unit + smoke tests
python -c "import compileall; compileall.compile_dir('.')"
python scripts/ingest_state_terms.py --list
```

## License

MIT
