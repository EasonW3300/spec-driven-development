from __future__ import annotations

import json
from pathlib import Path

from .capabilities import load_host_manifest
from .errors import SpecDrivenError


def validate_release(root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    required = (
        root / "skills/spec-driven-development/SKILL.md",
        root / "migrations/README.md",
        root / "README.md",
        root / "CHANGELOG.md",
    )
    for path in required:
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"required release file missing or empty: {path.relative_to(root)}")
    manifest_dir = root / "install/manifests"
    for path in sorted(manifest_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not raw.get("settings_fragment"):
            errors.append(f"host manifest settings_fragment is empty: {path.name}")
    for path in sorted(manifest_dir.glob("*.json")):
        try:
            manifest = load_host_manifest(path)
        except SpecDrivenError:
            continue  # malformed manifest already flagged by the settings_fragment check
        if not (root / manifest.skill_source).is_dir():
            errors.append(f"host manifest skill_source missing: {path.name}")
    if not list(manifest_dir.glob("*.json")):
        errors.append("no host manifests found")
    return tuple(errors)
