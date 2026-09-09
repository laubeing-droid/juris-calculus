# JC施工责任：复用唯一内核

本文件是接线任务，不是已经完成的JC补丁。唯一公开路径仍为jc-harness-local/1：create_local_client、local_case_bundle、evaluate_harness_bundle、local_read_run。无需密钥、激活账本或外部签章。

输入由宿主给定完整Case/Issue/Model/Requirement身份，生产共用唯一ContextKey。参考business_relations/context.py只是隔离副本，接生产时给真实转换/往返证明或使用唯一权威类型；不要维护两套可漂移结构。

要求逐项接入已证明语义：条件分支、金额与C/U分离、合法格、Exact/Inner/Outer、未决及实际结果见证。现有formal spine继续工作；对尚不支持语义明确报告未支持，不静默近似或删除。

ROOT03/04/06给出算法/检查语义，ROOT07负责公开入口与相同原始输入及结果的对应。求解器输出不可信；checker来自冻结实现/注册，不接受提交者回调。保持来源、事实与规则准入，不把统计高分变verified_fact。

实际验收要从已装产物公共入口取得回执及同一运行文件；旧公共入口冒烟只说明已有transport工作，不证明新增能力已进入。真实案例和参数仍不上传公共CI。

关联：ROOT02/ROOT07/ROOT08，任务及数学依据见同次交付的LMM/docs/ulm-consolidated。
