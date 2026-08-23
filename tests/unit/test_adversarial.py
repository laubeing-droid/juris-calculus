"""Fail-closed adversarial coverage after retirement of the CN candidate corpus."""

import pytest

from compiler_core.rule_packs import RulePackError, RulePackRegistry


def test_v4_adversarial_fail_closed(tmp_path) -> None:
    """A retired pack ID cannot fall through to another installed pack."""

    retired_pack_id = "cn-" + "legacy-corpus"
    with pytest.raises(RulePackError) as caught:
        RulePackRegistry(tmp_path).verify(retired_pack_id)
    assert caught.value.code == "PACK_NOT_INSTALLED"
