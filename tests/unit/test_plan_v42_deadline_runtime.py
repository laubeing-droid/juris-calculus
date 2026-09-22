"""Synthetic legal premises through JCClient + real YAML registry/calculator.

The synthetic calendar is explicitly released for 2000-2050 and is not a
statement about future Chinese holidays. All events and review flags are test
premises; expected arithmetic does not establish legal truth or fact admission.
"""
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from compiler_core.client import ClientV4Error, create_local_client
from tests.local.test_local_runtime import RULE_PACK

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def raises_code(code):
    with pytest.raises(ClientV4Error) as error:
        yield
    assert error.value.code == code


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("v42-deadline-runtime")
    packs = root / "packs"
    packs.mkdir()
    (packs / "jc-local-pack.json").write_text(json.dumps(RULE_PACK), encoding="utf-8")
    return create_local_client(root / "state", packs)


def time_value(day):
    return {"value": day, "precision": "date", "timezone": "Asia/Shanghai", "sourceRefs": []}


def calculate(client, rule_id, *, context=None, occurred=None, aware="2026-03-02",
              served="2026-03-02", now="2026-03-02T00:00:00+00:00", configs=None,
              coverage_end="2050-12-31"):
    legal_context = {
        "subjectQualified": True, "specialRulesReviewed": True, "serviceConfirmed": True,
        "appealable": True, "inCustody": True, "retrialGround": "ordinary",
        "judgmentEffectiveAt": time_value("2026-03-02"), "performanceMode": "specified",
        "performanceDueAt": time_value("2026-03-02"),
        "finalInstallmentDueAt": time_value("2026-03-02"),
        "domicileInPRC": True, "courtExtensionGranted": False, "answerPeriodApplicable": True,
        "wageArrears": False, "absenceNotAttributable": True, "effectiveInstrumentHarmsRights": True,
        "limitationApplies": True, "courtLongstopExtended": False, "authorityEvidence": True,
    }
    legal_context.update(context or {})
    event_ref = client.register_event({
        "id": "synthetic-event", "revision": 1, "matterId": "synthetic-matter",
        "occurredAt": time_value(occurred or aware), "awareAt": time_value(aware), "servedAt": time_value(served),
        "legalContext": legal_context,
    })
    request = {"matterId": "synthetic-matter", "eventRef": event_ref, "eventRevision": 1,
               "rules": [{"ruleId": rule_id, "ruleVersion": "1"}], "now": now,
               "calendar": {"ref": None, "coverageStart": "2000-01-01", "coverageEnd": coverage_end,
                            "released": True, "sourceRefs": [], "checkedAt": now}}
    if configs:
        request["configsRoot"] = str(configs)
    return next(row for row in client.calculate_deadlines(request)["deadlines"] if row["rule"]["ruleId"] == rule_id)


@pytest.mark.parametrize("rule_id,expected", [
    ("criminal.appeal.judgment", "2026-03-12"),
    ("criminal.appeal.ruling", "2026-03-07"),
    ("civil.retrial.application", "2026-09-02"),
    ("civil.enforcement.application", "2028-03-02"),
    ("civil.jurisdiction.objection", "2026-03-17"),
    ("civil.answer.first_instance", "2026-03-17"),
    ("labor.arbitration.application", "2027-03-02"),
    ("civil.third_party.revocation", "2026-09-02"),
    ("civil.limitation.longstop", "2026-03-02"),
])
def test_RT01_all_nine_rules_execute_through_real_public_entry(client, rule_id, expected):
    result = calculate(client, rule_id, occurred="2006-03-02" if rule_id.endswith("longstop") else "2026-03-02")
    assert result["dueDate"] == expected
    assert "legal_result:candidate_requires_lawyer_review" in result["calculationSteps"]


def test_RT02_yaml_only_changes_duration_anchor_and_legal_condition(client, tmp_path):
    document = yaml.safe_load((ROOT / "configs/deadline_rules_cn.v1.yaml").read_text(encoding="utf-8"))
    rule = next(item for item in document["rules"] if item["ruleId"] == "civil.answer.first_instance")
    draft = {"schema_version": "deadline-rules/1", "rules": [rule]}
    path = tmp_path / "deadline_rules_synthetic.yaml"
    rule["decision"]["cases"][0]["set"]["durationDays"] = 12
    path.write_text(yaml.safe_dump(draft), encoding="utf-8")
    assert calculate(client, rule["ruleId"], configs=tmp_path)["dueDate"] == "2026-03-16"
    rule["decision"]["cases"][0]["set"].update(anchor="awareAt", durationDays=15)
    path.write_text(yaml.safe_dump(draft), encoding="utf-8")
    assert calculate(client, rule["ruleId"], aware="2026-03-10", configs=tmp_path)["dueDate"] == "2026-03-25"
    rule["decision"]["require"].append({"field": "legalContext.syntheticReviewed", "equals": True})
    path.write_text(yaml.safe_dump(draft), encoding="utf-8")
    with raises_code("deadline_legal_premise_unverified"):
        calculate(client, rule["ruleId"], configs=tmp_path)
    assert calculate(client, rule["ruleId"], context={"syntheticReviewed": True}, configs=tmp_path)["dueDate"] == "2026-03-17"


@pytest.mark.parametrize("bad_condition", [
    {"field": "legalContext.subjectQualified", "greaterThan": 0},
    {"field": "legalContext.subjectQualified", "equals": True, "ignoreMissing": True},
])
def test_RT03_unknown_yaml_semantics_fail_closed(client, tmp_path, bad_condition):
    document = yaml.safe_load((ROOT / "configs/deadline_rules_cn.v1.yaml").read_text(encoding="utf-8"))
    rule = next(item for item in document["rules"] if item["ruleId"] == "civil.third_party.revocation")
    rule["decision"]["require"] = [bad_condition]
    (tmp_path / "deadline_rules_synthetic.yaml").write_text(yaml.safe_dump({"schema_version": "deadline-rules/1", "rules": [rule]}), encoding="utf-8")
    with raises_code("deadline_rule_syntax_invalid"):
        calculate(client, rule["ruleId"], configs=tmp_path)


@pytest.mark.parametrize("ground", ["211.1", "211.3", "211.12", "211.13"])
def test_RT04_retrial_special_ground_uses_awareness(client, ground):
    assert calculate(client, "civil.retrial.application", aware="2026-04-02",
                     context={"retrialGround": ground})["dueDate"] == "2026-10-02"


@pytest.mark.parametrize("mode,field,day,expected", [
    ("specified", "performanceDueAt", "2026-04-03", "2028-04-03"),
    ("installments", "finalInstallmentDueAt", "2026-05-03", "2028-05-03"),
    ("unspecified", "judgmentEffectiveAt", "2026-06-02", "2028-06-02"),
])
def test_RT05_enforcement_three_distinct_anchors(client, mode, field, day, expected):
    assert calculate(client, "civil.enforcement.application",
                     context={"performanceMode": mode, field: time_value(day)})["dueDate"] == expected


@pytest.mark.parametrize("rule_id", ["civil.answer.first_instance", "civil.jurisdiction.objection"])
def test_RT06_domicile_and_court_extension_are_yaml_cases(client, rule_id):
    assert calculate(client, rule_id, context={"domicileInPRC": False})["dueDate"] == "2026-04-01"
    assert calculate(client, rule_id, context={"courtExtensionGranted": True,
                                             "courtAnswerDueAt": time_value("2026-04-10")})["dueDate"] == "2026-04-10"
    with raises_code("deadline_legal_premise_unverified"):
        calculate(client, rule_id, context={"domicileInPRC": None})


def test_RT07_labor_wage_exception_is_not_a_one_year_deadline(client):
    with raises_code("deadline_legal_review_required"):
        calculate(client, "labor.arbitration.application", context={"wageArrears": True, "employmentEnded": False})
    assert calculate(client, "labor.arbitration.application", context={"wageArrears": True,
        "employmentEnded": True, "employmentEndedAt": time_value("2026-04-02")})["dueDate"] == "2027-04-02"


def test_RT08_longstop_is_review_not_extinction_and_keeps_court_extension(client):
    with raises_code("limitation_cap_review_required"):
        calculate(client, "civil.limitation.longstop", occurred="2006-02-01")
    assert calculate(client, "civil.limitation.longstop", occurred="2006-02-01", context={
        "courtLongstopExtended": True, "courtExtendedDueAt": time_value("2026-04-10")})["dueDate"] == "2026-04-10"
    with raises_code("deadline_legal_premise_unverified"):
        calculate(client, "civil.limitation.longstop", context={"limitationApplies": False})
    # UTC March 2 16:00 is already March 3 in the configured China timezone.
    with raises_code("limitation_cap_review_required"):
        calculate(client, "civil.limitation.longstop", occurred="2006-03-02", now="2026-03-02T16:00:00+00:00")


@pytest.mark.parametrize("count,expected", [(1, "2026-03-05"), (2, "2026-03-06"), (3, "2026-03-07"), (4, "2026-03-08")])
def test_RT09_custody_approved_extension_adds_to_original_three_days(client, count, expected):
    assert calculate(client, "criminal.custody.detention.extended", occurred="2026-03-01",
                     context={"approvedExtensionDays": count, "extensionApproved": True})["dueDate"] == expected


def suspension(start, end, **values):
    return {"kind": "suspension", "from": start, "to": end, "ground": "force_majeure",
            "cannotExercise": True, "legalGroundConfirmed": True, "eventRef": "synthetic-obstacle", **values}


@pytest.mark.parametrize("start,end,expected", [
    ("2024-06-01", "2024-08-31", "2026-06-30"),
    ("2025-12-01", "2026-08-31", "2027-03-01"),
    ("2026-01-01", "2026-08-31", "2027-03-01"),
    ("2026-06-30", "2026-08-31", "2027-03-01"),
    ("2026-07-01", "2026-08-31", "2026-06-30"),
    ("2026-01-01", "2026-01-02", "2026-07-02"),
])
def test_RT10_civil194_six_timings_real_entry(client, start, end, expected):
    result = calculate(client, "civil.limitation.general", aware="2023-06-30",
                       context={"adjustments": [suspension(start, end)]})
    assert result["dueDate"] == expected
    if end == "2026-08-31" and expected == "2027-03-01":
        assert "roll_forward:2027-02-28->2027-03-01" in result["calculationSteps"]


def test_RT11_calendar_gap_stays_gap_after_month_end(client):
    result = calculate(client, "civil.limitation.general", aware="2023-06-30", coverage_end="2026-12-31",
                       context={"adjustments": [suspension("2026-01-01", "2026-08-31")]})
    assert result["dueDate"] is None
    assert "calendar_coverage_missing:true" in result["calculationSteps"]


@pytest.mark.parametrize("changes", [{"cannotExercise": None}, {"legalGroundConfirmed": False},
                                     {"ground": "other_obstacle"}, {"ground": "invented_ground"}])
def test_RT12_obstacle_legal_facts_are_required(client, changes):
    with raises_code("deadline_legal_premise_unverified"):
        calculate(client, "civil.limitation.general", aware="2023-06-30",
                  context={"adjustments": [suspension("2026-01-01", "2026-08-31", **changes)]})


@pytest.mark.parametrize("ground", ["force_majeure", "no_legal_representative", "successor_or_estate_admin_undetermined",
                                    "controlled_by_obligor", "other_obstacle"])
def test_RT13_all_statutory_obstacle_categories_require_reviewed_fact(client, ground):
    assert calculate(client, "civil.limitation.general", aware="2023-06-30",
        context={"adjustments": [suspension("2026-01-01", "2026-08-31", ground=ground,
                                            legalReviewRef="synthetic-reviewed-other-ground")]})["dueDate"] == "2027-03-01"


def test_RT14_interruption_changes_effective_suspension_window(client):
    adjustments = [{"kind": "interruption", "at": "2025-03-01", "legalGroundConfirmed": True,
                    "eventRef": "synthetic-interruption"}, suspension("2026-01-01", "2026-08-31")]
    assert calculate(client, "civil.limitation.general", aware="2023-06-30",
                     context={"adjustments": adjustments})["dueDate"] == "2028-03-01"
    with raises_code("deadline_adjustment_order_unverified"):
        calculate(client, "civil.limitation.general", aware="2023-06-30", context={"adjustments": list(reversed(adjustments))})


def test_RT15_labor_suspension_continues_without_civil_six_month_reset(client):
    assert calculate(client, "labor.arbitration.application", aware="2025-06-30", context={
        "adjustments": [suspension("2026-01-01", "2026-01-11")]
    })["dueDate"] == "2026-07-10"


def test_RT16_general_limitation_expands_yaml_companion_without_caller_reminder(client):
    with raises_code("limitation_cap_review_required"):
        calculate(client, "civil.limitation.general", occurred="2000-03-02", aware="2026-03-02")
    result = calculate(client, "civil.limitation.general", occurred="2008-03-02", aware="2026-03-02")
    assert result["dueDate"] == "2028-03-02"
    assert "companion_limit:civil.limitation.longstop:2028-03-02" in result["calculationSteps"]
    assert calculate(client, "civil.answer.first_instance", occurred="2000-03-02")["dueDate"] == "2026-03-17"
    assert calculate(client, "labor.arbitration.application", occurred="2000-03-02")["dueDate"] == "2027-03-02"
    # A much later cap has a provable raw lower bound; an unavailable far-future
    # holiday calendar must not erase a current earlier ordinary expiry.
    assert calculate(client, "civil.limitation.general", occurred="2023-06-30", aware="2023-06-30",
                     coverage_end="2026-12-31")["dueDate"] == "2026-06-30"


@pytest.mark.parametrize("target,code", [("civil.limitation.general", "deadline_companion_cycle"),
                                       ("synthetic.missing", "deadline_companion_unknown")])
def test_RT17_yaml_companion_graph_rejects_cycle_and_unknown(client, tmp_path, target, code):
    document = yaml.safe_load((ROOT / "configs/deadline_rules_cn.v1.yaml").read_text(encoding="utf-8"))
    rule = next(item for item in document["rules"] if item["ruleId"] == "civil.limitation.general")
    rule["requiredCompanions"] = [{"ruleId": target, "ruleVersion": "1"}]
    (tmp_path / "deadline_rules_synthetic.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    with raises_code(code):
        calculate(client, rule["ruleId"], configs=tmp_path)


def test_RT18_victim_protest_is_five_days_and_separate_from_defendant_appeal(client):
    # 刑诉法229：被害人及其法定代理人不服一审判决，自收到判决书后五日以内请求抗诉；
    # 与230条被告人上诉判决十日分开。收到日2026-03-02，起算日不计入→原始2026-03-07（周六）；
    # 被害人非在押，105条第2款节假日顺延→2026-03-09（周一）。
    protest = calculate(client, "criminal.appeal.victim_protest", served="2026-03-02",
                        context={"instrumentIsJudgment": True})
    assert protest["dueDate"] == "2026-03-09"
    assert "roll_forward:2026-03-07->2026-03-09" in protest["calculationSteps"]
    assert "legal_result:candidate_requires_lawyer_review" in protest["calculationSteps"]
    appeal = calculate(client, "criminal.appeal.judgment", served="2026-03-02")
    assert appeal["dueDate"] == "2026-03-12"
    # 缺"判决书"前提或对象是裁定：229只允许对判决请求抗诉，具名拒绝而非默认适用。
    with raises_code("deadline_legal_premise_unverified"):
        calculate(client, "criminal.appeal.victim_protest", served="2026-03-02")
    with raises_code("deadline_legal_premise_unverified"):
        calculate(client, "criminal.appeal.victim_protest", served="2026-03-02",
                  context={"instrumentIsJudgment": False})


def test_RT19_registry_counts_are_recorded_not_padded(client):
    document = yaml.safe_load((ROOT / "configs/deadline_rules_cn.v1.yaml").read_text(encoding="utf-8"))
    top_level = [item["ruleId"] for item in document["rules"]]
    assert len(top_level) == 27  # 版本记录数（含行政复议/行政诉讼两族）
    assert len(set(top_level)) == 26  # 不同规则ID数（arbitration.set_aside.award 两个合法历史版本）
    assert "criminal.appeal.victim_protest" in set(top_level)


@pytest.mark.parametrize("rule_id,expected", [
    ("administrative.reconsideration.application", "2026-04-30"),  # 复议法20条：知道之日起60日
    ("administrative.litigation.filing", "2026-09-01"),  # 行诉法46条：知道之日起6个月
])
def test_RT20_administrative_families_execute_through_real_entry(client, rule_id, expected):
    result = calculate(client, rule_id, aware="2026-03-01")
    assert result["dueDate"] == expected
    assert "legal_result:candidate_requires_lawyer_review" in result["calculationSteps"]


def test_RT21_administrative_rules_fail_closed_without_reviewed_premise(client):
    for rule_id in ("administrative.reconsideration.application", "administrative.litigation.filing"):
        with raises_code("deadline_legal_premise_unverified"):
            calculate(client, rule_id, aware="2026-03-01", context={"subjectQualified": False})
