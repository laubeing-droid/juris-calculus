"""Evidence-bound lexical proposals from redacted text; never fact admission.

Only explicit dates, decimal CNY amounts and numeric durations are normalized.
Relative dates remain unresolved. No event role, legal anchor or legal effect is
inferred. The caller persists returned value/proposition bodies through the
existing content store; FactCandidateV4 is the existing proposal contract.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re

from compiler_core.contracts import ContentRefV4, FactCandidateV4, digest_value


_TOKEN = re.compile(
    r"(?P<date>(?<!\d)\d{4}(?:-\d{1,2}-\d{1,2}|年\d{1,2}月\d{1,2}日)(?!\d))"
    r"|(?P<relative>今日|今天|昨日|昨天|明日|明天|次日|当日|本月|上月|下月)"
    r"|(?P<amount>(?<![\d.,+\-负])[+\-负]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:万|亿)?元)"
    r"|(?P<duration>(?<![\d.])\d+(?:个)?(?:工作日|日|天|月|年))"
)


def extract_fact_candidates(
    text: str, *, document_ref: ContentRefV4, evidence_ref: ContentRefV4,
    redaction_state: str,
) -> list[dict[str, object]]:
    """Return proposals with half-open Unicode-code-point source spans.

    ``redaction_state`` is the trusted caller's admission result, not a claim
    that this function performs privacy scanning. Raw originals stay in A.
    """
    if redaction_state != "redacted":
        raise ValueError("redacted_input_required")
    proposals = []
    for match in _TOKEN.finditer(text):
        kind = match.lastgroup
        raw = match.group()
        normalized: object = None
        reason = "lexical_match_requires_lawyer_review"
        if kind == "date":
            parts = re.findall(r"\d+", raw)
            try:
                normalized = date(*(int(part) for part in parts)).isoformat()
            except ValueError:
                reason = "invalid_calendar_date"
        elif kind == "relative":
            reason = "relative_date_anchor_unverified"
        elif kind == "amount":
            number = raw[:-1].replace(",", "").replace("负", "-")
            multiplier = Decimal(1)
            if number[-1:] in {"万", "亿"}:
                multiplier = Decimal("10000" if number[-1] == "万" else "100000000")
                number = number[:-1]
            normalized = {"currency": "CNY", "amount": format(Decimal(number) * multiplier, "f")}
        elif kind == "duration":
            digits = re.match(r"\d+", raw).group()
            number = int(digits)
            unit = raw[len(digits):].removeprefix("个")
            normalized = {"count": number, "unit": {"天": "days", "日": "days", "工作日": "business_days", "月": "months", "年": "years"}[unit]}
        value = {"raw": raw, "normalized": normalized, "reason": reason, "status": "UNVERIFIED"}
        proposition = {
            "documentRef": document_ref.to_dict(), "kind": kind,
            "spanStart": match.start(), "spanEnd": match.end(),
            "offsetUnit": "unicode_code_points", "legalRole": None,
        }
        proposition_ref = ContentRefV4("fact-proposition", digest_value(proposition))
        candidate = FactCandidateV4(
            candidate_id=f"lexical-{proposition_ref.digest.hex}",
            proposition_ref=proposition_ref, value_kind=str(kind),
            value_ref=ContentRefV4("fact-value", digest_value(value)),
            evidence_refs=(evidence_ref,), producer_kind="deterministic_lexical_rule",
            proposal_ref=None,
        )
        proposals.append({"candidate": candidate.to_dict(), "proposition": proposition,
                          "value": value, "reviewRequired": True})
    return proposals
