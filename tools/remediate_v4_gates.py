#!/usr/bin/env python3
"""Generate WAITING_HUMAN / WAITING_EXTERNAL gate request envelopes.

施工方案 §1.1 / §22 / §3.6 require the runner to encode each external
dependency as a gate request envelope binding subject_digest,
required_roles, separation_of_duties, scope, expires_at, and
resume_command. This script enumerates every gate the施工方案 requires
before Z03 can complete and writes envelopes under
$JC_REMEDIATION_STATE_ROOT/requests/.

Per施工方案 §23 the agent must NOT auto-substitute these requests with
guesses; this script only DRAFTS the envelopes and saves recoverable
state. The runner must exit with code 20/21 and report the request paths
plus the unique resume_command.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


GATES: list[dict[str, Any]] = [
    {
        "gate_id": "B02-SPEC-INTAKE",
        "task_id": "B02",
        "kind": "EXTERNAL_GATE",
        "subject": "legal-math-modeling pinned commit + 5 differential fixtures",
        "required_roles": ["external_repo_maintainer"],
        "scope": "legal-math-modeling commit a3a015941f75091c87d57aa956e712f1546dd7d4 (or compatible successor) accessible at approved remote, license MIT, plus 5 differential fixtures with stable digests",
        "evidence_subject_paths": [
            "tests/fixtures/differential/spec_*.yaml",
            "tests/differential/spec_shadow_harness.py",
        ],
        "required_to_unblock": [
            "B02", "W0-01..05", "W1-06", "W2-06", "W3-05", "W4-07",
            "W5-01", "W5-06", "W6-05", "W7-04", "Z00", "Z03",
        ],
    },
    {
        "gate_id": "W0-05-VERIFIER-DEPENDENCY",
        "task_id": "W0-05",
        "kind": "HUMAN_GATE",
        "subject": "Approved Ed25519/RFC 8785 verifier dependency + test-only keys",
        "required_roles": ["engineering_reviewer", "release_approver"],
        "separation_of_duties": True,
        "scope": "Mature Ed25519 verifier (license MIT-compatible, Python 3.11/3.12 wheels for Windows+Linux, maintained), exact-pinned hash lock, test-only private keys fixtures with non-production scope marker",
        "evidence_subject_paths": [
            "requirements/core.lock",
            "requirements/dev.lock",
            "tests/fixtures/test_trust_root",
        ],
        "required_to_unblock": [
            "W0-05", "W1-05", "W1-06", "W2-03", "W2-04", "W2-06",
            "W4-04", "W4-07", "W5-CUTOVER", "W6-03", "W6-05",
            "W7-04", "W8-05", "W8-06", "H8-07",
        ],
    },
    {
        "gate_id": "H5-02-CN-LEGACY-AUTHORIZATION",
        "task_id": "H5-02",
        "kind": "HUMAN_GATE",
        "subject": "USER_AUTHORIZED_HISTORY_BOUND receipt for configs/zh_CN/rules.yaml removal",
        "required_roles": ["legal_reviewer", "engineering_reviewer", "release_approver"],
        "separation_of_duties": True,
        "scope": "Signed USER_AUTHORIZED_HISTORY_BOUND receipt binding施工方案 commit, two exact paths (configs/zh_CN/rules.yaml, configs/packs/cn-legacy-corpus/manifest.yaml), two Git blobs/SHA-256 (8f51fdfd..., 1b29b412...), rules bytes (13,620,766), rule count (21,144 unique rule IDs). No automation of the legacy corpus into cn-official. NO_RELEVANT_SEMANTICS_APPROVED must be具名 approved by signer, not runner.",
        "evidence_subject_paths": [
            "configs/zh_CN/rules.yaml",
            "configs/packs/cn-legacy-corpus/manifest.yaml",
        ],
        "required_to_unblock": [
            "H5-02", "W5-02C", "W5-03", "W5-CUTOVER", "W6-01",
            "W6-04", "W6-08", "Z00", "Z03",
        ],
    },
    {
        "gate_id": "H6-02-LOCK-APPROVAL",
        "task_id": "H6-02",
        "kind": "HUMAN_GATE",
        "subject": "Lockfile + new dependency approval for production/test/source-tool/release profiles",
        "required_roles": ["engineering_reviewer", "release_approver"],
        "separation_of_duties": True,
        "scope": "Approve exact hash-locked production/test/source-tool/release lock profiles. Jinja2/render and render.lock are whole-ecosystem removed; pydantic/python-docx/pdfplumber only enter source-tool profile; Hypothesis stays test-only.",
        "evidence_subject_paths": [
            "requirements/*.lock",
            "pyproject.toml",
        ],
        "required_to_unblock": [
            "H6-02", "W6-03", "W6-04", "W6-05", "W6-08", "Z00", "Z03",
        ],
    },
    {
        "gate_id": "H6-07-GITHUB-GOVERNANCE",
        "task_id": "H6-07",
        "kind": "MIXED",
        "subject": "GitHub branch/tag protection + CODEOWNERS + dual approver signer",
        "required_roles": ["github_admin", "release_approver"],
        "separation_of_duties": True,
        "scope": "Verified branch/tag protection, required checks, CODEOWNERS with two-person approval, release signer + dual approver, artifact retention policy. Provide evidence via API read or signed attestation.",
        "evidence_subject_paths": [
            ".github/workflows/ci.yml",
            ".github/workflows/auto-release.yml",
            "CODEOWNERS",
            "SECURITY.md",
        ],
        "required_to_unblock": [
            "H6-07", "W6-08", "W7-04", "H7-05",
        ],
    },
    {
        "gate_id": "H7-00-PRODUCTION-STORAGE-PROVIDER",
        "task_id": "H7-00",
        "kind": "MIXED",
        "subject": "Production state provider + Windows DACL/Junction + DSH service identity",
        "required_roles": ["operations_reviewer", "security_reviewer", "engineering_reviewer"],
        "separation_of_duties": True,
        "scope": "Approved Windows/NTFS + Linux/ext4 isolated environments with service identity, DACL/permissions, at-rest encryption, quota, retention, legal hold, backup/restore, capacity planning; signed attestation binding StorageCapability digest to readiness/run identity; DSH pinned commit + Node/pnpm lock + JC service identity distinct from DSH effective SID/UID; production transport authenticated.",
        "evidence_subject_paths": [
            "tests/storage_chaos/**",
            "tests/windows_security/**",
            "compiler_core/storage.py",
        ],
        "required_to_unblock": [
            "H7-00", "W7-01", "W7-02", "W7-03", "W7-04", "H7-05",
        ],
    },
    {
        "gate_id": "H7-05-KERNEL-RC-RELEASE",
        "task_id": "H7-05",
        "kind": "HUMAN_GATE",
        "subject": "Kernel RC remote promotion authorization",
        "required_roles": ["release_approver"],
        "separation_of_duties": True,
        "scope": "Exact commit/tree/wheel/evidence digests authorized for push/tag/release. Runner re-verifies signed artifact digest before proceeding.",
        "evidence_subject_paths": [
            "tools/build_provenance.py",
            "remediation/v4/evidence/kernel-rc-evidence.json",
        ],
        "required_to_unblock": ["H7-05"],
    },
    {
        "gate_id": "H8-00-FORMAL-SOURCE-INVENTORY",
        "task_id": "H8-00",
        "kind": "MIXED",
        "subject": "First-party FORMAL_SOURCE_INVENTORY with explicit legacy exclusion",
        "required_roles": ["source_custodian", "legal_reviewer", "engineering_reviewer", "release_approver"],
        "separation_of_duties": True,
        "scope": "Signed FORMAL_SOURCE_INVENTORY naming first-party sources for the first complete domain, with explicit exclusion of configs/zh_CN/rules.yaml path/digest/Git blob/pack ID/legacy rule-ID mappings; first-party license + redistribution policy; in-force / superseded / transitional version strategy; coverage and sampling standards. No auto-derivation from教材/OCR/类案/legacy manifest.",
        "evidence_subject_paths": [
            "configs/packs/cn-official/**",
            "remediation/v4/approvals/H8-00*",
        ],
        "required_to_unblock": [
            "H8-00", "W8-01", "W8-02", "H8-03", "H8-04", "W8-05",
            "W8-06", "H8-07",
        ],
    },
    {
        "gate_id": "H8-03-LEGAL-REVIEW",
        "task_id": "H8-03",
        "kind": "HUMAN_GATE",
        "subject": "Two-person legal review receipts for RuleV4 candidates",
        "required_roles": ["legal_reviewer_a", "legal_reviewer_b"],
        "separation_of_duties": True,
        "scope": "Per source/rule digest (or fixed Merkle root batch), each legal reviewer independently signs approve/reject/needs-change + interpretation choice + effect + scope + exceptions + reasons. Rejected items return to W8-02 as new digest; rule byte changes invalidate both old approvals.",
        "evidence_subject_paths": [
            "remediation/v4/approvals/H8-03*",
        ],
        "required_to_unblock": ["H8-03", "H8-04"],
    },
    {
        "gate_id": "H8-04-ENGINEERING-REVIEW",
        "task_id": "H8-04",
        "kind": "HUMAN_GATE",
        "subject": "Engineering review + role separation",
        "required_roles": ["engineering_reviewer"],
        "separation_of_duties": True,
        "scope": "Engineering reviewer signs receipt for type/executability/source binding/tests/coverage/loss/performance. Must be a different person from the two legal reviewers, source custodian, and release approver. Subject sets must match.",
        "evidence_subject_paths": [
            "remediation/v4/approvals/H8-04*",
        ],
        "required_to_unblock": ["H8-04", "W8-05"],
    },
    {
        "gate_id": "H8-07-CN-OFFICIAL-RELEASE",
        "task_id": "H8-07",
        "kind": "HUMAN_GATE",
        "subject": "cn-official release + 4.0.0 stable wheel promotion",
        "required_roles": ["pack_release_approver", "engine_release_approver"],
        "separation_of_duties": True,
        "scope": "Two distinct signers: pack release approver authorizes cn-official artifact; engine release approver authorizes 4.0.0 stable wheel rebuilt from a fresh commit (not the RC wheel relabeled). Both must reference the same engine/pack/trust/storage digests.",
        "evidence_subject_paths": [
            "remediation/v4/approvals/H8-07*",
        ],
        "required_to_unblock": [
            "H8-07", "H9-00", "W9-01", "W9-02", "W9-03", "W9-04",
            "W9-05", "W9-06", "Z00", "Z01", "Z02", "Z03",
        ],
    },
    {
        "gate_id": "H9-00-DSH-PIN",
        "task_id": "H9-00",
        "kind": "MIXED",
        "subject": "DSH pin + deployment topology + JC/DSH service identity separation",
        "required_roles": ["operations_reviewer", "security_reviewer", "release_approver"],
        "separation_of_duties": True,
        "scope": "Approved exact DSH commit/release, Node/pnpm lock, OS, out-of-tree bundle/profile location, JC MCP transport/process identity distinct from DSH effective SID/UID, allowed tools, update/rollback policy. JC formal production must be BLOCKED if JC and DSH share effective SID/UID/service principal or any path/volume/broker gives DSH write to JC state.",
        "evidence_subject_paths": [
            "tests/dsh_formal/**",
        ],
        "required_to_unblock": [
            "H9-00", "W9-01", "W9-02", "W9-03", "W9-04", "W9-05",
            "W9-06",
        ],
    },
]


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def _subject_digest(gate_id: str, subject: str, task_id: str) -> str:
    payload = json.dumps(
        {"gate_id": gate_id, "subject": subject, "task_id": task_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    state_root = os.environ.get("JC_REMEDIATION_STATE_ROOT")
    if not state_root:
        print("JC_REMEDIATION_STATE_ROOT not set", file=sys.stderr)
        return 2
    state_root = Path(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    requests_dir = state_root / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)

    source_tree_id = _git("rev-parse", "HEAD^{tree}").strip()
    plan_sha = hashlib.sha256(
        (ROOT / "20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md").read_bytes()
    ).hexdigest()
    audit_sha = hashlib.sha256(
        (ROOT / "20260819_juris-calculus_V4单主链生产投产全量代码审计.md").read_bytes()
    ).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    resume_command = (
        "py -3.12 -B tools/remediate_v4.py run "
        "--plan remediation/v4/tasks.json "
        f"--state-root \"{state_root}\" --through W9"
    )

    envelopes: list[dict[str, Any]] = []
    for gate in GATES:
        envelope: dict[str, Any] = {
            "schema_version": "jc/remediation-v4-gate-request/1.0",
            "gate_id": gate["gate_id"],
            "task_id": gate["task_id"],
            "kind": gate["kind"],
            "subject": gate["subject"],
            "subject_digest": _subject_digest(gate["gate_id"], gate["subject"], gate["task_id"]),
            "required_roles": gate["required_roles"],
            "separation_of_duties": gate.get("separation_of_duties", False),
            "scope": gate["scope"],
            "evidence_subject_paths": gate["evidence_subject_paths"],
            "required_to_unblock": gate["required_to_unblock"],
            "baseline_commit": _git("rev-parse", "HEAD").strip(),
            "baseline_tree": source_tree_id,
            "plan_sha256": plan_sha,
            "audit_sha256": audit_sha,
            "issued_at": now,
            "expires_at": expires,
            "resume_command": resume_command,
        }
        envelopes.append(envelope)

    envelopes.sort(key=lambda e: (e["task_id"], e["gate_id"]))
    for env in envelopes:
        path = requests_dir / f"{env['task_id']}_{env['gate_id']}.json"
        path.write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")

    # Index
    (requests_dir / "INDEX.json").write_text(
        json.dumps(
            {
                "schema_version": "jc/remediation-v4-gate-index/1.0",
                "baseline_commit": _git("rev-parse", "HEAD").strip(),
                "baseline_tree": source_tree_id,
                "plan_sha256": plan_sha,
                "audit_sha256": audit_sha,
                "issued_at": now,
                "count": len(envelopes),
                "gates": [
                    {
                        "task_id": e["task_id"],
                        "gate_id": e["gate_id"],
                        "kind": e["kind"],
                        "subject_digest": e["subject_digest"],
                        "expires_at": e["expires_at"],
                        "resume_command": e["resume_command"],
                    }
                    for e in envelopes
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"wrote {len(envelopes)} gate envelopes to {requests_dir}")
    print(f"unique resume_command: {resume_command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())