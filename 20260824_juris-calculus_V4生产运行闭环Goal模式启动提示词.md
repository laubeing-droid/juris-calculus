# juris-calculus V4 生产运行闭环 Goal 模式启动提示词

> **已归档：** 本文仅保留历史启动指令，不描述当前运行状态。当前信息见[状态页](remediation/v4/STATUS.md)与[文档索引](docs/README.md)。

进入 Goal/目标模式，直接接管并完成 juris-calculus V4 本机生产运行闭环整治。不要再写新方案、重复审计或讨论授权；按照已经批准的正式施工方案实施、测试、提交、运行并激活本机生产。

## Goal

在当前 Windows 主机上，把 juris-calculus V4 从现有代码状态一次性施工到：

```text
exit_code=0
status=LOCAL_PRODUCTION_ACTIVE
scope=local-windows-efs-pipl-articles-13-18
```

Goal 在上述终态及全部 Z10 证据真实成立前保持 active。可修复的软件、测试、依赖、环境配置和迁移错误必须由你自主定位、修改、重试，不得转成授权门禁、人工复核门禁或交给用户排查。

## 工作区

```text
主仓库：D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus
整治 worktree：D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation
整治分支：v4-remediation
当前已知 HEAD：d71c136 feat(remediation): deploy local stdio production profile
生产 state root：D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state
正式施工方案：D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation\20260824_juris-calculus_V4生产运行闭环彻底整治施工方案.md
方案 SHA-256：FBFB9AE0D2DB18AEB91662D2DDA2D843BA998C0A6020695CD5487087832D695E
```

只在整治 worktree 和上述生产 state root 内施工。主仓库只做只读状态核对，不覆盖主工作树中的用户改动。

## 已有授权一次性生效

用户已经授权，不得再次询问：

1. 修改、增加、删除正式施工方案 exact-path 矩阵覆盖的源码、测试、schema、manifest、配置、文档、任务 DAG、verifier、fixture 和 lockfile。
2. 将当前未跟踪的正式施工方案和本启动提示词加入整治分支并提交。
3. 执行 pytest、lint、type check、build、wheel 安装、CodeGraph、迁移、tamper/chaos/performance/security 测试和生产 E2E。
4. 创建必要的本地原子提交；每个 W10 任务按方案形成可回滚提交。
5. 在生产 state root 创建目录，启用并复验目录级 EFS，创建本机生产运行密钥、服务密钥、profile、release、venv、备份和恢复演练目录。
6. 以 `LOCAL_AUTOMATED_OWNER` 对既有六条 PIPL 第 13—18 条规则执行机器生产验收、签发、激活和观察运行。
7. 创建本机每日 EFS 备份任务计划，执行 status、backup、restore rehearsal、upgrade、rollback、revoke 等方案内运维动作。
8. 对当前范围内的错误实现、旧空壳 gate、重复 verifier、legacy consumer 和失效声明直接修复、失效或删除。

明确不做且仅不做：

- 不启用整盘 BitLocker；
- 不 push、不创建远程 tag/GitHub Release、不远程发布；
- 不部署远程服务；
- 不虚构外部 reviewer、DSH、第二签发人或第三方法律批准。

上述排除项不得阻止本机生产投产。`independent_human_review=false` 是本机观察生产的诚实状态字段，不是 `BLOCKED`、`WAITING_EXTERNAL` 或拒绝激活的条件。不得使用 test-only key 冒充生产密钥；应在 EFS state root 内自动创建并使用真实的本机生产运行密钥。

## 强制执行方式

1. 当前任务由主智能体直接完成；禁止创建子智能体、新任务或并行审查线程。
2. 不要先复述方案，不要输出长篇状态报告，不要请求“是否继续”。
3. 先核对 worktree branch/HEAD/status、方案 hash、现有 DAG/receipt 和 state root；发现与已知 HEAD 不同，以当前未被篡改的整治分支实际状态为准继续施工，不回退用户成果。
4. 将正式施工方案作为唯一施工合同。此前 W1-04、W9、Z 或旧 receipt 中与本方案冲突的完成声明，以 W10-00 的 append-only supersession 处理，不改写历史 evidence。
5. 不要一开始盲跑尚未实现的任务然后以报错结束。先把 `tasks.json`、runner、各 W10 实现及 verifier 补齐到可执行状态，再由同一 runner 连续执行。
6. 唯一生产整治入口必须收敛为：

```powershell
$env:JC_REMEDIATION_STATE_ROOT='D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state'
python -B tools\remediate_v4.py run --through Z10-03
```

7. W10-00 → W10-10 → Z10-00 → Z10-03 全部为 `AUTO`，严格依赖顺序执行；不得生成 `HUMAN_GATE`、approval request、reviewer request、activation proposal 或逐项确认 ledger。
8. 每个任务失败时读取真实 stdout/stderr 和测试结果，定位根因，做最小必要修改并重跑；禁止用 stub、mock PASS、固定 completed phase、仅文件存在、仅 schema 通过或空参数拒绝冒充完成。
9. 优先复用现有模块、Python 标准库和现有依赖。禁止为本轮再造第二主链、第二 runner、第二 bridge、额外确认系统或多层自我审计框架。
10. 每个 W10 任务验证通过后本地提交，再继续下一任务；普通修改、测试、lockfile 和本地提交均不暂停询问。
11. runner 必须支持从最新有效 receipt 恢复。同一命令重跑时继续未完成任务，不重复破坏已验证的 release 或 current state。
12. restore rehearsal 只在独立目录复验；需要回滚且验证成功时由 lifecycle 工具自动原子切换，不等待人工选择。生产 activation 由验证成功后的自动事务完成。

## 必须完成的任务链

严格实施正式施工方案中的全部任务，不得缩成 MVP：

```text
W10-00  失效旧的壳式生产完成声明
W10-01  完整且有界的 CaseInputBundle 合同
W10-02  每案 resolver overlay 隔离和清理
W10-03  production pack/trust/key/current-time loader
W10-04  完整 production composition root
W10-05  CLI、Python Client、stdio MCP 三入口统一
W10-06  正式 jc-formal bridge 和 active profile registry
W10-07  installed-wheel immutable production release
W10-08  六条 PIPL 真实生产 E2E 和原子激活
W10-09  status/backup/restore/upgrade/rollback/revoke 与任务计划
W10-10  逐任务独立 verifier、receipt 和恢复闭环
Z10-00  全仓、DAG、文件/问题地图和发布物复算
Z10-01  新进程 installed-wheel artifact/run 独立复验
Z10-02  Git、EFS、安装、权限、备份和运维终检
Z10-03  唯一最终生产结果
```

正式方案列明的功能、测试、迁移、exact paths、提交边界、回滚点和验收条件全部是本 Goal 的必做范围。“实现了大部分”“release candidate”“等 reviewer”“先观察再激活”均不是完成。

## 生产完成判定

只有真实满足以下条件才能把 Goal 标记 complete：

1. 唯一 runner 实际执行至 Z10-03，进程 `exit_code=0`。
2. `final-production-runtime-result.json` 的状态为 `LOCAL_PRODUCTION_ACTIVE`，并绑定实际 final commit/tree、wheel、pack、profile、config、run、certificate、bundle、verify/read、backup/restore/rollback 和 W10 receipt chain digests。
3. installed wheel 在无 repo cwd、无 `PYTHONPATH` 的新进程中运行。
4. CLI、Python Client、stdio MCP 和 `jc-formal` 使用同一 production composition root 和 CaseInputBundle 合同。
5. PIPL 第 13—18 条各有真实 positive run；evaluate → verify → read 和 bridge delivery 均通过。
6. review、missing、hypothetical、conflict、blocked、resource/cancel/error 状态矩阵按真实业务语义通过；这些业务状态不得被误解为工程 Goal 阻塞。
7. EFS state、最小密钥 ACL、installed release、backup、restore rehearsal、upgrade、rollback 和每日备份任务均实测通过。
8. Z10-00、Z10-01、Z10-02 独立通过；Z10-03 只聚合其真实证据，不调用旧共享空壳 gate。
9. 全量测试、lint、type check、build、wheel exact-set、Git diff check 和任务专属 verifier 全绿。
10. 所有计划内改动已本地提交，整治 worktree clean；主工作树未被修改。

完成时只输出一次最终交付摘要：最终 commit/tree、runner exit code、各测试命令和 exit code、安装版本、生产状态、六个 positive run refs、EFS/备份/恢复/回滚状态、任务计划状态、最终结果文件路径和唯一恢复命令。不要输出新的待授权事项。

如果遇到真实磁盘损坏、EFS/Windows 系统能力不可用等无法通过代码和本机配置修复的机器故障，保留 Goal active，写精确非零 receipt 和可恢复点；这属于机器故障，不得改写为 reviewer、法律授权或签发门禁。

立即开始直接施工。第一步核对现场并提交当前正式方案，随后实现 W10 任务链，最终执行唯一 runner 到 Z10-03；过程中不要停下来等用户回复。
