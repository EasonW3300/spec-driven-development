from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .errors import DiscoveryAmbiguousError
from .models import DocumentRef, ProjectConfig


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    resolved_root = root.resolve()
    if resolved_root not in path.parents or not path.is_file():
        raise DiscoveryAmbiguousError(f"document path is missing or outside project: {relative}")
    return path


def _configured(root: Path, paths: tuple[str, ...], kind: str) -> list[DocumentRef]:
    return [
        DocumentRef(kind, relative, _sha256(_safe_file(root, relative)))
        for relative in paths
    ]


def _scan(root: Path, kind: str, tokens: tuple[str, ...]) -> list[DocumentRef]:
    paths = sorted(
        path for path in root.rglob("*.md")
        if ".spec-driven" not in path.parts
        and any(token in path.name.lower() for token in tokens)
    )
    return [DocumentRef(kind, str(path.relative_to(root)), _sha256(path)) for path in paths]


def discover_documents(root: Path, config: ProjectConfig) -> tuple[DocumentRef, DocumentRef]:
    specs = _configured(root, config.spec_paths, "spec") if config.spec_paths else _scan(root, "spec", ("spec", "design"))
    plans = _configured(root, config.plan_paths, "plan") if config.plan_paths else _scan(root, "plan", ("plan", "roadmap"))
    if len(specs) != 1 or len(plans) != 1:
        raise DiscoveryAmbiguousError(
            f"expected one spec and one plan; found {len(specs)} spec(s), {len(plans)} plan(s)",
            remediation="set spec.paths and plan.paths in spec-driven.config.yaml",
        )
    return specs[0], plans[0]


def infer_test_commands(root: Path, config: ProjectConfig) -> tuple[str, str]:
    if config.unit_test_command and config.regression_test_command:
        return config.unit_test_command, config.regression_test_command
    candidates: list[tuple[str, str]] = []
    if (root / "pyproject.toml").is_file():
        candidates.append(("python -m pytest tests/unit -q", "python -m pytest -q"))
    if (root / "package.json").is_file():
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        if "test:unit" in scripts and "test" in scripts:
            candidates.append(("npm run test:unit", "npm test"))
    if len(candidates) != 1:
        raise DiscoveryAmbiguousError(
            "test command inference is ambiguous",
            remediation="configure tests.unit.command and tests.regression.command",
        )
    return candidates[0]
