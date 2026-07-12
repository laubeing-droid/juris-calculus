from tools.fast_path_interceptor import FastPathInterceptor


def test_builtin_alter_ego_signature_triggers_fast_path():
    hit = FastPathInterceptor().intercept(["Alter-Ego"])

    assert hit is not None
    assert hit["signature_id"] == "THREAT_NJ_PEN_001_AlterEgo"
    assert hit["method"] == "FAST_PATH_BYPASS"


def test_threat_report_lists_matching_builtin_signature():
    hits = FastPathInterceptor().get_threat_report(["Wis. Stat. 801.05"])

    assert len(hits) == 1
    assert hits[0]["signature_id"] == "THREAT_WI_ENF_001_LongArm"
