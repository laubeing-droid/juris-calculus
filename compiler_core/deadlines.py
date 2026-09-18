"""Deadline and calendar computation (03 card step 5, mother plan §3.3.5).

Calendar primitives follow the frozen mother-plan code. The deadline
engine is extracted from Harness ``providers.py::StatutoryDeadlineService``
(read-only reference, legal-harness-repo) and reshaped onto the frozen
IFC-1 deadline DTOs. Harness keeps its own ``_snapshot``/``_event``,
matter binding and business receipts; JC owns pure calendar/rule math.

Frozen behaviors:

- calendar coverage is fail-closed: an unreleased or out-of-coverage
  calendar raises ``calendar_coverage_missing`` (``dueDate=null`` on the
  wire). The 2027 public holiday calendar is an empty placeholder and is
  never treated as released — no year is guessed.
- a rule picks its own anchor event field (行为发生/知悉/起诉/送达/开庭
  are separate fields and never collapse into ``served_at``);
- year/month periods use calendar-true shifting with end-of-month
  clamping (no 30/365-day approximations), leap years included;
- the criminal custody chain is staged rules (拘留/延长/提请/审查批捕),
  never a fixed 37-day constant;
- preservation caps are checked by property type while the running
  countdown stays anchored to the court-set deadline;
- suspension/resumption/interruption are distinct adjustment effects,
  never uniformly "shift by N days";
- calculation steps and a deterministic calculation hash ride on every
  result, mirroring the extracted Harness receipt.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import json

from compiler_core.canonical_serialization import canonical_bytes

CALENDAR_COVERAGE_MISSING = "calendar_coverage_missing"

EVENT_TIME_ANCHORS = ("occurredAt", "awareAt", "filedAt", "servedAt", "hearingAt")


class DeadlineError(ValueError):
    """Typed deadline failure; ``code`` carries the frozen error name."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}" if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Calendar primitives (mother plan §3.3.5, frozen code)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalendarSnapshot:
    version: str
    coverage_start: date
    coverage_end: date
    released: bool
    overrides: Mapping[str, bool]

    def is_business_day(self, day: date) -> bool:
        if not self.released or not self.coverage_start <= day <= self.coverage_end:
            raise DeadlineError(
                CALENDAR_COVERAGE_MISSING,
                f"{day.isoformat()} outside released coverage "
                f"[{self.coverage_start.isoformat()}, {self.coverage_end.isoformat()}]",
            )
        explicit = self.overrides.get(day.isoformat())
        return explicit if explicit is not None else day.weekday() < 5


def calendar_shift(start: date, count: int, unit: str) -> date:
    if unit not in {"months", "years"}:
        raise DeadlineError("unsupported_calendar_unit", unit)
    year = start.year + (count if unit == "years" else 0)
    month = start.month + (count if unit == "months" else 0)
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    return start.replace(
        year=year,
        month=month,
        day=min(start.day, monthrange(year, month)[1]),
    )


def add_business_days(
    start: date,
    count: int,
    calendar: CalendarSnapshot,
) -> date:
    if count < 0:
        raise DeadlineError("negative_business_duration")
    cursor = start
    remaining = count
    while remaining:
        cursor += timedelta(days=1)
        if calendar.is_business_day(cursor):
            remaining -= 1
    return cursor


def roll_forward(day: date, calendar: CalendarSnapshot) -> date:
    cursor = day
    while not calendar.is_business_day(cursor):
        cursor += timedelta(days=1)
    return cursor


# ---------------------------------------------------------------------------
# Branch table (mother plan §3.35 branch table, data-driven)
# ---------------------------------------------------------------------------

# Each branch names the legal shape its rules follow. ``roll_forward_end``
# marks whether a calendar-day period landing on a rest day moves to the
# next business day (期间末日为节假日的顺延). No branch carries a numeric
# shortcut constant (the criminal custody chain is staged rules).
BRANCH_TABLE: dict[str, dict[str, Any]] = {
    "court_specified": {
        "description": "法院指定日期原样登记，不调用法定天数覆盖",
        "roll_forward_end": False,
        "requires_duration": False,
    },
    "limitation_period": {
        "description": "诉讼时效：年/月日历移动，月末与闰年按冻结规则",
        "roll_forward_end": True,
        "requires_duration": True,
        "supports_adjustments": True,
    },
    "evidence_period": {
        "description": "举证期限：程序/送达/主体条件独立",
        "roll_forward_end": True,
        "requires_duration": True,
    },
    "appeal_period": {
        "description": "上诉期限：送达锚定，条件独立",
        "roll_forward_end": True,
        "requires_duration": True,
    },
    "arbitration_period": {
        "description": "仲裁期限：程序条件独立",
        "roll_forward_end": True,
        "requires_duration": True,
    },
    "criminal_custody": {
        "description": "刑拘链：拘留/延长/提请/审查批捕分别事件与规则",
        "roll_forward_end": False,
        "requires_duration": True,
        "staged": True,
    },
    "preservation": {
        "description": "保全：财产类型上限核对，当前倒计时按法院届满日",
        "roll_forward_end": False,
        "requires_duration": False,
        "cap_check": True,
    },
    "preservation_renewal": {
        "description": "续保：申请日/法院续行决定分别记录，不自动延长届满日",
        "roll_forward_end": False,
        "requires_duration": False,
    },
    "pre_litigation_preservation": {
        "description": "诉前保全：起诉/仲裁触发条件与期限绑定",
        "roll_forward_end": True,
        "requires_duration": True,
    },
    "archive_organization": {
        "description": "归档整理：整理义务与保管/处置策略分开",
        "roll_forward_end": False,
        "requires_duration": False,
    },
}


def load_deadline_rules(configs_root: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """Load the versioned deadline rule registry from a configs root.

    The registry lives next to the rule packs (``configs/deadline_rules*.yaml``)
    and must be shipped explicitly in the wheel; see
    ``JCClient.calculate_deadlines`` for the resolution path.
    """

    from pathlib import Path

    import yaml

    root = Path(configs_root)
    registry: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(root.glob("deadline_rules*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != "deadline-rules/1":
            raise DeadlineError("deadline_registry_schema_invalid", str(path))
        for rule in document.get("rules", []):
            branch = str(rule.get("branch", ""))
            if branch not in BRANCH_TABLE:
                raise DeadlineError("deadline_branch_unknown", f"{rule.get('ruleId')}:{branch}")
            key = (str(rule["ruleId"]), str(rule["version"]))
            if key in registry:
                raise DeadlineError("deadline_rule_duplicate", str(key))
            registry[key] = rule
    return registry


def _event_time_value(event: Mapping[str, Any], anchor: str) -> tuple[str, str]:
    field = event.get(anchor)
    if not isinstance(field, Mapping):
        raise DeadlineError(f"deadline_trigger_event_field_missing:{anchor}")
    value = field.get("value")
    precision = str(field.get("precision", "unknown"))
    if value is None or precision == "unknown":
        raise DeadlineError("deadline_trigger_event_time_unknown", anchor)
    if precision not in {"date", "instant", "month"}:
        raise DeadlineError("deadline_trigger_event_time_unknown", f"{anchor}:{precision}")
    if precision == "month":
        raise DeadlineError("deadline_trigger_event_time_too_coarse", anchor)
    return str(value), precision


# ---------------------------------------------------------------------------
# Deadline computation
# ---------------------------------------------------------------------------


def _calculation_hash(seed: Mapping[str, Any]) -> str:
    payload = json.loads(canonical_bytes(seed).decode("utf-8"))
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def compute_deadline(
    *,
    rule: Mapping[str, Any],
    event: Mapping[str, Any],
    calendar: CalendarSnapshot,
    matter_id: str,
    event_id: str,
    event_revision: int,
    now: datetime,
) -> dict[str, Any]:
    """Compute one deadline per the extracted Harness algorithm.

    ``rule`` is one registry entry; ``event`` is the resolved IFC-1
    ProcedureEvent body; the result is an IFC-1 Deadline-shaped dict with
    the calculation receipt folded in as ``calculation``.
    """

    branch = str(rule["branch"])
    spec = BRANCH_TABLE[branch]
    anchor = str(rule.get("anchor", ""))
    if anchor not in EVENT_TIME_ANCHORS:
        raise DeadlineError("deadline_anchor_invalid", anchor)
    trigger_raw, precision = _event_time_value(event, anchor)
    try:
        trigger_day = date.fromisoformat(trigger_raw[:10])
    except ValueError as error:
        raise DeadlineError("deadline_trigger_event_time_invalid", trigger_raw) from error

    steps: list[str] = [
        f"trigger:{trigger_raw}",
        f"anchor:{anchor}",
        f"branch:{branch}",
    ]
    adjustments_used: list[str] = []

    date_origin = "calculated"
    due_date: date | None = None

    if branch == "court_specified":
        court_day_raw = rule.get("courtSpecifiedDate") or event.get("hearingAt", {}).get("value")
        if not court_day_raw:
            raise DeadlineError("deadline_court_date_missing")
        due_date = date.fromisoformat(str(court_day_raw)[:10])
        steps.append(f"court_specified:{due_date.isoformat()}")
    elif branch == "preservation":
        # 上限按财产类型核对；当前倒计时按法院届满日（court-set）。
        cap_days = {
            "bank_deposit": 365,
            "chattel": 730,
            "real_estate": 1095,
        }.get(str(rule.get("propertyType", "")))
        court_day_raw = rule.get("courtSpecifiedDate") or event.get("hearingAt", {}).get("value")
        if not court_day_raw:
            raise DeadlineError("deadline_court_date_missing")
        expiry = date.fromisoformat(str(court_day_raw)[:10])
        steps.append(f"court_expiry:{expiry.isoformat()}")
        if cap_days is not None:
            statutory_cap = trigger_day + timedelta(days=cap_days)
            steps.append(
                f"cap_check:propertyType={rule.get('propertyType')},"
                f"statutory_cap={statutory_cap.isoformat()},court_expiry={expiry.isoformat()}"
            )
            if expiry > statutory_cap:
                raise DeadlineError("preservation_cap_exceeded", str(rule.get("propertyType")))
        due_date = expiry
    elif branch == "preservation_renewal":
        # 申请窗口锚定在法院届满日前 N 日；续保申请绝不自动延长届满日。
        window_days = int(rule.get("windowDays", 30))
        court_day_raw = rule.get("courtSpecifiedDate")
        if not court_day_raw:
            raise DeadlineError("deadline_court_date_missing")
        expiry = date.fromisoformat(str(court_day_raw)[:10])
        due_date = expiry - timedelta(days=window_days)
        steps.append(f"renewal_window:expiry={expiry.isoformat()},days={window_days}")
        steps.append("no_auto_extension:true")
    elif branch == "archive_organization":
        due_date = trigger_day + timedelta(days=int(rule.get("durationDays", 0)))
        steps.append(f"organization_due:{due_date.isoformat()}")
        steps.append("retention_policy_separate:true")
    else:
        # Generic duration branch: limitation / evidence / appeal /
        # arbitration / criminal custody / pre-litigation preservation.
        duration = int(rule["durationDays"])
        duration_unit = str(rule.get("durationUnit", "days"))
        counting_mode = str(rule.get("countingMode", "CALENDAR_DAYS"))
        offset = int(rule.get("startOffsetDays", 0))
        boundary_inclusive = bool(rule.get("boundaryInclusive", False))
        starts_date = trigger_day + timedelta(days=offset)
        steps.append(f"start_offset_days:{offset}")
        starts_date_str = starts_date.isoformat()
        steps.append(f"starts_on:{starts_date_str}")
        inclusive_adjustment = 1 if boundary_inclusive else 0
        if duration_unit in {"months", "years"}:
            if counting_mode != "CALENDAR_PERIODS":
                raise DeadlineError("deadline_counting_mode_invalid", counting_mode)
            raw_expiry = calendar_shift(starts_date, duration, unit=duration_unit)
            raw_expiry = raw_expiry - timedelta(days=inclusive_adjustment)
            steps.append(f"calendar_period:{duration}{duration_unit}")
        elif counting_mode == "CALENDAR_DAYS":
            raw_expiry = starts_date + timedelta(days=duration - inclusive_adjustment)
            steps.append(f"calendar_days:{duration}")
        elif counting_mode == "BUSINESS_DAYS":
            required_calendar_version = rule.get("calendarVersion")
            if required_calendar_version and str(required_calendar_version) != calendar.version:
                raise DeadlineError("holiday_calendar_snapshot_mismatch")
            count = duration + (0 if boundary_inclusive else 1)
            raw_expiry = add_business_days(starts_date, count, calendar)
            steps.append(f"business_days:{count}")
        else:
            raise DeadlineError("deadline_counting_mode_invalid", counting_mode)

        due_date = raw_expiry
        if spec.get("roll_forward_end") and counting_mode != "BUSINESS_DAYS":
            try:
                rolled = roll_forward(due_date, calendar)
            except DeadlineError:
                rolled = due_date  # out-of-coverage end day: report the gap below
            if rolled != due_date:
                steps.append(f"roll_forward:{due_date.isoformat()}->{rolled.isoformat()}")
            due_date = rolled

        # Adjustment effects: suspension extends by the suspended span,
        # interruption restarts the whole period from the interrupting
        # event, resumption restarts only the remaining span. These are
        # distinct effects, never a uniform day shift.
        for adjustment in rule.get("adjustments", []) or []:
            kind = str(adjustment.get("kind"))
            if kind == "suspension":
                span = (date.fromisoformat(adjustment["to"]) - date.fromisoformat(adjustment["from"])).days
                due_date = due_date + timedelta(days=span)
                steps.append(f"suspension:+{span}d")
            elif kind == "interruption":
                restart = date.fromisoformat(adjustment["at"])
                if duration_unit in {"months", "years"}:
                    due_date = calendar_shift(restart, duration, unit=duration_unit)
                else:
                    due_date = restart + timedelta(days=duration - inclusive_adjustment)
                steps.append(f"interruption:restart_from={restart.isoformat()}")
            elif kind == "resumption":
                resume = date.fromisoformat(adjustment["at"])
                remaining = (due_date - resume).days
                due_date = resume + timedelta(days=remaining)
                steps.append(f"resumption:remaining={remaining}d")
            else:
                raise DeadlineError("deadline_adjustment_kind_invalid", kind)
            adjustments_used.append(str(adjustment.get("eventRef", "")))

    if due_date is not None:
        steps.append(f"expires_on:{due_date.isoformat()}")
        try:
            calendar.is_business_day(due_date)
            coverage_note = "covered"
        except DeadlineError:
            coverage_note = "calendar_coverage_missing"
        if coverage_note == "calendar_coverage_missing":
            # The computed date leaves the released coverage window: the
            # gap is reported honestly, no holiday is guessed.
            due_date = None
            steps.append("calendar_coverage_missing:true")

    zone = str(rule.get("timezone", "Asia/Shanghai"))
    try:
        ZoneInfo(zone)
    except ZoneInfoNotFoundError as error:
        raise DeadlineError("deadline_rule_timezone_invalid", zone) from error

    due_at = None
    if due_date is not None:
        due_at = datetime.combine(due_date, time(23, 59, 59), ZoneInfo(zone)).isoformat()

    rule_id = str(rule["ruleId"])
    rule_version = str(rule["version"])
    seed = {
        "rule_id": rule_id,
        "rule_version": rule_version,
        "branch": branch,
        "event_id": event_id,
        "event_revision": event_revision,
        "trigger": trigger_raw,
        "steps": steps,
        "due_date": due_date.isoformat() if due_date else None,
        "due_at": due_at,
    }
    digest = _calculation_hash(seed)
    receipt_ref = {
        "owner": "jc",
        "kind": "calculation-receipt",
        "id": f"deadline-{digest[:24]}",
        "version": "1",
        "matterId": matter_id,
        "digest": f"sha256:{digest}",
    }
    deadline_ref = {
        "owner": "jc",
        "kind": "deadline",
        "id": f"deadline-{digest[:24]}",
        "version": "1",
        "matterId": matter_id,
        "digest": f"sha256:{digest}",
    }
    rule_binding = {
        "ruleId": rule_id,
        "ruleVersion": rule_version,
        "ruleRef": rule.get("ruleRef") or {
            "owner": "jc", "kind": "rule", "id": rule_id, "version": rule_version,
            "matterId": matter_id, "digest": None,
        },
        "knowledgeSnapshotRef": rule.get("knowledgeSnapshotRef") or {
            "owner": "jc", "kind": "law-snapshot", "id": f"{rule_id}@{rule_version}",
            "version": "1", "matterId": matter_id, "digest": None,
        },
        "locator": str(rule.get("locator", f"deadline-rules/{rule_id}#{branch}")),
        "admissionReceiptRef": rule.get("admissionReceiptRef") or None,
    }
    return {
        "id": f"deadline-{digest[:24]}",
        "revision": 1,
        "ref": deadline_ref,
        "matterId": matter_id,
        "eventId": event_id,
        "eventRevision": event_revision,
        "rule": rule_binding,
        "calendar": {
            "ref": {
                "owner": "jc", "kind": "calendar", "id": calendar.version, "version": "1",
                "matterId": matter_id, "digest": None,
            },
            "coverageStart": calendar.coverage_start.isoformat(),
            "coverageEnd": calendar.coverage_end.isoformat(),
            "released": calendar.released,
            "sourceRefs": [],
            "checkedAt": now.astimezone().isoformat(),
        },
        "dateOrigin": date_origin,
        "dueDate": due_date.isoformat() if due_date else None,
        "dueAt": due_at,
        "parentDeadlineId": None,
        "manualOverrideRef": None,
        "adjustmentEventRefs": adjustments_used,
        "calculationSteps": steps,
        "calculationReceiptRef": receipt_ref,
        "obligations": [],
        "current": True,
        "supersedesRevision": None,
        "calculation": {
            "receipt_id": f"deadline-{digest[:24]}",
            "calculation_hash": digest,
            "trigger_at": trigger_raw,
            "starts_on": steps[4] if len(steps) > 4 else None,
            "expires_at": due_at,
            "timezone": zone,
            "branch": branch,
        },
    }
