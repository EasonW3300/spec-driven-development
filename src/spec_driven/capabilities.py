from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .errors import ConfigError

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


@dataclass(frozen=True)
class HostManifest:
    schema_version: int
    host: str
    adapter_module: str
    skill_source: str
    skill_target: str
    settings_target: str
    settings_fragment: dict[str, object]


def load_host_manifest(path: Path) -> HostManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ConfigError(f"unsupported host manifest: {path}")
    missing = [name for name in ("host", "adapter_module", "skill_source", "skill_target", "settings_target") if not raw.get(name)]
    fragment = raw.get("settings_fragment")
    if missing or not isinstance(fragment, dict) or not fragment:
        raise ConfigError(f"host manifest is missing required fields: {path}", remediation=f"fix install/manifests/{path.name}")
    return HostManifest(
        schema_version=1,
        host=str(raw["host"]),
        adapter_module=str(raw["adapter_module"]),
        skill_source=str(raw["skill_source"]),
        skill_target=str(raw["skill_target"]),
        settings_target=str(raw["settings_target"]),
        settings_fragment=dict(fragment),
    )
