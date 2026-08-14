"""受控公共Python facade；低层application与loaded-pack API保持内部。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from compiler_core.audit_bundle import (
    AuditBundle,
    default_state_root,
    evaluate_registered_case,
    replay_audit_bundle,
    verify_audit_bundle,
)
from compiler_core.contracts import CaseRequest
from compiler_core.rendering import RenderOutput, render_run
from compiler_core.resources import configs_root
from compiler_core.rule_packs import PackVerification, RulePackRegistry


class JCClient:
    """只使用包内release registry并重新净化调用者请求。"""

    def __init__(self, *, state_root: Path | None = None) -> None:
        self._state_root = Path(state_root).resolve() if state_root is not None else None

    @staticmethod
    def validate_request(payload: Mapping[str, Any]) -> CaseRequest:
        return CaseRequest.from_dict(payload)

    @staticmethod
    def verify_pack(pack_id: str) -> PackVerification:
        return RulePackRegistry(configs_root()).verify(pack_id)

    def evaluate(self, request: CaseRequest | Mapping[str, Any]) -> AuditBundle:
        payload = request.to_dict() if isinstance(request, CaseRequest) else request
        safe_request = CaseRequest.from_dict(payload)
        return evaluate_registered_case(
            safe_request,
            RulePackRegistry(configs_root()),
            state_root=self._state_root,
        )

    def verify_run(self, run_id: str):
        return verify_audit_bundle(self._state_root or default_state_root(), run_id)

    def replay(self, run_id: str) -> dict[str, Any]:
        return replay_audit_bundle(self._state_root or default_state_root(), run_id)

    def render(
        self,
        run_id: str,
        *,
        output_format: str = "markdown",
        audience: str = "agent",
    ) -> RenderOutput:
        return render_run(
            run_id,
            state_root=self._state_root,
            output_format=output_format,
            audience=audience,
        )
