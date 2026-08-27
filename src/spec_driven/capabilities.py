from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

CapabilityStatus = Literal["available", "degraded", "unavailable"]


@dataclass(frozen=True)
class Capability:
    name: str
    status: CapabilityStatus
    mechanism: str
    guarantee: str
    remediation: str | None


@dataclass(frozen=True)
class CapabilityReport:
    schema_version: int
    host: str
    adapter_version: str
    capabilities: tuple[Capability, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "host": self.host,
            "adapter_version": self.adapter_version,
            "capabilities": [asdict(item) for item in self.capabilities],
        }
