"""W9-JC 测试：独立准入（admit）、拒绝原因、result digest、CLI 子进程。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from compiler_core.admission import admit_rule, AdmissionOutcome

ROOT = Path(__file__).resolve().parents[1]

DIGEST = "a" * 64


def make_request(**overrides):
    req = {
        "request_id": "req-1",
        "snapshot_verification_receipt": {
            "receipt_id": "r1",
            "manifest_id": "snap-1",
            "manifest_digest": f"sha256-{DIGEST}",
            "result": "verified",
            "verified_at": "2026-08-11T00:00:00Z",
        },
        "fact_approval_ref": {
            "ref_id": "fact-ref-1",
            "fact_claim_id": "fact-1",
            "evidence_anchor_refs": ["anchor-1", "anchor-2"],
            "approved_at": "2026-08-11T00:00:00Z",
        },
        "locator": {
            "owner": "lccc",
            "snapshot": {"manifest_id": "snap-1", "digest": f"sha256-{DIGEST}"},
            "ref": {"kind": "relative_path", "value": "02_法律/01_民法典.md"},
            "digest": f"sha256-{DIGEST}",
            "page_map_status": "PAGE_MAP_UNVERIFIED",
        },
        "requested_at": "2026-08-11T00:00:00Z",
    }
    req.update(overrides)
    return req


class AdmissionTests(unittest.TestCase):
    def test_admit_verified_request(self):
        outcome = admit_rule(make_request())
        self.assertEqual(outcome.status, "admitted")
        self.assertEqual(outcome.produced_by, "jc")
        self.assertIsNone(outcome.rejection_reason)
        self.assertTrue(outcome.result_digest.startswith("sha256-"))

    def test_reject_snapshot_not_verified(self):
        outcome = admit_rule(make_request(snapshot_verification_receipt={
            "receipt_id": "r1", "manifest_id": "s", "manifest_digest": f"sha256-{DIGEST}",
            "result": "tampered", "verified_at": "2026-08-11T00:00:00Z",
        }))
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.rejection_reason, "snapshot_not_verified")

    def test_reject_fact_not_anchored(self):
        outcome = admit_rule(make_request(fact_approval_ref={
            "ref_id": "fact-ref-1", "fact_claim_id": "f", "evidence_anchor_refs": [], "approved_at": "x",
        }))
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.rejection_reason, "fact_not_evidence_anchored")

    def test_reject_locator_digest_missing(self):
        outcome = admit_rule(make_request(locator={
            "owner": "lccc", "snapshot": {"manifest_id": "s", "digest": f"sha256-{DIGEST}"},
            "ref": {"kind": "relative_path", "value": "x.md"},
        }))
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.rejection_reason, "locator_digest_missing")

    def test_reject_locator_digest_invalid(self):
        outcome = admit_rule(make_request(locator={
            "owner": "lccc", "snapshot": {"manifest_id": "s", "digest": f"sha256-{DIGEST}"},
            "ref": {"kind": "relative_path", "value": "x.md"}, "digest": "sha256-not-hex",
        }))
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.rejection_reason, "locator_digest_invalid")

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValueError) as ctx:
            admit_rule({})
        self.assertIn("admission_missing_field", str(ctx.exception))

    def test_result_digest_stable_and_unique(self):
        o1 = admit_rule(make_request())
        o2 = admit_rule(make_request())
        self.assertEqual(o1.result_digest, o2.result_digest, "同输入 digest 稳定")
        rejected = admit_rule(make_request(snapshot_verification_receipt={
            "receipt_id": "r1", "manifest_id": "s", "manifest_digest": f"sha256-{DIGEST}",
            "result": "tampered", "verified_at": "x",
        }))
        self.assertNotEqual(o1.result_digest, rejected.result_digest)

    def test_cli_admit_subprocess(self):
        import os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(make_request(), f)
            path = f.name
        code = (
            "import sys; sys.path.insert(0, r'{}'); "
            "from compiler_core.cli import main; raise SystemExit(main(['admit', '--input', r'{}', '--json']))"
        ).format(ROOT, path)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["command"], "admit")
            self.assertEqual(payload["cli_status"], "ok")
            self.assertEqual(payload["status"], "admitted")
            self.assertEqual(payload["produced_by"], "jc")
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
