from tools.fast_path_interceptor import FastPathInterceptor
from addons.us import us_lookup


def test_builtin_alter_ego_signature_triggers_fast_path():
    hit = FastPathInterceptor().intercept(["Alter-Ego"])

    assert hit is not None
    assert hit["signature_id"] == "THREAT_NJ_PEN_001_AlterEgo"
    assert hit["method"] == "FAST_PATH_BYPASS"


def test_invalid_usc_title_triggers_intercept(monkeypatch):
    monkeypatch.setattr(
        us_lookup,
        "_BLUEPRINT",
        {
            "domain_assets": {
                "united_states_code": {
                    "titles": [{"title": "28", "name": "Judiciary and Judicial Procedure"}]
                }
            }
        },
    )
    hit = FastPathInterceptor().intercept(["999 U.S.C. § 1"])

    assert hit is not None
    assert hit["signature_id"] == "USC_INVALID_TITLE"
    assert hit["method"] == "USC_VALIDATION"
