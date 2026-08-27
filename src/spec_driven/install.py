from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .capabilities import HostManifest


def _registration_identity(entry: dict[str, object]) -> object:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False)


def _dedupe(value: object) -> object:
    if isinstance(value, list):
        seen: list[object] = []
        result: list[object] = []
        for item in value:
            normalized = _dedupe(item)
            identity = _registration_identity(normalized) if isinstance(normalized, dict) else repr(normalized)
            if identity not in seen:
                seen.append(identity)
                result.append(normalized)
        return result
    if isinstance(value, dict):
        return {key: _dedupe(item) for key, item in value.items()}
    return value


def _merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)  # type: ignore[arg-type]
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _dedupe([*merged[key], *value])  # type: ignore[arg-type]
        else:
            merged[key] = deepcopy(value)
    return _dedupe(merged)


@dataclass(frozen=True)
class InstallPlan:
    manifest: HostManifest
    project_root: Path
    settings_target: Path


@dataclass(frozen=True)
class InstallReceipt:
    backup_dir: Path
    target: Path
    backup_file: Path | None

    @property
    def applied_keys(self) -> tuple[str, ...]:
        payload = json.loads(self.target.read_text(encoding="utf-8")) if self.target.is_file() else {}
        keys = tuple(payload.keys())
        return tuple(str(key) for key in keys)


def plan_install(manifest: HostManifest, project_root: Path, source_root: Path) -> InstallPlan:
    del source_root
    return InstallPlan(manifest=manifest, project_root=project_root.resolve(), settings_target=(Path(project_root).resolve() / manifest.settings_path))


def claude_code_settings_fragment(hook_command: str) -> dict[str, object]:
    def entry(matcher: str) -> dict[str, object]:
        registration = {"type": "command", "command": hook_command}
        return {"matcher": matcher, "hooks": [registration]} if matcher else {"matcher": "", "hooks": [registration]}

    return {
        "hooks": {
            "SessionStart": [entry("")],
            "PostToolUse": [entry("Bash")],
            "PostToolUseFailure": [entry("Bash")],
            "UserPromptSubmit": [entry("")],
        }
    }


def apply_install(plan: InstallPlan, backup_dir: Path) -> InstallReceipt:
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = plan.settings_target
    target.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, object] = {}
    backup_file: Path | None = None
    if target.is_file():
        current = json.loads(target.read_text(encoding="utf-8"))
        suffix = "".join(ch if ch.isalnum() else "-" for ch in str(target.relative_to(plan.project_root)))
        backup_file = backup_dir / f"{suffix}.bak"
        shutil.copy2(target, backup_file)
    merged = _merge(current, plan.manifest.settings_fragment)
    temporary = target.with_suffix(f"{target.suffix}.tmp-{backup_dir.name}")
    temporary.write_text(json.dumps(merged, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return InstallReceipt(backup_dir=backup_dir, target=target, backup_file=backup_file)


def rollback_install(receipt: InstallReceipt) -> None:
    if receipt.backup_file is None:
        receipt.target.unlink(missing_ok=True)
        return
    shutil.copy2(receipt.backup_file, receipt.target)
