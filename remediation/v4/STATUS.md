# V4 remediation authoritative status

Updated: 2026-08-24

- Goal status: `ACTIVE`.
- Authoritative state root: `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state`.
- Current runner result: 51 tasks `COMPLETED`; only `H7-00=WAITING_EXTERNAL`.
- `H7-00` is a production-target capability gate. It requires evidence from the real target provider for the state provider, platform, encryption at rest, and SLO. It does not require an `authorized_reviewer`, and a user reply or test-only key cannot satisfy it.
- `H6-07` is not reached and is not an active blocker. Old request files are retained as history; `run.json` contains only the currently reached wait state.
- The local release-candidate MCP implementation is usable for candidate testing, but it is not evidence of a real production target and does not make `legal_production_ready=true`.
- All 44 audit IDs remain registered until the downstream target, remote-governance, production-validation, and Z00-Z03 tasks produce their required evidence.
- The single external ledger is `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state\external-ledger.json` (`sha256:eae4fcc7aebd4b3ad1fa3f798726851e677479f1e6577b35ca83a06a09cd3aab`).
- The prior bootstrap `B00 FAILED` / `B00-CG UNVERIFIED` / `B01 UNVERIFIED` status is superseded by the current receipt chain.
- Unique recovery command:

```powershell
py -3.12 -B D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\tools\remediate_v4.py run --plan D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\remediation\v4\tasks.json --state-root D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state --through W9
```
