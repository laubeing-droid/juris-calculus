# 美国10案基准测试 — 数据来源与可复现性证据链
最后更新: 2026-06-02 21:57

本文件建立从 真实联邦法院判决书 → 抽象化JSON事实 → 引擎运行结果 的完整可验证链条。

## 证据链结构

```
判决书PDF (可公开下载/法院存档)
    ↓ 人工/半自动事实提取
us_complaints/core/*.json + us_complaints/roadmap/*.json
    ↓ run_benchmark.py (FixpointEvaluator + 8条 US_CONTRACT_RULES)
results/Benchmark_10Cases_US.md
```

## 完整对应表

| US-REAL ID | 真实案名 | 案号 | 法院 | PDF文件 |
|:--:|------|------|------|------|
| 001 | Twitter, Inc. v. Musk | C.A. No. 2022-0613-KSJM | Del. Ch. 2022 | Twitter_v_Musk_2022-0613-KSJM.pdf (168KB) |
| 002 | Bradford v. Walmart Stores Texas | No. 23-40138 | 5th Cir. 2024 | Bradford_v_Walmart_5thCir_2024.pdf (120KB) |
| 003 | Tynes v. Florida Dep't of Juvenile Justice | No. 21-13245 | 11th Cir. 2023 | Tynes_v_FloridaDJJ_11thCir_2023.pdf (204KB) |
| 004 | In re Marriott Int'l Data Breach Litigation | No. 22-1744 | 4th Cir. 2023 | In_re_Marriott_DataBreach_4thCir_2023.pdf (186KB) |
| 005 | SEC v. Ripple Labs, Inc. | No. 1:20-cv-10832 (AT) | S.D.N.Y. 2023 | SEC_v_Ripple_SJ_Order_2023.pdf (499KB) |
| 006 | Waymo LLC v. Uber Technologies, Inc. | No. 3:17-cv-00939 | N.D. Cal. 2017 | Waymo_v_Uber_Complaint.pdf (207KB) |
| 007 | United States v. Google LLC | No. 1:20-cv-03010 | D.D.C. 2023 | US_v_Google_2023_DDC.pdf (1.5MB) |
| 008 | Chevron Corp. v. Donziger | No. 1:11-cv-00691 (LAK) | S.D.N.Y. 2014 | Chevron_v_Donziger_RICO_Judgment_2014.pdf (1.2MB) |
| 009 | Apple Inc. v. Samsung Electronics Co. | 786 F.3d 983 | Fed. Cir. 2015 | Apple_v_Samsung_14-1802_Opinion.pdf (292KB) |
| 010 | NRA v. Vullo | 602 U.S. ___ | SCOTUS 2024 | NRA_v_Vullo_2024_SCOTUS.pdf (184KB) |
| (备用) | EEOC v. Waffle House, Inc. | 534 U.S. 279 | SCOTUS 2002 | EEOC_v_Waffle_House_534_US_279.pdf (1.2MB) |
| (备用) | Facebook Cambridge Analytica MDL | No. 3:18-md-02843-VC | N.D. Cal. 2019 | Facebook_Cambridge_Analytica_MTD_Order.pdf (466KB) |

## 法律领域覆盖

| 案件 | 法律领域 | 诚实拒算原因 |
|------|----------|-------------|
| Twitter v. Musk | UCC 合同/衡平法 | — (唯一收敛) |
| Bradford v. Walmart | 过失侵权 (Torts) | 无侵权规则 |
| Tynes v. Florida DJJ | 就业歧视 (Title VII) | 无歧视概念 |
| In re Marriott | 数据隐私 (Class Action) | 无隐私/集体诉讼规则 |
| SEC v. Ripple | 证券法 (Securities) | 无证券概念 |
| Waymo v. Uber | 商业秘密 (Trade Secret) | 无商业秘密规则 |
| US v. Google | 反垄断 (Antitrust) | 无反垄断规则 |
| Chevron v. Donziger | RICO/欺诈 | 无RICO规则 |
| Apple v. Samsung | 专利/FRAND | 无专利规则 |
| NRA v. Vullo | 宪法第一修正案 | 无宪法规则 |

## 可复现性

任何人可验证此基准测试：

```bash
# 1. 克隆仓库
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus

# 2. 安装依赖
pip install pyyaml

# 3. 运行基准测试
python tests/run_benchmark.py

# 4. 查看结果
cat tests/results/Benchmark_10Cases_US.md
```

预期输出：1/10 收敛（US-REAL-001, 1 claim: ContractExists），9/10 诚实拒算。

## PDF存档位置

所有判决书全文均可通过 PACER、CourtListener 或各联邦法院官网公开获取。案号见上表。

详细案号与来源说明另见笔者随附的 `US_Benchmark_10例案号与来源说明.txt`。

## 事实提取说明

JSON测试文件中的 `facts` 字段是对判决书公开事实的人工结构化提炼，不含当事人个人信息。事实提取遵循以下原则：
1. 仅提取法院意见中已公开陈述的事实要素
2. 将法律概念抽象为引擎可识别的键值对
3. 故意保留引擎注册表外的概念 → 触发诚实拒算

所有JSON文件内容均可在 GitHub 仓库公开获取，任何人可对这些事实提取的忠实性进行交叉验证。
