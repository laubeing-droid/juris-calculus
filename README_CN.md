# juris-calculus v2.0.0

中国法符号化推理引擎，支持基于 addon 插件的跨法域扩展。

## 架构

```
  Layer 0: juris_blueprint.json（14 个 CN MoE 领域）
  Layer 1: 信任标签（认知状态枚举）
  Layer 2: Horn 子句不动点评估器（2,117 条中国法规则）
  Layer 3: MoE 规则路由 + 分层评估器
  Layer 4: 对抗管线（推理器/审计器/验证器）
  Layer 5: Dung AAF 论证框架 + 步骤验证器（EVM）
  Layer 6: 神经叶子节点（Kill Switch + 冷启动保护）

  addons/             <-- 可选法域插件
    hk/               香港特别行政区（Cap 26，364 条 Horn 规则）
    us/               美国（UCC，53 Title 索引，266 法院，419 联邦术语）
    federation/       普通法系配对比较引擎
```

## 本体 vs Addons

本体引擎只含中国法。其他法域通过 `plugin_registry.discover()` 自动发现并加载。
核心代码不含任何 HK/US 的 import。

## 法域覆盖

| 法域 | 规则 | 法系 | 状态 |
|------|------|------|------|
| CN（中国大陆） | 2,117 条 Horn 规则，14 个 MoE 领域 | 大陆法系 | 本体（始终加载） |
| HK（香港） | 364 条 Horn 规则（Cap 26/32/33/4A/571/6/622） | 普通法系 | Addon |
| US（美国） | 53 Title 索引 + 266 法院 + 419 联邦术语 | 普通法系 | Addon |

## 快速开始

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
pytest tests/          # 43 个测试
python mcp_server.py   # MCP 服务端
```

## 个性化 YAML（多律师共享算法）

设置 `JURIS_CONFIG_DIR` 指向个人 YAML 库。同一套算法代码，不同律师各自沉淀规则。

## 许可

MIT
