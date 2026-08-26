# `juris-calculus` V4 handoff

Status date: 2026-08-26 (Asia/Shanghai)

## Current checkpoint

The 4.0.0 remediation run completed all 92 tasks through `Z10-03`. The external
final result records `LOCAL_PRODUCTION_ACTIVE` and `exit_code=0` for the bounded
Windows/EFS deployment covering《中华人民共和国个人信息保护法》第十三至十八条。
The deployed runtime source commit is
`91daa6658dcd555d02199d91f16fe49bf0b5ba09` and its active local pack is
`cn-official-local`.

The exact command streams, receipts, artifacts, and digests remain authoritative in
the external remediation-state directory. See the repository projection in
[remediation/v4/STATUS.md](remediation/v4/STATUS.md).

## Remaining boundary

- Observation is still required; independent human review is not claimed.
- `cn-official-local` does not imply remote promotion of the public `cn-official`
  pack.
- No push, tag, GitHub release, or external production promotion is claimed.
- Any remote release remains subject to the separately governed release process in
  [docs/operations/RELEASE_V4.md](docs/operations/RELEASE_V4.md).

## Resume and verify

From the repository root, set `JC_REMEDIATION_STATE_ROOT` to the existing external
state directory and run:

```powershell
python -B tools\remediate_v4.py run --through Z10-03
```

The runner validates the receipt chain before returning success. Historical V3 replay
is isolated under [docs/operations/V3_HISTORICAL_REPLAY.md](docs/operations/V3_HISTORICAL_REPLAY.md)
and is not a current API, schema, runtime, or migration route.
