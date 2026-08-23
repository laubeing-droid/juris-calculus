# V3.0.2 historical replay isolation

This page is an artifact locator and recovery procedure only. It is not current schema, API, runtime, migration, or legal-source authority. Current JC processes must not discover, load, clean, migrate, or fall back to V3 state.

## Frozen identity

| Item | Frozen value |
| --- | --- |
| Annotated tag | `v3.0.2` / tag object `b2087e18a4bdbb884a04e36f12cab300f1c322dd` |
| Commit | `aa0e038daf066bfc0baa4d27ee54adef12c3ae16` |
| Tree | `64b2af1036582269341bd0423a9d2eb5f92e560a` |
| Source date epoch | `1783877180` |
| Replay environment | CPython 3.12 / Windows x86-64 / network disabled |
| Source archive | `juris-calculus-v3.0.2-source.zip`, 2,744,951 bytes, `sha256:2b429ff7e5988bab66f8dd55114c34ea59a9e998ab741a5164eb8b48f0a5dff6` |
| Replay wheel | `juris_calculus-3.0.2-py3-none-any.whl`, 2,608,509 bytes, `sha256:2c76be31a121e68135b6c81dd1572d45feb207696869484da839a0db3c93388e` |
| Contract inputs | 13 files / 51,601 bytes / inventory `sha256:04cd31f9b06ddc5f71ad7ceea76fc1b76af28f6e29b7e159a50ad383c3035974` |
| Offline wheelhouse | 11 wheels / 3,050,541 bytes / inventory `sha256:97a0ae4b6b04c2777bb281491cd9f21d06277bff7584d53e5892fbf33a974fab` |
| Pack/schema resources | 35 wheel blobs / 14,384,357 bytes / inventory `sha256:06250b3e51f37de08fcfa3832f6f9d814b5db310f5c49cd0afc4efc6449870d1` |
| Replay tests | 3 files / 25,212 bytes / inventory `sha256:a5120552d5eff023243ebda30fabadf7743f3cf456835507225eaac9f3392d50` |

The replay wheel is `LOCAL_REPLAY_BUILD_NOT_RELEASE_ASSET`: it was built locally from the exact tag with `setuptools==83.0.0`, `wheel==0.47.0`, `SOURCE_DATE_EPOCH=1783877180`, and the frozen locks. The GitHub release had no wheel asset when this bundle was frozen on 2026-08-23; do not describe this wheel as an upstream release asset.

The bundle locator is:

```text
$JC_REMEDIATION_STATE_ROOT/evidence/W5-07/frozen-v3.0.2-v1
```

`source/` contains the exact tag checkout and its five lock profiles, contracts, schema, and manifests. `wheelhouse/` is the no-network environment. `artifacts/` contains the replay wheel. `replay-tests/` contains the exact tag test that performs evaluate, successful replay, render, then a missing-pack replay failure.

## Isolated no-network replay

Run outside every JC source checkout. The command creates a fresh environment, installs only from the frozen wheelhouse, and executes the frozen V3 test from the external bundle:

```powershell
$Bundle = Join-Path $env:JC_REMEDIATION_STATE_ROOT 'evidence\W5-07\frozen-v3.0.2-v1'
$ReplayEnv = Join-Path $env:TEMP ('jc-v3.0.2-replay-' + [guid]::NewGuid().ToString('N'))
py -3.12 -B -m venv $ReplayEnv
$ReplayPython = Join-Path $ReplayEnv 'Scripts\python.exe'
$env:PIP_NO_INDEX = '1'
$env:PYTHONNOUSERSITE = '1'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
& $ReplayPython -B -m pip install --no-index --find-links (Join-Path $Bundle 'wheelhouse') PyYAML==6.0.3 pytest==9.1.1
& $ReplayPython -B -m pip install --no-index --no-deps (Join-Path $Bundle 'artifacts\juris_calculus-3.0.2-py3-none-any.whl')
Push-Location (Join-Path $Bundle 'replay-tests')
& $ReplayPython -B -m pytest -q -p no:cacheprovider --basetemp (Join-Path $ReplayEnv 'pytest') 'tests/unit/test_cli_evaluate_subprocess.py::test_cli_evaluate_writes_bundle_then_replay_passes'
Pop-Location
```

The W5-07 machine gate repeats this replay in another fresh environment and emits a content-addressed receipt. Its frozen case identity is `sha256:1290d07c92fa311a25760904e34e4721df56aa488996fe1e446a06de68d14889`.

## Existing V3 run/cache custody

Registered V3 run and pack-cache roots remain read-only historical records. Do not point V4 at them and do not delete or migrate them. To inspect one, make a bounded throwaway copy of the exact registered run plus its exact registered pack cache, verify the registry fingerprints, and give only that copy to the isolated V3 environment. Never fill a missing blob from the current repository, another pack, `cn-official`, a different V3 cache, or a V4 state root.

Two failures are intentional and distinct:

- If a frozen bundle file is absent or its digest differs, the W5-07 gate stops with `V3_REPLAY_MATERIAL_MISSING` or `V3_REPLAY_MATERIAL_DRIFT`; it does not download a replacement.
- If the historical run's exact pack material is absent, V3 replay exits `6` with `REPLAY_MATERIAL_MISSING`; it does not evaluate again or fall back.

The retired current-tree guides remain locatable only by Git blobs `66070f1b28f5658e0e380dbff480556b624b110a` (`MIGRATION_V2_TO_V3.md`) and `028df6c25bc8a8896f02d2c49a19b0255cac64f5` (`WORKBUDDY.md`). Git history and this frozen bundle are sufficient; no compatibility code or automatic migration command is provided.
