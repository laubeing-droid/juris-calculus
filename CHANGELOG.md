# Changelog

## 4.0.0 — Local production

### Runtime boundary

- Public CLI, Python, MCP, schema, application, certificate, verify, and replay surfaces are V4-only.
- V3/W1b adapters, caller-trusted shortcuts, duplicate authorities, and legacy rule fallback were removed from the current tree and wheel.
- `configs/zh_CN/rules.yaml` and the `cn-legacy-corpus` manifest were retired with history-bound evidence; no content was promoted into `cn-official`.

### Evidence and packaging

- Required tests are governed by `tests/required-v4-tests.json` with zero required skip/xfail bypass.
- Hash-locked build, runtime, test, and release profiles drive a byte-identical A/B wheel build and repository-outside installed-wheel tests.
- `tools/build_provenance.py` binds the exact wheel, RECORD, runtime SBOM, source commit/tree, schema, tool contract, authority registry, trust material, and locks.
- `.github/workflows/ci.yml` builds once; `.github/workflows/auto-release.yml` only promotes that exact artifact after tag, production signature, environment, and governance checks.

### Not yet promoted

- Local Windows/EFS production uses the installed-wheel runtime, active profile registry, and bounded `cn-official-local` pack. No remote release or external DSH deployment is claimed.
- Test-only provenance is explicitly `TEST_ONLY_NOT_PROMOTABLE`.

## Historical lines

V3.0.2 and older interfaces are retained only in frozen historical artifacts. See `docs/operations/V3_HISTORICAL_REPLAY.md`; it is not current runtime authority.
