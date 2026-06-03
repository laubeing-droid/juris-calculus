#!/usr/bin/env python3
"""
juris-calculus Pipeline 结构化 Schema v1.0
Pydantic 紧箍咒 — 大模型输出格式铁律
"""
from typing import List, Optional
from pydantic import BaseModel, Field

class ExtractedFact(BaseModel):
    atom: str = Field(
        description="ontology_map.yaml 定义的标准原子ID，如 Contract.Breach.FUNDAMENTAL 或 Defense.LIMITATION_EXPIRED"
    )
    source_quote: str = Field(
        description="激活该原子的案卷原文片段"
    )
    alignment_strength: int = Field(
        ge=1, le=5,
        description="跨法域对齐强度: 5=基本等同, 4=高度近似, 3=功能近似, 2=部分重叠, 1=不建议对应"
    )
    risk_label: bool = Field(
        default=False,
        description="是否触发 PRC-US 对齐框架的高危风险标签"
    )

class LegalFactPayload(BaseModel):
    reasoning_path: str = Field(
        default="",
        description="大模型法律语义消解的思维链(Chain of Thought)"
    )
    facts: List[ExtractedFact] = Field(
        description="提取的布尔事实原子列表"
    )
