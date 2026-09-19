# U02 规则数据修正证据（归 03：注册表同步）

- run-id: `full-20260919-015613-108316` ｜ 日期: 2026-09-19
- 校验通道: `lccc_consumer.verify_citation`（冻结八字段输出），只读实跑于 **U02 注册消费镜像**
  `jusbench-repo/.local/dev/u02/state/lccc/mirror/snapshots/1`，钉定 dataset tree
  `55ba1b1f932fd1fdac58cfc144f12cdaffb3d6a9d9c73380a7d6f718bc2aa8eb`（与 04 卡
  `reports/u02-law-source-registry.json` 登记一致）。

## 修正 1：仲裁裁决撤销期间 → 三个月

- 依据: 《中华人民共和国仲裁法》（2025-09-12 公布，**2026-03-01 施行**）第七十二条：
  「当事人申请撤销裁决的，应当自收到裁决书之日起三个月内提出。」
- wjbs: `1.2.156.3005.6-0100000000100120250912000900000`
- locator: `lccc://55ba1b1f…/1.2.156.3005.6-0100000000100120250912000900000#art=72`
- 红绿: 绿（现行三个月原文）= **verified, receipt `lcver-8701db6a8153daaf`**；
  红（六个月表述）= failed, receipt `lcver-cd1d1eb6863a3d7c`（六个月文本不在现行第七十二条中）。
- 注册表动作: `arbitration.set_aside.award` 新增 **version "2"（三个月，effectiveFrom 2026-03-01）**；
  version "1"（六个月，2006 口径）保留为历史版本（`status: historical`，`supersededBy: "2"`），不删除。

## 修正 2：续行保全申请窗口 → 届满七日前

- 依据: 《最高人民法院关于人民法院办理财产保全案件若干问题的规定》（2020-12-29 公布，2021-01-01 施行）
  **第十八条**：「申请保全人申请续行财产保全的，应当在保全期限届满七日前向人民法院提出；
  逾期申请或者不申请的，自行承担不能续行保全的法律后果。」
- wjbs: `1.2.156.3005.6-1100000000161020201229169600000`
- locator: `lccc://55ba1b1f…/1.2.156.3005.6-1100000000161020201229169600000#art=18`
- 红绿: 绿（七日前原文）= **verified, receipt `lcver-c5f24af601fa6938`**；
  红（三十日前表述）= failed, receipt `lcver-b1d24076b5d37079`。
- 注册表动作: `preservation.renewal.application` `windowDays: 30 → 7`，锚绑定第十八条；
  cap_check 逻辑（法院指定日优先、财产类型上限核对）不变。

## 备注

- 四条 receipt 均为本次只读实跑产出（receipt 字段含 mirrorTree=55ba1b1f、issuedAt=2026-09-19T06:43Z 段），
  与 04 卡已登记锚（`u02-law-source-registry.json`，OFFICIAL_INDEX_METADATA_VERIFIED）同源同树。
- 运行环境注意：该镜像深层路径超 Windows MAX_PATH，只读访问需短前缀（subst）或等效手段；
  生产消费走 04 公开入口，不受本机开发环境影响。
