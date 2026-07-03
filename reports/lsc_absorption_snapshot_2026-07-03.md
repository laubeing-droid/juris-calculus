# LSC Absorption Snapshot 2026-07-03

## Repository Snapshot

| Repository | Path | Branch | Git HEAD | Dirty state |
|---|---|---|---|---|
| JC target | `D:\Codex\juris-calculus` | `main` before work, then `codex/lsc-boundary-absorption` | `685399546c3d00b15b72f2d9db8ddd378e6d98c7` | clean before work |
| LSC source | `D:\Codex\Legal Skill Calculus 全量摸底与数学化落地` | `master` | `c2c2a136117fd4c904b27d0814316e19e5e48b5a` | dirty: deleted `Legal_Skill_Calculus_Handoff_2026-07-01.md`, deleted `Legal_Skill_Calculus_Implementation_Prompt_2026-07-01.md`, untracked `新建文件夹/` |
| legal-math-modeling spec | `D:\Codex\数学证明\legal-math-modeling` | `master` | `0f37aea2a7c9740374d27a07ad9b59b3266fce24` | clean |
| Deli orchestration | `D:\Codex\数学证明自动研究` | `main` | `742300a6cb87e8268da3cb0c92dda7875e1911f1` | clean |

## Baseline Counts

- LSC source file count: 784.
- JC workflow files present: `.github/workflows/ci.yml`, `.github/workflows/auto-release.yml`.
- JC remote: `origin https://github.com/laubeing-droid/juris-calculus.git`.

## Baseline Verification

| Command | Result |
|---|---|
| `python mcp_server.py --test` | passed locally; 33 tools and 12 resources loaded |
| `pytest tests/unit/test_agent_protocol.py tests/unit/test_anti_degradation.py -v --tb=short` | blocked before migration changes: direct `pytest` collection could not import top-level `tools` package |

## Boundary Commitment

This migration does not copy LSC business objects. In particular, it does not copy the LSC 36-object layer, Deadline/Fee/Interest/Jurisdiction/Citation tools, LSC AgentSkill, CLI/API wrappers, Chinese-law concrete rules, or any P1/P2 substantive judgment into JC.

