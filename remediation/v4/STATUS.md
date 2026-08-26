# V4 remediation authoritative status

Updated: 2026-08-26

This page is the human-readable projection of the completed remediation run. The
external append-only receipts remain authoritative for exact commands, digests, and
timestamps.

## Current result

- Runner `0.60.0` completed all 92 tasks through `Z10-03`; no task remains incomplete.
- The final result is `LOCAL_PRODUCTION_ACTIVE` with `exit_code=0` for the bounded
  Windows/EFS deployment covering《中华人民共和国个人信息保护法》第十三至十八条。
- The installed runtime source commit is
  `91daa6658dcd555d02199d91f16fe49bf0b5ba09`.
- The active local pack is `cn-official-local`. It is a bounded local-production pack,
  not the remotely promoted public `cn-official` pack.
- Independent human review is not claimed. Observation remains required for the
  local deployment.
- No push, tag, remote release, or external production promotion is claimed.

The retained `goal.json` and `external-ledger.json` are pre-W10 workflow snapshots.
For current completion state, use `run.json` and the final Z10 result evidence.

## Resume and verify

Set `JC_REMEDIATION_STATE_ROOT` to the existing external remediation-state directory,
then run the single governed entrypoint from the repository root:

```powershell
python -B tools\remediate_v4.py run --through Z10-03
```

A successful no-op verification prints the plan summary and exits `0`. Digest or
receipt drift exits nonzero and must not be described as production completion.

## Related documents

- [Release boundary](../../docs/operations/RELEASE_V4.md)
- [Audit-bundle contract](../../docs/contracts/AUDIT_BUNDLE.md)
- [Operator handoff](../../HANDOFF.md)
- [Documentation index](../../docs/README.md)
