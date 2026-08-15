# cn-official build 层

依据：20260815 施工方案 §13。

- 本层存放经 source/interpretation/legal 三类审核全部 approved 的候选规则的签名构建产物。
- 构建只能由携带 `HumanPromotionReceiptV1` 的显式流程触发；生成器不得自动修改 manifest 状态。
- 法律解释、工程编码和测试预期由不同字段、不同收据承载，构建不得合并三者。
- 首域（民事诉讼期间计算）未完成前，本层保持空；对外状态只能是 `BLOCKED` 或 `PARTIAL`。
