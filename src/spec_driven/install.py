from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

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
    return InstallPlan(manifest=manifest, project_root=project_root.resolve(), settings_target=(Path(project_root).resolve() / manifest.settings_target))


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


# --- Codex (TOML) installation primitives -------------------------------------
#
# The Codex host config (~/.codex/config.toml) is user-owned TOML. Unlike JSON
# settings we cannot round-trip comments through a parser, so the merge is
# text-append based: untouched bytes are preserved exactly and a managed block
# carries only the top-level scalar/array keys (today: `notify`).


@dataclass(frozen=True)
class TomlInstallReceipt:
    """Receipt for a merge_toml_fragment run; applied_keys == () means no-op."""

    backup_path: Path | None  # None: file did not exist before this merge
    target: Path
    applied_keys: tuple[str, ...]


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ValueError(f"unsupported fragment value type for TOML: {type(value)!r}")


def _managed_marker() -> str:
    return "# managed by spec-driven-development"


def merge_toml_fragment(config_path: Path, fragment: Mapping[str, object]) -> TomlInstallReceipt:
    import tomllib

    conflict = (
        "refusing to overwrite existing differing value; resolve manually or update "
        f"the key in {config_path} to match the spec-driven manifest"
    )
    current_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else None
    existing: dict[str, object] = {}
    if current_text is not None:
        try:
            with config_path.open("rb") as handle:
                existing = tomllib.load(handle)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"{config_path} is not valid TOML: {error}") from error

    changed: dict[str, object] = {}
    for key, value in fragment.items():
        if key in existing:
            if existing[key] != value:
                raise ValueError(f"conflict on `{key}`: {conflict}")
            continue  # identical -> idempotent no-op for this key
        changed[key] = value
    if not changed:
        return TomlInstallReceipt(backup_path=None, target=config_path, applied_keys=())

    backup: Path | None = None
    if current_text is not None:
        backup = config_path.with_name(config_path.name + ".spec-driven.bak")
        shutil.copy2(config_path, backup)
        updated = current_text.rstrip("\n") + "\n\n" + _managed_marker() + "\n"
    else:
        updated = _managed_marker() + "\n"
    updated += "".join(f"{key} = {_toml_value(value)}\n" for key, value in changed.items())
    temporary = config_path.with_name(config_path.name + ".spec-driven.tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, config_path)
    return TomlInstallReceipt(backup_path=backup, target=config_path, applied_keys=tuple(changed))


def rollback_toml(receipt: TomlInstallReceipt) -> None:
    if receipt.applied_keys == ():
        return  # merge was a no-op; nothing to restore
    if receipt.backup_path is not None:
        shutil.copy2(receipt.backup_path, receipt.target)
        return
    receipt.target.unlink(missing_ok=True)  # file was created by this merge


def copy_assets(source_dir: Path, codex_home: Path) -> None:
    """Mirror <source>/prompts into codex_home/prompts and <source>/skills into
    codex_home/skills atomically; identical files are left untouched."""
    for tree in ("prompts", "skills"):
        source_tree = source_dir / tree
        if not source_tree.is_dir():
            continue
        for source_file in sorted(p for p in source_tree.rglob("*") if p.is_file()):
            destination = codex_home / tree / source_file.relative_to(source_tree)
            if destination.is_file():
                if destination.read_bytes() == source_file.read_bytes():
                    continue
                destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".spec-driven.tmp")
            shutil.copy2(source_file, temporary)
            os.replace(temporary, destination)
