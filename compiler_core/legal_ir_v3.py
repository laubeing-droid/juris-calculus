#!/usr/bin/env python3
"""Minimal Typed Legal IR v3 compatibility layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from compiler_core.types import LegalRule


class LegalType(str, Enum):
    LEGAL_PERSON = "LegalPerson"
    DATE = "Date"
    DECIMAL = "Decimal"
    MONEY = "Money"
    BOOLEAN = "Boolean"
    EVIDENCE = "Evidence"
    JURISDICTION = "Jurisdiction"


class RuleType(str, Enum):
    HORN = "horn"
    DEFEASIBLE_OBLIGATION = "defeasible_obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"
    CONSTITUTIVE = "constitutive"


@dataclass
class SourceRef:
    authority_id: str
    source_span: str = ""
    source_hash: str = ""


@dataclass
class Validity:
    jurisdiction: str
    valid_from: str = ""
    valid_to: Optional[str] = None
    legal_version: str = ""


@dataclass
class TypedVariable:
    name: str
    type: LegalType


@dataclass
class Condition:
    predicate: str
    args: List[str] = field(default_factory=list)
    negated: bool = False


@dataclass
class ConditionTree:
    all: List[Condition] = field(default_factory=list)
    any: List[Condition] = field(default_factory=list)
    not_conditions: List[Condition] = field(default_factory=list)


@dataclass
class LegalIRRule:
    rule_id: str
    rule_type: RuleType
    validity: Validity
    source: SourceRef
    variables: List[TypedVariable] = field(default_factory=list)
    conditions: ConditionTree = field(default_factory=ConditionTree)
    conclusion: Condition = field(default_factory=lambda: Condition(predicate=""))
    exceptions: List[str] = field(default_factory=list)
    priority: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legal_rule(cls, rule: LegalRule, jurisdiction: str = "") -> "LegalIRRule":
        conditions = ConditionTree(
            all=[Condition(predicate=premise) for premise in rule.premise_atoms]
        )
        return cls(
            rule_id=rule.id,
            rule_type=RuleType.HORN if rule.head_type == "HORN" else RuleType.CONSTITUTIVE,
            validity=Validity(jurisdiction=jurisdiction or rule.jurisdiction or "UNKNOWN",
                              valid_from=rule.valid_from,
                              valid_to=rule.valid_to or None),
            source=SourceRef(authority_id=rule.source_anchor or "UNANCHORED"),
            conditions=conditions,
            conclusion=Condition(predicate=rule.head_claim),
            exceptions=list(rule.exception_chain),
            priority={
                "authority_rank": rule.authority_rank,
                "priority_over": list(rule.priority_over),
            },
        )

    def to_legal_rule(self) -> LegalRule:
        return LegalRule(
            id=self.rule_id,
            premise_atoms=[condition.predicate for condition in self.conditions.all],
            head_claim=self.conclusion.predicate,
            exception_chain=list(self.exceptions),
            head_type="HORN" if self.rule_type == RuleType.HORN else "NON_HORN",
            source_anchor=self.source.authority_id,
            valid_from=self.validity.valid_from,
            valid_to=self.validity.valid_to or "",
            jurisdiction=self.validity.jurisdiction,
            authority_rank=str(self.priority.get("authority_rank", "")),
            priority_over=list(self.priority.get("priority_over", [])),
        )


def legal_ir_rule_from_dict(data: Dict[str, Any]) -> LegalIRRule:
    variables = [
        TypedVariable(name=item["name"], type=LegalType(item["type"]))
        for item in data.get("variables", [])
    ]
    conditions = data.get("conditions", {})
    return LegalIRRule(
        rule_id=data["rule_id"],
        rule_type=RuleType(data.get("rule_type", "horn")),
        validity=Validity(**data.get("validity", {})),
        source=SourceRef(**data.get("source", {})),
        variables=variables,
        conditions=ConditionTree(
            all=[_condition(item) for item in conditions.get("all", [])],
            any=[_condition(item) for item in conditions.get("any", [])],
            not_conditions=[_condition(item) for item in conditions.get("not", [])],
        ),
        conclusion=_condition(data.get("conclusion", {})),
        exceptions=list(data.get("exceptions", [])),
        priority=dict(data.get("priority", {})),
    )


def _condition(data: Dict[str, Any]) -> Condition:
    return Condition(
        predicate=data.get("predicate", ""),
        args=list(data.get("args", [])),
        negated=bool(data.get("negated", False)),
    )
