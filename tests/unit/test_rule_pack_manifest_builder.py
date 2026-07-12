"""离线规则包 manifest 维护工具的只读一致性门禁。"""

from tools.build_rule_pack_manifests import CONFIGS, stale_manifests


BUILD_COMMIT = "2053843f397d2ee1c0797831f05f80ba89841e79"


def test_current_manifests_match_generator_without_writes() -> None:
    before = {
        path: path.read_bytes()
        for path in sorted((CONFIGS / "packs").rglob("manifest.yaml"))
    }

    assert stale_manifests(BUILD_COMMIT) == ()

    assert {path: path.read_bytes() for path in before} == before
