from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from ..errors import ConfigError, StateConflictError
from ..models import DocumentUpdate, Module


def _managed(root: Mapping[str, object]) -> Mapping[str, object]:
    value = root.get("spec_driven")
    if not isinstance(value, Mapping):
        raise ConfigError("document requires a spec_driven mapping")
    return value


def parse_structured_modules(root: Mapping[str, object]) -> tuple[Module, ...]:
    raw_modules = _managed(root).get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ConfigError("spec_driven.modules must be a non-empty list")
    modules: list[Module] = []
    seen: set[str] = set()
    for raw in raw_modules:
        if not isinstance(raw, Mapping):
            raise ConfigError("each module must be a mapping")
        module_id = str(raw.get("id", ""))
        if not module_id:
            raise ConfigError("each module requires id")
        if module_id in seen:
            raise ConfigError(f"duplicate module id: {module_id}")
        seen.add(module_id)
        modules.append(
            Module(
                module_id=module_id,
                title=str(raw.get("title", "")),
                order=int(raw.get("order", 0)),
                goal=str(raw.get("goal", "")),
                prerequisites=tuple(str(item) for item in raw.get("prerequisites", [])),
                acceptance=tuple(str(item) for item in raw.get("acceptance", [])),
                test_requirements=tuple(str(item) for item in raw.get("tests", [])),
            )
        )
    ordered = tuple(sorted(modules, key=lambda module: module.order))
    if [module.order for module in ordered] != list(range(1, len(ordered) + 1)):
        raise ConfigError("module order must be contiguous starting at 1")
    return ordered


def apply_structured_update(
    root: MutableMapping[str, object], update: DocumentUpdate
) -> None:
    managed = root.get("spec_driven")
    if not isinstance(managed, MutableMapping):
        raise ConfigError("document requires a mutable spec_driven mapping")
    raw_modules = managed.get("modules")
    if not isinstance(raw_modules, list):
        raise ConfigError("spec_driven.modules must be a list")
    target: MutableMapping[str, Any] | None = None
    for raw in raw_modules:
        if isinstance(raw, MutableMapping) and raw.get("id") == update.module_id:
            target = raw
            break
    if target is None:
        raise StateConflictError(f"managed module not found: {update.module_id}")
    target["status"] = update.status
    target["completed_points"] = list(update.completed_points)
    target["notes"] = list(update.notes)
    target["evidence"] = list(update.evidence_summary)
    managed["active_module_id"] = update.next_module_id
