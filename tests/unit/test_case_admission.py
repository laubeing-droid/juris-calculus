import pytest

from compiler_core.contracts import CaseRequest, ContractValidationError, SCHEMA_VERSION
from compiler_core.types import IRState
from compiler_core.version import __version__


DIGEST = "b" * 64


def _payload():
    """返回不含任何实体法律默认的最小显式案件上下文。"""

    return {
        "schema_version": SCHEMA_VERSION,
        "jurisdiction": "CN",
        "governing_law": "PRC Civil Code",
        "as_of_date": "2026-07-11",
        "facts": [{"id": "fact::contract-validity", "status": "unknown"}],
        "rule_pack_id": "cn-candidate",
        "rule_pack_version": __version__,
        "rule_pack_digest": DIGEST,
    }


def test_empty_ir_state_has_no_legal_or_temporal_assumptions():
    state = IRState()

    assert state.temporal_scope == {}
    assert state.state_tracker == {}
    assert state.world_id == ""


@pytest.mark.parametrize("field", ["jurisdiction", "governing_law", "as_of_date"])
def test_case_request_requires_explicit_legal_context(field):
    payload = _payload()
    payload.pop(field)

    with pytest.raises(ContractValidationError) as exc:
        CaseRequest.from_dict(payload)

    assert exc.value.code == "MISSING_REQUIRED_FIELD"


def test_contract_validity_is_an_explicit_unknown_fact_not_a_state_default():
    request = CaseRequest.from_dict(_payload())

    assert request.facts[0].id == "fact::contract-validity"
    assert request.facts[0].status.value == "unknown"
