# JC v3 治理、训练与ADVISORY边界

## 规则治理

[有理有据的][高等] `jc rules audit <pack-id>`先执行pack manifest、文件hash和inventory验证，再复用唯一规则审计实现生成完整治理artifact。默认stdout只返回计数和逻辑引用；完整candidate ID、source snapshot、有效期、modality、priority、重复ID、测试覆盖和findings写入`governance/<pack-digest>/audit.json`。

[有理有据的][高等] 缺来源规则是candidate问题，不因存在而让legacy corpus伪装成正式pack；但任何来源缺失规则进入reasoning-ready、重复ID、悬空关系、无效日期或非法modality均不能通过相应门禁。治理报告只能建议人工晋升，不能修改YAML或pack状态。

## 训练导出

[有理有据的][高等] `jc training export <pack-id> --out <dir> --seed <n>`只读取经过manifest完整性验证的规则语料，输出train/dev/test JSONL及`training_manifest.json`。每条记录包含pack ID/version/digest、source/admission状态、split与split seed；candidate-only规则必须保留。

[有理有据的][高等] 训练导出拒绝写入pack config root，不读取案件审计包，manifest固定声明`private_case_facts_included=false`与`automatic promotion=false`。训练产物不能反向晋升正式规则；晋升仍需治理、promotion gate和人工批准。

## 缺失事实机器数据

[有理有据的][高等] `MISSING_REQUIRED_FACT`结果现包含`missing_fact_review`：fact ID、受影响rule/claim、UNKNOWN原因、允许回答类型和正式事实所需来源条件。Graph JSON使用`missing_premise`与`potential_conclusion`边表达“若缺失事实补齐可能影响哪里”，不得把potential edge当作已发生推导。

## 诉讼策略ADVISORY

[有理有据的][高等] `jc analyze strategy --run <run-id>`只读取hash有效的完整run，根据现有missing facts、攻击/例外/优先边、分支、taint、claims、rules和sources生成机器路径：证据补全、冲突复核、假设压力测试、正式依据保存或无可行动正式依据。

[有理有据的][高等] 输出始终为`ADVISORY`、`review_required=true`、`formal_certificate_generated=false`，写入独立`analysis/`目录；它不补案情、不新增法律依据、不改CanonicalResult，也不决定律师具体行动。

## 类案分析

[有理有据的][高等] `jc analyze similar-cases --run <run-id> --index <path>`只比较结构化fact/rule/claim/edge集合，使用固定Jaccard加权，不引入向量数据库、embedding、网络服务或SQLite。Index必须带版本、法域、来源、逐案source hash和整体content digest。

[有理有据的][高等] 输出包含相同因素、差异因素、来源、日期、分项分数和限制，明确“结构相似不预测法院结果”。仓库只含合成fixture index，用于机制测试；当前没有合法授权的真实类案索引，因此实务质量验收状态为`BLOCKED`，不得以fixture得分宣称类案能力已达到实务质量。

## 三轨边界

[有理有据的][高等] HK/US/PRC现有三轨只保留显式engineering harness。各轨记录legacy pack/config digest，但由于不存在三套reasoning-ready official pack，普通场景和fast path均为review-only、`formal_kernel_used=false`，并带`ENGINEERING_HARNESS`或`FAST_PATH_INTERCEPT`标记。不得把低层矩阵结果包装成正式案件结论。

## [我违规之处]

无。
