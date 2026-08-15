# cn-official staging 层

依据：20260815 施工方案 §13。

- 本层只存放候选 `RuleV4` 与其绑定的第一方快照引用（snapshot_ref + raw hash + locator）。
- 第一方来源无法稳定取得时保持空层；不以第三方文本替代（§13 Gate）。
- 真实 pilot 使用去标识化合成边界事实，不写入私人案件。
- 本层任何内容都不是 reasoning-ready 正式规则；manifest 状态仍由 `manifest.yaml` 唯一表达，当前为 `blocked`。
