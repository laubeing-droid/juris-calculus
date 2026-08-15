# cn-official release 层

依据：20260815 施工方案 §13。

- 本层存放已晋级（人工晋级收据有效）的正式规则包发布材料，供 JC load/replay。
- 晋级前置条件：第一方快照稳定可得、每条规则可回到 snapshot 与 locator、
  有效期/起算边界/文书类型/例外 mutation 均能改变预期结果、法律审核收据与运行时收据分离。
- 任一条件不满足时本层保持空；`manifest.yaml` 保持 `blocked`。
