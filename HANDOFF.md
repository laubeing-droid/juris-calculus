# `juris-calculus` V4 remediation handoff

Status date: 2026-08-24 (Asia/Shanghai)

## Current state

The current source and package version is 4.0.0rc1. The local V4 kernel, deterministic build, installed-wheel gates, SBOM, checksums, and test-only signed provenance are implemented. Remote production promotion is not completed.

The exact Git commit, tree, command streams, test reports, and artifact digests are authoritative only in the append-only remediation receipts. Prose does not replace those receipts.

## External boundary

The public GitHub repository currently has no ruleset and `main` branch protection is not enabled. Production promotion still requires:

1. protected branch/tag and required-check governance;
2. approval of the protected `release` environment;
3. an authorized production Ed25519 release-attestor key;
4. an exact tag resolving to the tested wheel source commit;
5. separate source/legal/engineering approvals before any `cn-official` promotion;
6. separately authorized production deployment.

The workflows in `.github/workflows/ci.yml` and `.github/workflows/auto-release.yml` encode the build-once/promotion boundary, but committing workflow code does not satisfy any external gate.

## Resume and verify

The governed remediation runner is `tools/remediate_v4.py`; the current task plan is `remediation/v4/tasks.json`. Use the absolute state-root command recorded in `remediation/v4/STATUS.md`.

Focused current checks:

```powershell
python -B tools/remediate_v4.py verify-wave W0-04
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests/packaging
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests/formal_e2e tests/mcp_protocol tests/security
python -B mcp_server.py --test
git diff --check
```

Historical V3 replay is isolated under `docs/operations/V3_HISTORICAL_REPLAY.md`; it is not a current API, schema, runtime, or migration route.
