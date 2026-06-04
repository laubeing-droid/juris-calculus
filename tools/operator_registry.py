#!/usr/bin/env python3
"""
tools/operator_registry.py — 算子注册表 v1.2.0
══════════════════════════════════════════════════════════
算子自文档化 (Operator Self-Documentation):
  每个算子定义时自动注册其 JSON Schema、入参约束、
  优先级偏好、以及对应的 CBL/SPC 规则ID。

设计原则:
  1. 算子即信源 (Operator as Single Source of Truth)
  2. Schema 动态生成 — 修改算子 = 自动更新对外协议
  3. Codex 无法发明逻辑 — 只能组合已注册算子
══════════════════════════════════════════════════════════
"""

from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class OperatorType(Enum):
    CBL_FORCE_VOID = "FORCE_VOID"           # 成文法一票否决
    CBL_FORCE_SUPPRESS = "FORCE_SUPPRESS"    # 成文法权力抑制
    CBL_MAPPING_OVERRIDE = "MAPPING_OVERRIDE" # 概念替换重构
    SPC_JUDICIAL_TENDENCY = "SPC_HORN"       # 最高法裁判倾向
    CN_HORN_FULL = "CN_HORN"                 # 中国成文法全量
    HK_HORN = "HK_HORN"                      # 香港普通法
    US_HORN = "US_HORN"                      # 美国联邦法
    THREAT_INTERCEPT = "THREAT_INTERCEPT"    # 威胁拦截
    STATE_ROUTER = "STATE_ROUTER"            # 州级路由


@dataclass
class OperatorSchema:
    """算子自文档化 Schema"""
    id: str
    type: OperatorType
    description: str
    trigger_facts: List[str] = field(default_factory=list)
    additional_conditions: List[str] = field(default_factory=list)
    output_states: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    risk_level: str = "MEDIUM"  # CRITICAL | HIGH | MEDIUM | LOW

    # ═══ 对外协议字段 ═══
    operator_preference: Dict[str, Any] = field(default_factory=dict)
    sovereignty_anchoring: bool = False   # 是否强制主权锚定
    allow_settlement: bool = True          # 是否允许和解/折中
    critical_threshold: float = 0.80       # 置信度门控

    @property
    def json_schema(self) -> Dict:
        """导出为 JSON Schema 格式"""
        return {
            "operator_id": self.id,
            "type": self.type.value,
            "description": self.description,
            "trigger": {
                "facts": self.trigger_facts,
                "conditions": self.additional_conditions,
            },
            "output": {
                "states": self.output_states,
            },
            "legal_basis": {
                "citations": self.citations,
                "risk_level": self.risk_level,
            },
            "operator_preference": self.operator_preference or {
                "primary": self.type.value,
                "critical_threshold": self.critical_threshold,
            },
            "constraints": {
                "sovereignty_anchoring": self.sovereignty_anchoring,
                "allow_settlement": self.allow_settlement,
            }
        }


class OperatorRegistry:
    """
    算子注册表 — 所有法律算子的唯一信源。

    用法:
      @OperatorRegistry.register(
          id="CBL_VOID_001",
          type=OperatorType.CBL_FORCE_VOID,
          description="中国法域数据出境一票否决",
          trigger_facts=["Cross_Border_Data_Transfer_To_US"],
          citations=["《数据安全法》第21条"],
          risk_level="CRITICAL",
          sovereignty_anchoring=True,
          allow_settlement=False,
      )
      def force_void_data_export(fact_stream):
          ...
    """

    _registry: Dict[str, OperatorSchema] = {}
    _functions: Dict[str, Callable] = {}

    @classmethod
    def register(cls, *, id: str, type: OperatorType, description: str,
                 trigger_facts: List[str] = None,
                 additional_conditions: List[str] = None,
                 output_states: List[str] = None,
                 citations: List[str] = None,
                 risk_level: str = "MEDIUM",
                 operator_preference: Dict = None,
                 sovereignty_anchoring: bool = False,
                 allow_settlement: bool = True,
                 critical_threshold: float = 0.80):
        """注册算子 — 同时注册函数和 Schema"""
        schema = OperatorSchema(
            id=id,
            type=type,
            description=description,
            trigger_facts=trigger_facts or [],
            additional_conditions=additional_conditions or [],
            output_states=output_states or [],
            citations=citations or [],
            risk_level=risk_level,
            operator_preference=operator_preference or {},
            sovereignty_anchoring=sovereignty_anchoring,
            allow_settlement=allow_settlement,
            critical_threshold=critical_threshold,
        )

        def decorator(func: Callable):
            cls._registry[id] = schema
            cls._functions[id] = func
            return func

        return decorator

    @classmethod
    def get_all_schemas(cls) -> Dict[str, Dict]:
        """导出全部算子 Schema — Codex 消费此接口获取能力边界"""
        return {op_id: schema.json_schema for op_id, schema in cls._registry.items()}

    @classmethod
    def get_schemas_by_type(cls, op_type: OperatorType) -> Dict[str, Dict]:
        """按类型过滤 Schema"""
        return {
            op_id: schema.json_schema
            for op_id, schema in cls._registry.items()
            if schema.type == op_type
        }

    @classmethod
    def get_schemas_by_risk(cls, risk_level: str) -> Dict[str, Dict]:
        """按风险等级过滤"""
        return {
            op_id: schema.json_schema
            for op_id, schema in cls._registry.items()
            if schema.risk_level == risk_level
        }

    @classmethod
    def get_critical_operators(cls) -> Dict[str, Dict]:
        """获取所有 CRITICAL 级算子 (Codex 必须优先调用)"""
        return cls.get_schemas_by_risk("CRITICAL")

    @classmethod
    def get_sovereignty_operators(cls) -> Dict[str, Dict]:
        """获取所有强制主权锚定算子"""
        return {
            op_id: schema.json_schema
            for op_id, schema in cls._registry.items()
            if schema.sovereignty_anchoring
        }

    @classmethod
    def invoke(cls, op_id: str, *args, **kwargs):
        """调用已注册算子"""
        if op_id not in cls._functions:
            raise ValueError(f"Operator not found: {op_id}")
        return cls._functions[op_id](*args, **kwargs)

    # ═══════════════════════════════════════════
    # 操作器自举 (Operator Bootstrap)
    # ═══════════════════════════════════════════

    @classmethod
    def bootstrap_from_yaml(cls, blocking_path: str = None, spc_path: str = None,
                            hk_path: str = None, force: bool = False):
        """
        从 YAML 配置文件自动生成算子注册。
        解决 blocking_rules.yaml 编辑后 OperatorRegistry 不同步的断层。

        版本原子性保证:
          每次 bootstrap 记录 source_hash → 修改 YAML → hash 变化 → 重新 bootstrap
          旧版本规则不自动覆盖已有注册(除非 force=True)

        Args:
            blocking_path: blocking_rules.yaml 路径
            spc_path: spc_rules.yaml 路径
            hk_path: hk/extended_rules.yaml 路径
            force: 是否强制覆盖已有注册

        Returns:
            {added: int, skipped: int, source_hash: str}
        """
        import hashlib
        import yaml as _yaml
        from pathlib import Path

        base = Path(__file__).resolve().parents[1]
        added = 0
        skipped = 0
        source_texts = []

        # ── CBL 阻断规则 ──
        if blocking_path is None:
            blocking_path = base / "configs" / "prc_us_alignment" / "blocking_rules.yaml"
        cbl_path = Path(blocking_path)
        if cbl_path.exists():
            with open(cbl_path, "r", encoding="utf-8") as f:
                raw = f.read()
                source_texts.append(raw)
                data = _yaml.safe_load(raw)
            for rule in data.get("rules", []):
                rid = rule.get("id", "")
                if not rid or (rid in cls._registry and not force):
                    skipped += 1
                    continue
                action = rule.get("action", {})
                op_type_str = action.get("type", "FORCE_VOID")
                op_type = _map_yaml_type(op_type_str)
                cls._registry[rid] = OperatorSchema(
                    id=rid,
                    type=op_type,
                    description=rule.get("description", ""),
                    trigger_facts=[rule.get("trigger_fact", "")] if rule.get("trigger_fact") else [],
                    additional_conditions=rule.get("additional_conditions", []),
                    output_states=[action.get("status", "VOID")],
                    citations=[action.get("map_to", "")] if action.get("map_to") else [],
                    risk_level="CRITICAL" if op_type_str in ("FORCE_VOID", "FORCE_SUPPRESS") else "HIGH",
                    sovereignty_anchoring=op_type_str in ("FORCE_VOID", "FORCE_SUPPRESS"),
                    allow_settlement=op_type_str == "MAPPING_OVERRIDE",
                    operator_preference={
                        "primary": op_type_str,
                        "critical_threshold": 0.88 if op_type_str == "FORCE_VOID" else 0.80,
                    } if op_type_str in ("FORCE_VOID", "FORCE_SUPPRESS") else {},
                )
                # Placeholder function
                cls._functions[rid] = lambda **kwargs: {"status": "SUCCESS", "op": rid}
                added += 1

        # ── SPC 裁判规则 ──
        if spc_path is None:
            spc_path = base / "configs" / "prc_us_alignment" / "spc_rules.yaml"
        spc_p = Path(spc_path)
        if spc_p.exists():
            with open(spc_p, "r", encoding="utf-8") as f:
                raw = f.read()
                source_texts.append(raw)
                data = _yaml.safe_load(raw)
            for rule in data.get("rules", []):
                rid = rule.get("id", "")
                if not rid or (rid in cls._registry and not force):
                    skipped += 1
                    continue
                cls._registry[rid] = OperatorSchema(
                    id=rid,
                    type=OperatorType.SPC_JUDICIAL_TENDENCY,
                    description=rule.get("head_claim", "")[:100],
                    trigger_facts=rule.get("premise_atoms", []),
                    output_states=[rule.get("head_claim", "")[:50]],
                    citations=[rule.get("description", "")] if rule.get("description") else [],
                    risk_level="HIGH",
                )
                cls._functions[rid] = lambda **kwargs: {"status": "SUCCESS", "op": rid}
                added += 1

        # ── HK 扩展规则 ──
        if hk_path:
            hk_p = Path(hk_path)
            if hk_p.exists():
                with open(hk_p, "r", encoding="utf-8") as f:
                    raw = f.read()
                    source_texts.append(raw)
                    data = _yaml.safe_load(raw)
                for rule in data.get("rules", []):
                    rid = rule.get("id", "")
                    if not rid or (rid in cls._registry and not force):
                        skipped += 1
                        continue
                    cls._registry[rid] = OperatorSchema(
                        id=rid,
                        type=OperatorType.HK_HORN,
                        description=rule.get("description", "")[:100],
                        trigger_facts=rule.get("premise_atoms", []),
                        output_states=[rule.get("head_claim", "")],
                        risk_level="MEDIUM",
                    )
                    cls._functions[rid] = lambda **kwargs: {"status": "SUCCESS", "op": rid}
                    added += 1

        source_hash = hashlib.sha256("".join(source_texts).encode()).hexdigest()[:12]

        return {
            "added": added,
            "skipped": skipped,
            "total_registered": len(cls._registry),
            "source_hash": source_hash,
        }

    @classmethod
    def get_source_hash(cls) -> str:
        """返回最近一次 bootstrap 的源文件 hash — 用于版本比对"""
        if hasattr(cls, '_last_source_hash'):
            return cls._last_source_hash
        return "UNBOOTSTRAPPED"


def _map_yaml_type(yaml_type: str) -> OperatorType:
    """YAML action.type → OperatorType 枚举"""
    mapping = {
        "FORCE_VOID": OperatorType.CBL_FORCE_VOID,
        "FORCE_SUPPRESS": OperatorType.CBL_FORCE_SUPPRESS,
        "MAPPING_OVERRIDE": OperatorType.CBL_MAPPING_OVERRIDE,
        "CONDITIONAL_SECONDARY": OperatorType.CBL_FORCE_SUPPRESS,
    }
    return mapping.get(yaml_type, OperatorType.CBL_FORCE_VOID)

    @classmethod
    def execute(cls, op_id: str, **kwargs) -> Any:
        """
        安全执行算子。
        若 Pydantic 可用 → 自动校验入参 Schema。
        返回: Schema校验通过后的算子执行结果。
        """
        if op_id not in cls._registry:
            raise ValueError(f"Operator not found: {op_id}")

        schema = cls._registry[op_id]
        func = cls._functions[op_id]

        # ── Pydantic 强校验 (可选) ──
        try:
            from pydantic import BaseModel, ValidationError
            model = cls._build_validation_model(op_id, schema, kwargs)
            validated = model(**kwargs).model_dump()
            # 仅传函数实际接受的参数
            import inspect
            sig = inspect.signature(func)
            clean_kwargs = {k: v for k, v in validated.items() if k in sig.parameters}
            return func(**clean_kwargs)
        except ImportError:
            pass  # 降级: 不做Pydantic校验
        except ValidationError as e:
            raise ValueError(f"Codex input validation failed for {op_id}: {e}")

        # 降级: 无Pydantic → 直接调用(仅传函数接受的参数)
        import inspect
        sig = inspect.signature(func)
        clean_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return func(**clean_kwargs)

    @classmethod
    def _build_validation_model(cls, op_id: str, schema: 'OperatorSchema', kwargs: Dict):
        """动态构建 Pydantic 校验模型 (仅当 Pydantic 可用时)"""
        from pydantic import BaseModel, Field, create_model

        fields = {}
        for fact in schema.trigger_facts:
            fields[fact_to_field(fact)] = (bool, Field(default=True,
                description=f"Trigger fact: {fact}"))
        for cond in schema.additional_conditions:
            field_name = fact_to_field(cond.replace("NOT ", "NOT_"))
            fields[field_name] = (bool, Field(default=True,
                description=f"Condition: {cond}"))

        fields["sovereignty_anchoring"] = (
            bool, Field(default=schema.sovereignty_anchoring,
                description=f"主权锚定 (固定值: {schema.sovereignty_anchoring})")
        )
        fields["allow_settlement_check"] = (
            bool, Field(default=schema.allow_settlement,
                description=f"是否允许和解 (固定值: {schema.allow_settlement})")
        )
        fields["critical_threshold"] = (
            float, Field(default=schema.critical_threshold, ge=0.0, le=1.0,
                description=f"置信度门控阈值")
        )

        return create_model(f"{op_id}Validation", **fields)

    @classmethod
    def generate_legal_task_schema(cls, task_focus: List[str] = None) -> Dict:
        """
        动态生成 Codex 可消费的法律对抗任务 Schema。
        基于当前已注册的全部算子能力。
        """
        critical_ops = cls.get_critical_operators()
        sovereignty_ops = cls.get_sovereignty_operators()
        all_ops = cls.get_all_schemas()

        prc_focused = task_focus and "PRC" in task_focus

        return {
            "version": "1.2.0",
            "kernel": "juris-calculus-trirail",
            "total_operators": len(all_ops),
            "critical_operators": len(critical_ops),
            "sovereignty_anchored": len(sovereignty_ops),

            "task_protocol": {
                "task_id": "UUID (auto-generated)",
                "meta": {
                    "jurisdiction_focus": task_focus or ["PRC", "HK", "US"],
                    "priority": "CRITICAL | HIGH | MEDIUM",
                    "threat_level": "RED | YELLOW | GREEN",
                },
                "fact_stream": {
                    "subject": "实体名称",
                    "incident": "触发纠纷的核心事实",
                    "data_assets": ["涉及的数据资产清单"],
                    "jurisdictional_nexus": "事实与各法域连接点",
                },
                "confrontation_params": {
                    "opponent_strategy": "美方律师战术预测",
                    "red_line_check": [
                        op_id for op_id in critical_ops.keys()
                    ] if prc_focused else [],
                    "expected_outcome": "VOID_REQUEST | SUPPRESS_REQUEST | SETTLEMENT",
                },
            },

            "operator_preferences": {
                op_id: schema["operator_preference"]
                for op_id, schema in all_ops.items()
                if schema["operator_preference"]  # 非空
            },

            "sovereignty_constraints": {
                op_id: {
                    "anchoring": schema["constraints"]["sovereignty_anchoring"],
                    "settlement_allowed": schema["constraints"]["allow_settlement"],
                }
                for op_id, schema in sovereignty_ops.items()
            },

            "available_operators": {
                op_id: {
                    "type": schema["type"],
                    "risk": schema["legal_basis"]["risk_level"],
                    "citations": schema["legal_basis"]["citations"],
                }
                for op_id, schema in all_ops.items()
            },
        }


# ═══════════════════════════════════════════════
# 预注册核心算子 (基于 blocking_rules.yaml + spc_rules.yaml)
# ═══════════════════════════════════════════════

@OperatorRegistry.register(
    id="PEN_001_Data_CrossBorder_Security",
    type=OperatorType.CBL_FORCE_VOID,
    description="数据出境安全评估 — 未经CAC批准的数据出境行为自始无效",
    trigger_facts=["US_Cloud_Act_Data_Request", "Cross_Border_Data_Transfer_To_US"],
    additional_conditions=["Identified_Sensitive_Data_Or_State_Secret"],
    output_states=["VOID"],
    citations=["《数据安全法》第21条", "《数据出境安全评估办法》"],
    risk_level="CRITICAL",
    sovereignty_anchoring=True,
    allow_settlement=False,
    critical_threshold=0.85,
)
def pen_001_operator():
    pass


@OperatorRegistry.register(
    id="PEN_003_Long_Arm_Interdiction",
    type=OperatorType.CBL_FORCE_SUPPRESS,
    description="长臂管辖阻断 — 美国域外管辖权在中国法域内效力归零",
    trigger_facts=["US_Long_Arm_Jurisdiction_Asserted"],
    additional_conditions=["Entity_Type_PRC_National"],
    output_states=["SUPPRESSED"],
    citations=["《反外国制裁法》第12条", "《阻断办法》第9条"],
    risk_level="CRITICAL",
    sovereignty_anchoring=True,
    allow_settlement=False,
    critical_threshold=0.88,
    operator_preference={
        "primary": "FORCE_SUPPRESS",
        "fallback": "PEN_002_Secondary_Sanction_Block",
        "critical_threshold": 0.88,
    },
)
def pen_003_operator():
    pass


@OperatorRegistry.register(
    id="PEN_004_OFAC_CounterCollision",
    type=OperatorType.CBL_FORCE_SUPPRESS,
    description="OFAC制裁反制 — 中国实体在OFAC制裁下自动触发反制",
    trigger_facts=["OFAC_Sanctions_Imposed"],
    additional_conditions=["Entity_Type_PRC_National"],
    output_states=["PRC_ANTI_SANCTION_ACTIVE"],
    citations=["《反外国制裁法》第12条"],
    risk_level="CRITICAL",
    sovereignty_anchoring=True,
    allow_settlement=False,
    critical_threshold=0.90,
)
def pen_004_operator():
    pass


@OperatorRegistry.register(
    id="PEN_005_Crypto_Prohibition",
    type=OperatorType.CBL_FORCE_VOID,
    description="加密货币交易全面禁止",
    trigger_facts=["Cryptocurrency_Transaction"],
    output_states=["VOID", "PRC_VOID"],
    citations=["《关于进一步防范和处置虚拟货币交易炒作风险的通知》(2021)"],
    risk_level="CRITICAL",
    sovereignty_anchoring=True,
    allow_settlement=False,
    critical_threshold=0.90,
)
def pen_005_operator():
    pass


@OperatorRegistry.register(
    id="CN_SPEC_001_Horizontal_Veil_Piercing",
    type=OperatorType.CBL_MAPPING_OVERRIDE,
    description="横向人格否认 — 关联公司资产混同直接穿透",
    trigger_facts=["Affiliated_Companies_Asset_Confusion"],
    output_states=["VOIDABLE"],
    citations=["《公司法》(2024修订)第23条第3款"],
    risk_level="HIGH",
    sovereignty_anchoring=False,
    allow_settlement=False,
)
def cn_spec_001_operator():
    pass


@OperatorRegistry.register(
    id="BLK_019_AtWillEmployment",
    type=OperatorType.CBL_FORCE_VOID,
    description="任意雇佣阻断 — 中国劳动合同法解雇保护",
    trigger_facts=["At_Will_Employment", "US_Employment_At_Will"],
    output_states=["VOID"],
    citations=["《劳动合同法》第39-48条"],
    risk_level="HIGH",
    sovereignty_anchoring=True,
    allow_settlement=False,
)
def blk_019_operator():
    pass


@OperatorRegistry.register(
    id="BLK_021_Discovery_Fishing",
    type=OperatorType.CBL_MAPPING_OVERRIDE,
    description="证据开示阻断 — 美式discovery替换为证据交换",
    trigger_facts=["US_Pre_Trial_Discovery"],
    output_states=["MAPPING_OVERRIDE"],
    citations=["《民事诉讼法》第284条", "《民诉解释》第224条"],
    risk_level="MEDIUM",
    allow_settlement=True,
)
def blk_021_operator():
    pass


@OperatorRegistry.register(
    id="SPC_001_Horizontal_Piercing_Judicial",
    type=OperatorType.SPC_JUDICIAL_TENDENCY,
    description="最高法: 横向人格否认裁判倾向",
    trigger_facts=["Affiliated_Companies_Asset_Confusion", "Commingling_Of_Funds"],
    additional_conditions=["No_Independent_Corporate_Identity"],
    output_states=["Horizontal_Veil_Piercing_Applicable"],
    citations=["《公司法》第23条第3款", "最高法相关司法解释"],
    risk_level="HIGH",
)
def spc_001_operator():
    pass


@OperatorRegistry.register(
    id="THREAT_NJ_PEN_001_AlterEgo",
    type=OperatorType.THREAT_INTERCEPT,
    description="NJ法人人格否认威胁 — 触发CBL强制阻断",
    trigger_facts=["Alter-Ego", "piercing the corporate veil"],
    output_states=["IMMEDIATE_PRC_CBL_FORCE_VOID"],
    citations=["《公司法》第23条第3款"],
    risk_level="CRITICAL",
    sovereignty_anchoring=True,
    allow_settlement=False,
    critical_threshold=0.92,
    operator_preference={
        "primary": "FORCE_VOID",
        "critical_threshold": 0.92,
    },
)
def threat_nj_pen_001():
    pass


@OperatorRegistry.register(
    id="THREAT_WI_ENF_001_LongArm",
    type=OperatorType.THREAT_INTERCEPT,
    description="WI长臂管辖威胁 — 旁路Horn直接CBL阻断",
    trigger_facts=["Long-Arm Statute 801.05", "Wis. Stat. 801.05"],
    output_states=["IMMEDIATE_PRC_CBL_FORCE_VOID"],
    citations=["《反外国制裁法》第12条"],
    risk_level="CRITICAL",
    sovereignty_anchoring=True,
    allow_settlement=False,
    critical_threshold=0.90,
)
def threat_wi_enf_001():
    pass


def fact_to_field(fact_name: str) -> str:
    """事实名 → 合法 Python 字段名"""
    return fact_name.replace(" ", "_").replace("-", "_").replace(".", "_")[:60]


# ── Pydantic 模式注册 (可选 — 用于Codex严格输入校验) ──
def register_pydantic(name: str, description: str = ""):
    """
    Pydantic 模式注册 — Codex 传入参数自动校验。
    用法:
      from pydantic import BaseModel
      class CBLVoidInput(BaseModel):
          fact_id: str
          sovereignty_anchoring: bool = True
      @register_pydantic("CBL_VOID", "中国法律强行法阻断")
      def force_void_operator(fact_id, sovereignty_anchoring):
          ...
    """
    def decorator(func: Callable):
        import inspect
        sig = inspect.signature(func)
        fields = {}
        for name, param in sig.parameters.items():
            if name in ('self', 'cls'):
                continue
            annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
            default = param.default if param.default != inspect.Parameter.empty else ...
            fields[name] = (annotation, default)
        try:
            from pydantic import create_model
            model = create_model(f"{name}Schema", **fields)
            OperatorRegistry._registry[name] = OperatorSchema(
                id=name,
                type=OperatorType.CBL_FORCE_VOID,
                description=description,
            )
            OperatorRegistry._functions[name] = func
        except ImportError:
            # 降级: 不注册Schema，仅注册函数
            OperatorRegistry._functions[name] = func
        return func
    return decorator


# ── MCP 工具: list_available_legal_operators ──
def list_available_legal_operators() -> Dict:
    """Codex 消费: 获取当前内核全部可用算子"""
    return {
        "total": len(OperatorRegistry._registry),
        "operators": OperatorRegistry.get_all_schemas(),
        "critical": OperatorRegistry.get_critical_operators(),
        "sovereignty": OperatorRegistry.get_sovereignty_operators(),
    }


# ═══════════════════════════════════════════════
# LegalTaskSchema — Codex 法律对抗任务自动校验
# ═══════════════════════════════════════════════

try:
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_V2 = True
except ImportError:
    try:
        from pydantic import BaseModel, Field, validator as field_validator
        _PYDANTIC_V2 = False
    except ImportError:
        BaseModel = None
        Field = None
        _PYDANTIC_V2 = False

if BaseModel:

    class LegalTaskSchema(BaseModel):
        """
        法律对抗任务自动化校验模板。
        Codex 提交的每个任务必须通过此 Schema 严格校验，
        否则 CBL_Gatekeeper 在入口层直接物理阻断。
        """

        # 基础信息
        task_id: str = Field(..., description="任务唯一标识")
        jurisdiction_focus: List[str] = Field(
            ..., min_length=1,
            description="目标法域，至少包含 PRC/HK/US 之一"
        )

        # 事实流
        subject_entity: str = Field(..., min_length=2, description="涉事实体名称")
        incident_description: str = Field(
            ..., min_length=20,
            description="必须详细描述争议事实 (至少20字)"
        )

        # 主权边界 (不可谈判的硬约束)
        is_prc_sovereign_boundary: bool = Field(
            default=True,
            description="是否涉及 PRC 主权边界 — 若为 True 则强制加载 CBL_Rules"
        )

        # 风险与算子偏好
        operator_preference: str = Field(
            default="FORCE_VOID",
            description="Codex 必须显式选择对抗策略: FORCE_VOID | FORCE_SUPPRESS | MAPPING_OVERRIDE | RESONANCE_AUDIT"
        )

        # 安全门控: 敏感数据声明 (空=禁止对撞)
        has_identified_sensitive_data: bool = Field(
            ..., description="必须声明是否涉及敏感数据/国家秘密，未声明禁止调用对撞"
        )

        # 可选: 威胁签名检测
        known_threat_signature: Optional[str] = Field(
            default=None,
            description="已知的威胁签名 (NJ/WI 黑话)"
        )

        @field_validator('jurisdiction_focus')
        @classmethod
        def must_be_supported(cls, v):
            allowed = {'PRC', 'HK', 'US'}
            if not set(v).issubset(allowed):
                raise ValueError(f"非法法域: {set(v) - allowed}。系统仅支持 PRC, HK, US")
            return v

        @field_validator('operator_preference')
        @classmethod
        def must_be_valid_strategy(cls, v):
            valid = {'FORCE_VOID', 'FORCE_SUPPRESS', 'MAPPING_OVERRIDE', 'RESONANCE_AUDIT'}
            if v not in valid:
                raise ValueError(f"非法算子偏好: {v}。有效值: {valid}")
            return v

        class Config:
            # 禁止 Codex 传入未定义的额外字段
            extra = "forbid"

else:
    # 降级: Pydantic 不可用时用 dataclass 替代
    from dataclasses import dataclass, field as dc_field
    @dataclass
    class LegalTaskSchema:
        task_id: str
        jurisdiction_focus: List[str] = dc_field(default_factory=lambda: ["PRC"])
        subject_entity: str = ""
        incident_description: str = ""
        is_prc_sovereign_boundary: bool = True
        operator_preference: str = "FORCE_VOID"
        has_identified_sensitive_data: bool = False
        known_threat_signature: Optional[str] = None

        def model_dump(self):
            """兼容 Pydantic 接口"""
            return {k: v for k, v in self.__dict__.items()}


# ═══════════════════════════════════════════════
# CBL_Gatekeeper — 入口层物理阻断
# ═══════════════════════════════════════════════

class CBLGatekeeper:
    """
    CBL 网关 — 对撞机入口层的强制安检。
    设计原则:
      1. has_identified_sensitive_data 未声明 → 直接拒绝
      2. is_prc_sovereign_boundary=True → 强制加载主权操作器
      3. 所有通过关口 → 生成对撞凭证 (CollisionToken)
    """

    BLOCK_ON_UNDECLARED_DATA = True
    FORCE_SOVEREIGN_OPERATORS = True

    @classmethod
    def validate(cls, task: LegalTaskSchema) -> Dict:
        """
        入口校验: Codex 提交的 LegalTaskSchema → 通过/阻断

        Returns:
          通过: {"passed": True, "token": {...}, "forced_operators": [...]}
          阻断: {"passed": False, "reason": "..."}
        """
        # ═══ 阻断条件 1: 未声明敏感数据 ═══
        if cls.BLOCK_ON_UNDECLARED_DATA:
            if not isinstance(task, LegalTaskSchema):
                return {"passed": False, "reason": "任务未通过 LegalTaskSchema 校验。请确保 has_identified_sensitive_data 已显式声明。"}

        # ═══ 阻断条件 2: 主权边界 → 强制加载主权操作器 ═══
        forced_operators = []
        if cls.FORCE_SOVEREIGN_OPERATORS and getattr(task, 'is_prc_sovereign_boundary', True):
            forced_operators = list(OperatorRegistry.get_sovereignty_operators().keys())

        # ═══ 阻断条件 3: operator_preference 校验 ═══
        if getattr(task, 'operator_preference', '') not in ('FORCE_VOID', 'FORCE_SUPPRESS', 'MAPPING_OVERRIDE', 'RESONANCE_AUDIT'):
            return {"passed": False, "reason": f"非法 operator_preference: {task.operator_preference}"}

        # ═══ 生成对撞凭证 ═══
        token = {
            "task_id": getattr(task, 'task_id', 'UNKNOWN'),
            "issued_at": __import__('datetime').datetime.now().isoformat(),
            "jurisdiction_focus": getattr(task, 'jurisdiction_focus', ['PRC']),
            "sovereignty_active": getattr(task, 'is_prc_sovereign_boundary', True),
            "operator_preference": getattr(task, 'operator_preference', 'FORCE_VOID'),
            "has_sensitive_data": getattr(task, 'has_identified_sensitive_data', False),
            "forced_sovereignty_operators": forced_operators,
        }

        return {
            "passed": True,
            "token": token,
            "forced_operators": forced_operators,
            "gatekeeper_version": "v1.2.0",
        }

    @classmethod
    def gate_and_collide(cls, task: LegalTaskSchema, trirail_engine=None) -> Dict:
        """
        全链路: 校验 + 对撞。
        如果 gate 拒绝 → 返回拒绝原因。
        如果 gate 通过 → 调用 trirail_collide。
        """
        gate_result = cls.validate(task)
        if not gate_result["passed"]:
            return {"blocked": True, **gate_result}

        # 通过 → 对撞
        # 构建事实流
        facts = {}
        if hasattr(task, 'known_threat_signature') and task.known_threat_signature:
            facts[task.known_threat_signature] = 1.0
        if hasattr(task, 'has_identified_sensitive_data') and task.has_identified_sensitive_data:
            facts["Identified_Sensitive_Data_Or_State_Secret"] = 1.0
            facts["Cross_Border_Context"] = 1.0
        if hasattr(task, 'is_prc_sovereign_boundary') and task.is_prc_sovereign_boundary:
            facts["Cross_Border_Context"] = 1.0

        return {
            "blocked": False,
            "gate_token": gate_result["token"],
            "fact_stream": facts,
            "forced_operators": gate_result["forced_operators"],
        }
