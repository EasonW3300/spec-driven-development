from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .errors import ConfigError
from .models import ProjectConfig

_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "spec": {"paths": []},
    "plan": {"paths": []},
    "modules": {"source": "plan", "allow_inference": True},
    "tests": {"unit": {"command": None}, "regression": {"command": None}},
    "documents": {"adapters": ["markdown"]},
    "host": {"adapter": "generic", "confirmation_command": "confirm-next"},
    "runtime": {"state_dir": ".spec-driven"},
}


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _read(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    loaded = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"configuration root must be a mapping: {path}")
    return dict(loaded)


def load_config(
    project_root: Path,
    global_path: Path | None = None,
    session_override: Mapping[str, object] | None = None,
) -> ProjectConfig:
    raw = _merge(_DEFAULTS, _read(global_path))
    raw = _merge(raw, _read(project_root / "spec-driven.config.yaml"))
    raw = _merge(raw, session_override or {})
    if raw.get("schema_version") != 1:
        raise ConfigError("only config schema_version 1 is supported")
    return ProjectConfig(
        schema_version=1,
        spec_paths=tuple(str(item) for item in raw["spec"]["paths"]),
        plan_paths=tuple(str(item) for item in raw["plan"]["paths"]),
        unit_test_command=raw["tests"]["unit"]["command"],
        regression_test_command=raw["tests"]["regression"]["command"],
        document_adapters=tuple(str(item) for item in raw["documents"]["adapters"]),
        host_adapter=str(raw["host"]["adapter"]),
        confirmation_command=str(raw["host"]["confirmation_command"]),
        state_dir=str(raw["runtime"]["state_dir"]),
        allow_module_inference=bool(raw["modules"]["allow_inference"]),
    )
