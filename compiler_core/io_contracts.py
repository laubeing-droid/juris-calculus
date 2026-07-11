"""Cross-module declarations for the neutral reasoning boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ModuleIOContract:
    """Declare fact keys a module may consume and output keys it may produce."""

    module_id: str
    consumed_keys: frozenset[str] = field(default_factory=frozenset)
    produced_keys: frozenset[str] = field(default_factory=frozenset)
    allowed_output_kinds: frozenset[str] = field(default_factory=lambda: frozenset({"machine_packet"}))

    def validate_read(self, fact_key: str) -> None:
        """Reject reads that were not declared by this module."""

        if fact_key not in self.consumed_keys:
            raise ValueError(f"{self.module_id} cannot read undeclared fact key: {fact_key}")

    def validate_output(self, output_key: str, output_kind: str = "machine_packet") -> None:
        """Reject outputs outside the declared ownership and kind contract."""

        if output_key not in self.produced_keys:
            raise ValueError(f"{self.module_id} cannot produce undeclared output key: {output_key}")
        if output_kind not in self.allowed_output_kinds:
            raise ValueError(f"{self.module_id} cannot produce output kind: {output_kind}")


@dataclass
class IORegistry:
    """Track output ownership across a multi-step orchestration."""

    owners: dict[str, str] = field(default_factory=dict)

    def claim_outputs(self, contract: ModuleIOContract) -> None:
        """Claim produced keys and fail on ownership collisions."""

        for key in contract.produced_keys:
            existing = self.owners.get(key)
            if existing and existing != contract.module_id:
                raise ValueError(f"output key collision: {key} owned by {existing}")
            self.owners[key] = contract.module_id


def validate_mcp_machine_status(payload: Mapping[str, Any]) -> bool:
    """Return True when MCP/API payload preserves machine-readable boundary status."""

    if "result_status" in payload:
        return True
    if "reasoning_boundary" in payload and isinstance(payload["reasoning_boundary"], Mapping):
        return "result_status" in payload["reasoning_boundary"]
    return False

