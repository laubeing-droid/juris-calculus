"""Cross-platform and cross-jurisdiction compatibility tests."""
from tools.platform_check import check_platform


def test_all_jurisdiction_configs_exist():
    report = check_platform(["cn", "hk", "us"])
    assert report["os"]["system"] in ("Windows", "Linux", "Darwin")
    assert "import:compiler_core" in report["results"]
    assert report["results"]["import:compiler_core"] == "OK"


def test_cn_jurisdiction_standalone():
    report = check_platform(["cn"])
    ok = True
    for key in report["results"]:
        if "config:cn" in key:
            ok = ok and report["results"][key] == "OK"
    assert ok, f"CN configs: {report['results']}"


def test_collision_interfaces_load():
    report = check_platform(["cn"])
    assert "collision_interfaces" in report["results"]
    assert "rules" in report["results"]["collision_interfaces"]
