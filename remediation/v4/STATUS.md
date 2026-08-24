# V4 remediation authoritative status

Updated: 2026-08-24

- Goal status: `ACTIVE`.
- Authoritative state root: `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state`.
- Current runner result: 56 tasks `COMPLETED`; only `H8-00=WAITING_HUMAN` is currently reached.
- The current Windows host is the authorized production target. `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-production-state` is directory-level EFS encrypted; H7-00 and W7-01..04 completed with content-bound receipts.
- Measured local target results: p50 `139.66 ms`, p95/p99 `150.57 ms`, throughput `7.15 operations/s`, RSS `102854656 bytes`, artifact growth `36864 bytes/run`; all are within the declared single-user local budgets.
- `H8-00` now requires the selected immutable first-party China-law source inventory and an `authorized_reviewer` cryptographic approval. No source/reviewer/signature has been fabricated.
- `H6-07` is not reached and is not an active blocker. No push, tag or remote release occurred.
- The local release-candidate MCP and the production storage target are verified separately; `legal_production_ready` remains false until cn-official, signing, DSH and final Z gates complete.
- All 44 audit IDs remain registered until the downstream target, remote-governance, production-validation, and Z00-Z03 tasks produce their required evidence.
- The single external ledger is `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state\external-ledger.json` (`sha256:d6d333083207322d7bfeeac0722df2124cd08d477cdea7be67685bad0fbdb130`).
- The prior bootstrap `B00 FAILED` / `B00-CG UNVERIFIED` / `B01 UNVERIFIED` status is superseded by the current receipt chain.
- Unique recovery command:

```powershell
py -3.12 -B D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\tools\remediate_v4.py run --plan D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\remediation\v4\tasks.json --state-root D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state --through W9
```
