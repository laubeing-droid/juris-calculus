# theory_absorption fixtures（W0 固定）

依据：20260815 施工方案 §6 动作 6、§17。

## 目的

为 P01—P09 固定正例、反例与缺失/冲突例。fixture 的来源、预期值和 oracle 在 `manifest.json` 中独立记录；预期值来自方案语义，不是由被测代码生成（禁止同一函数自证，§11 动作 6）。

## 结构

- `manifest.json`：fixture 清册、oracle 来源、证据等级。
- `pNN_*.json`：每个研究项一组 cases；`kind` 取 `positive` / `negative` / `missing`。

## 消费规则

1. W1—W9 施工中的测试必须引用这些 fixture，不允许私自复制一份改变预期值的副本。
2. 实现与 fixture 冲突时，差异必须分类为 `SPEC_MISMATCH` / `IMPLEMENTATION_MISMATCH` / `TRANSLATION_MISMATCH` / `ORACLE_UNRESOLVED`，不得以修改 expected 值消除（§12 动作 3、Gate）。
3. P03/P04/P07 的深度 fixture 随 W4/W5/W6 扩展；扩展必须保持既有 case 不变。
4. 证据等级（§17）：本目录 fixture 目前为 differential fixture 级别；不构成法律正确性声明。
