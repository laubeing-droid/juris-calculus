from tools.test_quality_auditor import audit_test_quality
from tools.recovery_guard import verify_recovery_safeguards

def test_test_quality_no_errors():
    report = audit_test_quality()
    assert report["status"] == "PASS"
    assert report["files_checked"] >= 10

def test_recovery_safeguards_pass():
    report = verify_recovery_safeguards()
    assert report["status"] == "PASS"
    assert report["results"]["max_iterations"] > 0
