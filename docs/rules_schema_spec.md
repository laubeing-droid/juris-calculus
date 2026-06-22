# Rules Schema Specification

> 自动生成于 2026-06-18

## 字段清单

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | string | 是 | 规则唯一标识，格式 PREFIX-NNN | PC-001 |
| premise_atoms | list[str] | 是 | 前提条件原子，≥1 个 | [breach_alleged, state_compensation] |
| head_claim | string | 是 | 结论（裁判规则），40-150字 | 国家赔偿的责任主体是... |
| exception_chain | list[str] | 否 | 例外规则 ID 列表 | [PC-001-exc] |
| concepts | list[str] | 否 | 概念标签，用于检索 | [国家赔偿, 行政赔偿] |
| mechanical_exception | bool | 否 | 是否机械性例外，默认 true | false |
| head_type | string | 否 | 规则类型，默认 HORN | HORN |
| namespace | string | 否 | 领域命名空间 | admin / tort / criminal |
| norm_modality | string | 是 | 规范模态 | OBLIGATION / PROHIBITION / PERMISSION / CONSTITUTIVE |
| modality_confidence | float | 否 | 模态置信度 0-1 | 0.9 |
| modality_source | string | 否 | 模态来源 | llm_confirmed / keyword_head / deep_distill_v2 / auto_distill |
| reparation_chain_pool | list | 否 | 赔偿计算路径 | [实际损失, 可预见损失] |
| source_anchor | string | 否 | 来源锚定（书名/章节） | 环境资源审判实务/第二编 |
| valid_from | string | 否 | 生效日期 | 2021-01-01 |
| valid_to | string | 否 | 失效日期 | |
| jurisdiction | string | 否 | 法域 | CN / HK / US |
| authority_rank | string | 否 | 权威等级 | constitution / statute / regulation / guideline |
| trust_label | string | 否 | 信任标签，默认 UNVERIFIED | ENGINEERING_BASELINE |
| data_quality | string | 否 | 数据质量标签，默认 CLEAN | CLEAN / UNCERTAIN / SPARSE |

## norm_modality 取值

| 值 | 含义 | 关键词 |
|----|------|--------|
| OBLIGATION | 义务性规则 | 应当、必须、需要 |
| PROHIBITION | 禁止性规则 | 不得、禁止、严禁 |
| PERMISSION | 许可性规则 | 可以、有权、允许 |
| CONSTITUTIVE | 构成性规则 | 构成、认定为、视为 |

## trust_label 取值

| 值 | 含义 |
|----|------|
| UNVERIFIED | 未验证 |
| ENGINEERING_BASELINE | 工程基线 |
| DATA_INSUFFICIENT_FOR_PROOF | 数据不足以证明 |
| TESTED_PROPERTY | 已测试属性 |
| SMT_PROVED_FINITE | SMT 有限证明 |

## data_quality 取值

| 值 | 含义 |
|----|------|
| CLEAN | 干净：蒸馏+人工双审 |
| UNCERTAIN | 不确定：仅 LLM 蒸馏 |
| SPARSE | 稀疏：补偿字段缺失 |
| PROVISIONAL | 临时：L2/L3 轻量条目 |
