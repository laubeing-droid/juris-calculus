# V4 build-once release and promotion

The current package version authority is `compiler_core/version.py`; the release tag must be exactly `v4.0.0rc1` while that authority remains unchanged. The public contracts are `schemas/jc-v4.schema.json` and `mcp_manifest.json`.

## Local release candidate

`.github/workflows/ci.yml` runs the required Ubuntu/Windows Python matrix, static gates, two clean source builds, byte comparison, installed-wheel suites, SBOM generation, and test-only provenance. It uploads both byte-identical wheels and the reports as one commit-addressed artifact.

The committed fixture key can create only a release candidate. Its provenance status is `TEST_ONLY_NOT_PROMOTABLE`; `tools/build_provenance.py` rejects that key in production verification unless the caller explicitly opts into test verification.

## Production promotion

`.github/workflows/auto-release.yml` is callable only from the completed CI run. It downloads that run's exact artifact and does not build a wheel. Before `gh release create`, it requires all of the following:

1. the GitHub ref is a tag and resolves to the caller commit;
2. tag, package metadata, CLI/MCP version, and `RunIdentityV4` share the version authority;
3. the A/B wheels are still byte-identical;
4. a protected `release` environment supplies `JC_RELEASE_ED25519_KEY_JSON`;
5. the key is production-authorized Ed25519 material, not the test fixture;
6. production provenance verifies with `--require-tag-ref` and without `--allow-test-key`;
7. repository branch/tag rules, required checks, review policy, and retention are enabled externally.

Local workflow files cannot prove item 7, cannot create a production key, and cannot impersonate a release approver. Until those external conditions are real, production release is not authorized.

`cn-official` has a separate legal promotion boundary. No engine release makes candidate, OCR, textbook, case, or retired legacy material an official legal source.
