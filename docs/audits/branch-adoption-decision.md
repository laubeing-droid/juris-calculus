# 历史分支裁决：codex/lmm-runtime-receipt

裁决日期：2026-08-16（W0）
裁决基线：`main@5b7bd00`，当前施工分支 `codex/jc-theory-absorption-plan@d9ec2fc`
依据：20260815 施工方案 §1.3、§6 动作 4 与 Gate。

## 分支事实

`codex/lmm-runtime-receipt` 比 `main` 多两个提交：

| 提交 | 主题 |
| --- | --- |
| `be60fc2` | feat: produce verified LMM refinement receipts |
| `ad26dcf` | docs: track JC upgrade construction plan |

裁决原则（方案 §1.3）：不自动 merge；逐文件判定移植 / 按当前合同重写 / 废弃；禁止为保留历史投入整枝合并。refinement fixture 未经独立 oracle 核对，不进入主线（§6 Gate）。

## 逐文件裁决

### commit be60fc2（runtime refinement receipt）

| 文件 | 裁决 | 理由与处置 |
| --- | --- | --- |
| `compiler_core/runtime_refinement.py` | REWRITE | 设计方向正确（消费状态无关 run binding、重放 audit bundle、签发内容寻址 v2 receipt），但建立在 v3 合同上。W8 建设 `RunIdentityV2`/receipt 分离时按 v4 合同重写；重写前不作为正式 authority。 |
| `compiler_core/cli.py`（+51 行 refinement receipt 子命令） | REWRITE | v4 施工后 CLI 由 `contracts_v4` + 稳定 exit code 重建入口；该子命令语义保留（receipt 查询），实现重写。 |
| `tools/run_lmm_refinement_fixture.py` | REWRITE | fixture 运行器；须改为对 v4 audit bundle 运行，并与独立 oracle 分离（不能同一函数生成与验证预期值，§11 动作 6）。 |
| `tests/fixtures/lmm_refinement/configs/**` | ADOPT-PENDING-ORACLE | 十案合成 fixture 暴露三处真实语义分歧；在独立 oracle 核对完成前仅允许作为审查材料，不进入主线测试断言。 |
| `tests/unit/test_runtime_refinement_receipt.py` | REWRITE | 断言绑定 v3 receipt 结构；随 runtime_refinement 重写迁移到 v4。 |
| `memory.md`（+18 行） | DROP | 工作区叙事文件；其结论已在本施工方案的基线章节中重新陈述，避免 stale narrative 随分支合并。 |

### commit ad26dcf（旧升级施工方案）

| 文件 | 裁决 | 理由与处置 |
| --- | --- | --- |
| `260810_juris-calculus重点升级施工方案.md` | DROP | 已被 `20260815_juris-calculus理论成果全量吸收施工方案.md` 全量取代；不合并，保留于分支历史即可。 |

## 工作区残留裁决

| 残留 | 性质 | 处置 |
| --- | --- | --- |
| `tests/fixtures/lmm_refinement/cases.json`（未跟踪，被 `*.json` 规则掩盖） | 分支检出残留的生成数据，分支上亦未提交 | 已移至 `build-artifacts/residual-lmm_refinement-from-codex-lmm-runtime-receipt/`（tracked tree 外），可由分支上的 `tools/run_lmm_refinement_fixture.py` 重新生成；不删除证据、不进入主线。 |

## 结论

- 不 merge `codex/lmm-runtime-receipt`；分支保留供 W8 重写时逐文件摘取。
- 所有 REWRITE 项在对应波次（W1 CLI、W8 receipt）落地前，不产生任何主线行为变化。
- ADOPT-PENDING-ORACLE 项必须先通过独立 oracle 核对（差分，不以修改期望值消除差异）才能进入 `tests/fixtures/theory_absorption/` 或主线断言。
