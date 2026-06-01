import json, os

real_cases = [
  {
    'case_id': 'US-REAL-002',
    'cause_of_action': 'Negligence (Premises Liability)',
    'complexity': 'medium',
    'governing_law': {'statute': 'State tort law', 'restatement': 'Restatement (Second) of Torts 343'},
    'facts': {
      'DutyOfCare': 'Walmart作为商业场所经营者对顾客负有合理注意义务',
      'BreachOfDuty': '商场地面存在湿滑危险状况未设置警告标志',
      'Causation': '顾客因地面湿滑摔倒导致身体伤害',
      'ActualInjury': '臀部骨折+医疗费用',
      'ConstructiveNotice': '湿滑状况存在时间足以推定商场应当知晓',
      'DamagesClaimed': '已主张'
    },
    'notes': 'REAL PATTERN: Slip-and-fall premises liability. Walmart is the most-sued company in America.',
    'expected': 'HONEST_REFUSAL — no tort rules in US_CONTRACT_RULES',
    'missing_concepts': ['DutyOfCare', 'BreachOfDuty', 'Causation', 'ActualInjury', 'ConstructiveNotice']
  },
  {
    'case_id': 'US-REAL-003',
    'cause_of_action': 'Employment Discrimination (Title VII)',
    'complexity': 'high',
    'governing_law': {'statute': 'Title VII of Civil Rights Act of 1964, 42 USC 2000e'},
    'facts': {
      'AdverseAction': '因性别原因被解雇',
      'ProtectedClass': '性别歧视',
      'QualifiedEmployee': '原告具备岗位要求的资历',
      'DisparateTreatment': '同等情况下其他性别员工未被解雇',
      'PretextAlleged': '雇主声称绩效原因但评估记录显示此前绩效良好',
      'DamagesClaimed': '工资损失+精神损害赔偿+惩罚性赔偿'
    },
    'notes': 'REAL PATTERN: McDonnell Douglas burden-shifting framework. Title VII employment discrimination.',
    'expected': 'HONEST_REFUSAL — discrimination concepts not in registry',
    'missing_concepts': ['AdverseAction', 'ProtectedClass', 'DisparateTreatment', 'PretextAlleged']
  },
  {
    'case_id': 'US-REAL-004',
    'cause_of_action': 'Class Action (Data Privacy)',
    'complexity': 'extreme',
    'governing_law': {'statute': 'Federal Rule 23 + State Privacy Laws'},
    'facts': {
      'DataBreach': '大规模用户隐私数据泄露',
      'ConsumerHarm': '数百万用户个人信息被未经授权访问',
      'ClassSize': 'N > 1,000,000',
      'CommonalityAlleged': '所有受害者遭受同一数据泄露事件',
      'DamagesClaimed': '集体损害赔偿+信用监控费用'
    },
    'notes': 'REAL PATTERN: Facebook/Cambridge Analytica privacy class actions. Tests M3 batch decay at N>1M.',
    'expected': 'HONEST_REFUSAL on legal logic; M3 decay testable on pricing',
    'missing_concepts': ['DataBreach', 'ClassCertification', 'Commonality', 'ConsumerHarm']
  },
  {
    'case_id': 'US-REAL-005',
    'cause_of_action': 'Securities Law (Howey Test)',
    'complexity': 'high',
    'governing_law': {'statute': 'Securities Act of 1933, Securities Exchange Act of 1934'},
    'facts': {
      'SecurityOffering': '发行XRP代币',
      'RegistrationStatus': '未向SEC注册',
      'HoweyTest_Investment': '投资者投入资金',
      'HoweyTest_CommonEnterprise': '投资者利益与被告努力相关联',
      'HoweyTest_ProfitExpectation': '投资者期望从被告努力中获利',
      'DamagesClaimed': '民事罚款+非法所得追缴+禁令救济'
    },
    'notes': 'REAL CASE: SEC v. Ripple Labs (S.D.N.Y.). Howey Test for investment contract classification.',
    'expected': 'HONEST_REFUSAL — securities concepts absent',
    'missing_concepts': ['HoweyTest_Investment', 'HoweyTest_CommonEnterprise', 'HoweyTest_ProfitExpectation']
  },
  {
    'case_id': 'US-REAL-006',
    'cause_of_action': 'Trade Secret Misappropriation',
    'complexity': 'high',
    'governing_law': {'statute': 'Defend Trade Secrets Act (DTSA) + CUTSA'},
    'facts': {
      'TradeSecretExists': '电池技术和制造工艺构成商业秘密',
      'ConfidentialityObligation': '被告雇员签署保密协议',
      'Misappropriation': '被告通过挖角原告工程师获取商业秘密',
      'DamagesClaimed': '禁令救济+赔偿研发成本'
    },
    'notes': 'REAL PATTERN: Tesla v. Rivian (California Superior Court). Trade secret misappropriation.',
    'expected': 'HONEST_REFUSAL — trade secret concepts absent',
    'missing_concepts': ['TradeSecretExists', 'ConfidentialityObligation', 'Misappropriation']
  },
  {
    'case_id': 'US-REAL-007',
    'cause_of_action': 'Antitrust (Sherman Act Section 2)',
    'complexity': 'extreme',
    'governing_law': {'statute': 'Sherman Act Section 2, 15 USC 2'},
    'facts': {
      'MarketPower': 'Google在通用搜索服务市场具有垄断地位',
      'ExclusionaryConduct': '通过排他性默认搜索引擎协议排除竞争对手',
      'AnticompetitiveEffects': '消费者选择减少，创新受阻，广告价格上涨',
      'DamagesClaimed': '结构性救济（拆分或行为限制）+禁令'
    },
    'notes': 'REAL CASE: United States v. Google LLC (D.D.C. 2023-2024). Monopolization under Sherman Act 2.',
    'expected': 'HONEST_REFUSAL — antitrust concepts completely absent',
    'missing_concepts': ['MarketPower', 'ExclusionaryConduct', 'AnticompetitiveEffects', 'RelevantMarket']
  },
  {
    'case_id': 'US-REAL-008',
    'cause_of_action': 'RICO / Fraud (Judgment Fraud)',
    'complexity': 'high',
    'governing_law': {'statute': 'RICO Act, 18 USC 1961-1968'},
    'facts': {
      'FraudulentScheme': '被告律师通过贿赂欺诈手段获取不利判决',
      'PatternOfRacketeering': '多起相关欺诈行为构成敲诈勒索模式',
      'Enterprise': '被告与其法律团队构成RICO意义上的企业',
      'DamagesClaimed': '判决金额返还+三倍赔偿+律师费'
    },
    'notes': 'REAL CASE: Chevron v. Donziger (S.D.N.Y.). Ecuadorian judgment fraud under RICO.',
    'expected': 'HONEST_REFUSAL — RICO concepts absent',
    'missing_concepts': ['FraudulentScheme', 'PatternOfRacketeering', 'Enterprise']
  },
  {
    'case_id': 'US-REAL-009',
    'cause_of_action': 'Patent FRAND Breach',
    'complexity': 'high',
    'governing_law': {'statute': 'Patent Act 35 USC + FRAND obligations'},
    'facts': {
      'PatentOwnership': '原告拥有移动通信标准必要专利',
      'FRANDCommitment': '原告向标准组织做出FRAND许可承诺',
      'LicensingDispute': '被告使用专利但拒绝支付FRAND合理许可费',
      'DamagesClaimed': '合理许可费+禁令救济'
    },
    'notes': 'REAL PATTERN: Apple v. Samsung (N.D. Cal.). FRAND standard-essential patent licensing.',
    'expected': 'HONEST_REFUSAL — patent/FRAND concepts absent',
    'missing_concepts': ['PatentOwnership', 'FRANDCommitment', 'LicensingDispute']
  },
  {
    'case_id': 'US-REAL-010',
    'cause_of_action': 'First Amendment Retaliation',
    'complexity': 'high',
    'governing_law': {'statute': 'First Amendment, 42 USC 1983'},
    'facts': {
      'ProtectedSpeech': 'NRA从事受第一修正案保护的倡导活动',
      'GovernmentCoercion': '纽约州金融监管机构施压保险公司停止与NRA业务往来',
      'ChillingEffect': '政府行为对NRA言论产生寒蝉效应',
      'CausalLink': '政府施压直接导致商业关系中断',
      'DamagesClaimed': '宣告性救济+禁令+名义损害赔偿'
    },
    'notes': 'REAL CASE: NRA v. Vullo (Supreme Court 2024). First Amendment retaliation against NY regulator.',
    'expected': 'HONEST_REFUSAL — constitutional concepts absent',
    'missing_concepts': ['ProtectedSpeech', 'GovernmentCoercion', 'ChillingEffect', 'StateAction']
  }
]

dir = 'tests/us_complaints'
os.makedirs(dir, exist_ok=True)
for c in real_cases:
    name = f"{c['case_id']}.json"
    fp = os.path.join(dir, name)
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
    mc = c.get('missing_concepts', [])
    print(f"{c['case_id']} [{c['complexity']:7s}] {c['cause_of_action'][:45]} | {len(c['facts'])} atoms | missing={len(mc)}")

print(f"\n{len(real_cases)} real cases written")
