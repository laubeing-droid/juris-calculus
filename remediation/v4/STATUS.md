# V4 remediation authoritative status

Updated: 2026-08-22

This file supersedes the bootstrap status emitted by commit `a881f2827b9112e98f500bab5200c6db20cb7ebf`.

- Goal status: `ACTIVE`.
- `B00`: `FAILED`. `tools/remediate_v4.py run` did not execute the task DAG and hard-coded completed phases.
- `B00-CG`: `UNVERIFIED`. Existing CodeGraph reports remain observations only; all closure and `CONFIRMED` claims require reconstruction against the current commit and tree.
- `B01`: `UNVERIFIED`. Tracked-path enumeration may be reused as input, but every disposition, terminal state, and closure task requires semantic review.
- The 12 requests under `C:\Users\being\AppData\Local\Temp\jc_remediation_state` are `INVALID_SUPERSEDED`. They were not reached through the DAG, their subject digests were not bound to actual review artifacts, their baseline drifted, and the runner did not verify or consume approvals.
- The old state root is retained unchanged. Its invalidation manifest records 22 files, 211,469 bytes, and aggregate manifest SHA-256 `44bf0b3b7902f17ad8d354528e0078aef904e67fa91f919e0f22c4fac9ac59e1`.
- Authoritative state root: `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state`.
- Unique recovery command:

```powershell
py -3.12 -B D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\tools\remediate_v4.py run --plan D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\remediation\v4\tasks.json --state-root D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state --through W9
```

No gate request is valid until the rebuilt runner reaches that task in `WAITING` state and binds the request to the actual subject artifact.
