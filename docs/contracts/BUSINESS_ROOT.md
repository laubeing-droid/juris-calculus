# jc-business-root/1 能力契约

状态：**已实现并安装**（2026-09-11 第一批，见 `docs/ulm-consolidated/IMPLEMENTATION_HANDOFF.md`）。本文解释公共入口与边界；字段与工具的机器权威仍是 `compiler_core/contracts.py`、`schemas/jc-v5.schema.json`。

## 能力是什么

有限情景条件本金计算：给定宿主选定的完整 I0（20 维上下文 + 条件本金 spec + 可选结算模型），内核枚举全部布尔情景 Ω，逐情景给出本金余额 C=max(R,0)、超付残差 U=max(−R,0)，由独立检查器按守恒律验证，并在声明模型上给出 E[C]、E[U]、E[R]、阈值事件概率与合法和解格。**全部输出是条件模型分析**：不是法院认定、不是个案胜率、不是返还请求已经成立。

## 公共入口（jc-harness-local/1 传输面）

```python
client = create_local_client(state_root, rule_roots)

# 1. 能力查询（由已安装实现生成，不读候选 manifest）
client.business_capabilities()

# 2. 构造请求（宿主已选定 I0；selection_ref 是宿主输入修订摘要）
task = BusinessTaskV1(..., selection_ref=..., input=BusinessTaskInputV1(...))
bundle = client.local_case_bundle(case_id=..., decision_time=..., business_tasks=(task,))

# 3. 唯一求值（一次请求恰一次 Application.evaluate；结果密封进审计包）
result = client.evaluate_harness_bundle(bundle, case_id=..., issue_queries=[])

# 4. verify-only：从已核 run 只读导出两份受保护文件字节（零求值）
docs = client.business_delivery_documents(
    run_identity_ref=result["run_identity_ref"], business_task_id=task.task_id)

# 5. Harness 落盘后，核验实际字节（零求值；不改密封包）
verdict = client.verify_business_delivery(
    run_identity_ref=result["run_identity_ref"],
    business_task_id=task.task_id,
    selected_input_ref=task.selection_ref,
    artifacts={"conditional_principal.txt": ..., "calculation.json": ...},
)
```

## 边界（不允许项）

* 求解器输出不可信：独立 checker 用结构指称与全枚举重推，守恒行 `C≥0、U≥0、C·U=0、C−U+recognized==principal` 逐行验证，覆盖集独立形成。
* 核验不接受提交者 expected、checker 回调或自由文件系统路径；两份文件任一被改即整体拒绝，旧核验不自动覆盖新稿。
* 不把 `formal_evidence`（交叉验证算法、kernel 待证）说成 kernelChecked；不把合成 3/5 叫真实胜率；合成来源不升级 `verified_fact`。
* 精确数一律规范有理数字符串（`"2/5"`、`"1000"`）；float、NaN、bool-as-int、重复键、未知字段全部拒绝。
* 兼容性：`business_tasks_v1`/`business_results_v1` 为空时整体不出现在规范字节中，旧请求与旧密封 run 的规范身份逐字节不变。

## 相关

* 施工报告与未关闭清单：[../ulm-consolidated/IMPLEMENTATION_HANDOFF.md](../ulm-consolidated/IMPLEMENTATION_HANDOFF.md)
* 可运行样例：[examples/harness/sample_local_business.py](../../examples/harness/sample_local_business.py)
* 数学权威（LMM，另一仓）：`tools/business_relations/reference/` 与 `JurisLean/BusinessRoot/`
