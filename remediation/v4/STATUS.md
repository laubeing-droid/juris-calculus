# V4 remediation authoritative status

Updated: 2026-08-24

- Goal status: `ACTIVE`.
- Authoritative state root: `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state`.
- Current runner result: 59 tasks `COMPLETED`; only `H8-03=WAITING_HUMAN` is currently reached.
- The current Windows host is the authorized production target. `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-production-state` is directory-level EFS encrypted; H7-00 and W7-01..04 completed with content-bound receipts.
- The latest volatile measurements are authoritative in state evidence `evidence/W7/target/W7-02.json`; p50/p95/p99, throughput, RSS, and artifact-growth checks all pass the declared single-user local budgets.
- `H8-00`, `W8-01`, and `W8-02` completed for《中华人民共和国个人信息保护法》第十三至十八条。The inventory binds all 74 articles: 6 typed candidates and 68 explicit omissions, with no legacy-corpus dependency.
- The exact `candidate-bundle.json` (`sha256:4b1424c4bb334d3d7c1f165c2cad270905ddae39f9cdd1a666799679b4050002`) and `review.md` (`sha256:3644d55a0e14a4cad60271234bc04528e5d75f2ac77cf7d90716f1f46ebb2f51`) are candidate-only and await the two distinct legal reviews requested by `H8-03`. No reviewer/signature has been fabricated.
- `H6-07` is not reached and is not an active blocker. No push, tag or remote release occurred.
- The local release-candidate MCP and the production storage target are verified separately; `legal_production_ready` remains false until cn-official, signing, DSH and final Z gates complete.
- All 44 audit IDs remain registered until the downstream target, remote-governance, production-validation, and Z00-Z03 tasks produce their required evidence.
- The single external ledger is `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state\external-ledger.json`; it points to the current H8-03 request and is updated outside Git.
- The prior bootstrap `B00 FAILED` / `B00-CG UNVERIFIED` / `B01 UNVERIFIED` status is superseded by the current receipt chain.
- Unique recovery command:

```powershell
py -3.12 -B D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\tools\remediate_v4.py run --plan D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\remediation\v4\tasks.json --state-root D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state --through W9
```
