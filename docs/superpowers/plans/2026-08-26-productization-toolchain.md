# Productization Toolchain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the complete spec-driven system with safe host installation, versioned state/config migrations, capability diagnostics, release verification, and reversible upgrades.

**Architecture:** Productization wraps the existing core and adapters without moving workflow policy into installers. A host manifest describes files and settings to install; an install planner produces a preview and applies only approved paths with backups. Versioned pure migration functions update machine-owned config/state copies before atomic replacement. `doctor` and `self-test` report capabilities and degraded guarantees using stable JSON schemas.

**Tech Stack:** Python 3.11+, `importlib.metadata`, `tomlkit>=0.13,<0.14`, `json`, `shutil`, existing atomic persistence, `pytest`, `hatchling`, GitHub Actions YAML.

## Global Constraints

- Requires completion of the core, Claude Code adapter, Codex adapter, and structured document adapter plans.
- Installation and upgrade never rewrite user spec/plan files.
- Existing host settings are merged, backed up, and restored on rollback; unknown settings remain untouched.
- Migrations are sequential, deterministic, idempotent, and operate only on machine-owned config/state.
- All install and migration targets are constrained to declared user/project roots; path traversal is rejected.
- `doctor` distinguishes available, degraded, and unavailable capabilities and never reports a guarantee that an adapter cannot provide.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
src/spec_driven/
  capabilities.py        # from core baseline Task 2; consumed, not modified
  diagnostics.py         # created here
  install.py             # from core baseline Task 7; hardened in Task 2
  migrate.py             # created here
  release.py             # created here
install/manifests/       # committed by the adapter plans; verified in Task 1
  claude-code.json
  codex.json
migrations/
  README.md
tests/unit/test_capabilities.py          # extended in Task 1
tests/unit/test_install.py               # extended in Task 2
tests/unit/test_migrate.py
tests/integration/test_doctor.py
tests/integration/test_install_round_trip.py   # extended in Task 2
tests/e2e/test_self_test.py
.github/workflows/ci.yml
README.md
CHANGELOG.md
```

`capabilities.py` owns the cross-host capability vocabulary. `install.py` plans, previews, applies, and rolls back filesystem/settings changes. `migrate.py` owns pure version transitions. `diagnostics.py` renders reports and runs fixture self-tests. `release.py` validates package contents and compatibility metadata.

---

### Task 1: Verify the cross-host capability and compatibility model

The capability vocabulary ships in core baseline Task 2 (`src/spec_driven/capabilities.py`): `CapabilityStatus` (`available`/`degraded`/`unavailable`), `Capability`, `CapabilityReport`, and `HostManifest(schema_version, host, adapter_module, skill_source, skill_target, settings_target, settings_fragment)` with `load_host_manifest(path)` rejecting missing or empty mechanisms. This task does **not** redefine any of that code; it proves the real per-host manifests that the adapter plans commit load, declare importable adapters, and expose concrete registrations.

**Files:**
- Consumes: `src/spec_driven/capabilities.py` (core baseline Task 2).
- Verify committed by adapter plans: `install/manifests/claude-code.json`, `install/manifests/codex.json`.
- Modify: `tests/unit/test_capabilities.py` (append cross-host verification; keep core's tests intact).

- [ ] **Step 1: Confirm the core capability module and its tests already pass**

Run core baseline Task 2's capability tests unchanged:

```bash
python -m pytest tests/unit/test_capabilities.py -q
```

Expected: green. If `Capability`, `CapabilityReport`, `HostManifest`, or `load_host_manifest` is missing, stop and complete core baseline Task 2 first; nothing in this plan adds them.

- [ ] **Step 2: Write the cross-host manifest verification test**

Append to `tests/unit/test_capabilities.py`:

```python
import importlib
from pathlib import Path

import pytest

from spec_driven.capabilities import CapabilityReport, load_host_manifest

ROOT = Path(__file__).resolve().parents[2]
HOSTS = {"claude-code", "codex"}


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_real_manifest_declares_importable_adapter_and_concrete_registration(host: str) -> None:
    manifest = load_host_manifest(ROOT / "install" / "manifests" / f"{host}.json")
    assert manifest.host == host
    importlib.import_module(manifest.adapter_module)
    assert manifest.settings_fragment
    assert manifest.skill_source
    assert manifest.settings_target


def test_capability_report_builds_per_host() -> None:
    for host in sorted(HOSTS):
        manifest = load_host_manifest(ROOT / "install" / "manifests" / f"{host}.json")
        report = CapabilityReport(1, manifest.host, "0.1.0", ())
        assert report.to_dict()["host"] == manifest.host
```

This requires the Claude Code and Codex adapter plans to have committed their real, contract-tested manifest files before this task runs. Do not replace those files with examples here.

- [ ] **Step 3: Run the tests**

```bash
python -m pytest tests/unit/test_capabilities.py -q
```

- [ ] **Step 4: Commit the cross-host verification**

```bash
git add tests/unit/test_capabilities.py
git commit -m "test: verify per-host capability manifests"
```

---

### Task 2: Verify and harden the installation surface

The installation primitives ship in core baseline Task 7 (`src/spec_driven/install.py`): `InstallOperation`, `InstallPlan`, `InstallReceipt`, `plan_install`, `apply_install`, `rollback_install`, plus the CLI `install --host --scope --dry-run` and `uninstall --receipt`. This task does **not** rebuild them. It closes the one blind spot — `uninstall` currently trusts the receipt file without verifying its paths (spec §12: reject path escape) — and proves the real adapter manifests install, merge, persist project-scope receipts, and roll back byte-equivalently.

**Files:**
- Consumes: `src/spec_driven/install.py`, `src/spec_driven/cli.py` (core baseline Task 7); `install/manifests/claude-code.json`, `install/manifests/codex.json` and their skill sources (adapter plans).
- Modify: `src/spec_driven/install.py` (add `verify_receipt`).
- Modify: `src/spec_driven/cli.py` (`uninstall` gains `--root` and verifies the receipt before rolling back).
- Modify: `tests/unit/test_install.py` (append receipt-verification tests).
- Modify: `tests/integration/test_install_round_trip.py` (append cross-host real-manifest E2E; core Task 7 already placed a unit-level round-trip there).

**Interfaces:**
- Consumed from core baseline Task 7: `InstallPlan`, `InstallReceipt`, `plan_install`, `apply_install`, `rollback_install`, CLI `install`/`uninstall`.
- Added: `verify_receipt(receipt: InstallReceipt, root: Path) -> None` re-resolves every target and backup path against `root` and raises `ValueError` (`path escapes target root`) for any escape.
- CLI: `uninstall --receipt PATH --root ROOT` (default ROOT = current working directory) validates the receipt before `rollback_install`.

- [ ] **Step 1: Write failing receipt-hardening tests**

Append to `tests/unit/test_install.py`:

```python
from spec_driven.install import InstallReceipt, verify_receipt


def test_receipt_with_escaping_target_is_rejected(tmp_path: Path) -> None:
    receipt = InstallReceipt("bad", (("../outside.json", None),), ())
    with pytest.raises(ValueError, match="escapes target root"):
        verify_receipt(receipt, tmp_path / "root")


def test_receipt_with_escaping_backup_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "settings.json").write_text("{}", encoding="utf-8")
    receipt = InstallReceipt("bad", (("settings.json", str(tmp_path / "backups" / "0-settings.json")),), ())
    with pytest.raises(ValueError, match="escapes target root"):
        verify_receipt(receipt, tmp_path / "root")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/test_install.py -q
```

Expected: import error for `verify_receipt`.

- [ ] **Step 3: Implement receipt verification**

Add to `src/spec_driven/install.py`:

```python
def verify_receipt(receipt: InstallReceipt, root: Path) -> None:
    """Reject any receipt path that would escape the declared target root."""
    resolved_root = root.resolve()
    for target_text, backup_text in receipt.backups:
        for candidate in (target_text, backup_text):
            if candidate is None:
                continue
            resolved = (resolved_root / candidate).resolve()
            if resolved != resolved_root and resolved_root not in resolved.parents:
                raise ValueError(f"path escapes target root: {candidate}")
```

- [ ] **Step 4: Wire receipt verification into uninstall**

Extend the `uninstall` handler from core Task 7 with a `--root` argument (default `Path.cwd()`), read the receipt, verify it, then roll back:

```python
def _uninstall(args: argparse.Namespace) -> int:
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    parsed = InstallReceipt(**receipt)
    verify_receipt(parsed, args.root)
    rollback_install(parsed)
    return 0
```

- [ ] **Step 5: Write the cross-host real-manifest round-trip test**

Append to `tests/integration/test_install_round_trip.py`. This requires the adapter plans to have committed `install/manifests/claude-code.json`, `install/manifests/codex.json`, and each manifest's `skill_source` directory (Claude Code: `skills/spec-driven-development/` from core Task 8; Codex: `adapters/codex/`) before this task runs.

```python
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spec_driven.capabilities import load_host_manifest
from spec_driven.cli import _install, _uninstall
from spec_driven.install import apply_install, plan_install, rollback_install, verify_receipt

ROOT = Path(__file__).resolve().parents[2]
HOSTS = {"claude-code", "codex"}


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_real_manifest_merges_and_rolls_back_byte_equivalent(tmp_path: Path, host: str) -> None:
    manifest = load_host_manifest(ROOT / "install" / "manifests" / f"{host}.json")
    target = tmp_path / "home"
    settings = target / manifest.settings_target
    settings.parent.mkdir(parents=True)
    seed = '{"theme": "dark"}' if settings.suffix == ".json" else 'model = "keep"\n'
    settings.write_text(seed, encoding="utf-8")
    receipt = apply_install(plan_install(manifest, ROOT, target), target / ".spec-driven-install-backups")
    merged = settings.read_text(encoding="utf-8")
    assert "theme" in merged or "keep" in merged  # unknown key survived
    verify_receipt(receipt, target)
    rollback_install(receipt)
    assert settings.read_text(encoding="utf-8") == seed


def test_real_manifests_expose_concrete_registrations() -> None:
    claude = load_host_manifest(ROOT / "install" / "manifests" / "claude-code.json")
    assert "SessionStart" in claude.settings_fragment["hooks"]
    codex = load_host_manifest(ROOT / "install" / "manifests" / "codex.json")
    assert codex.settings_fragment == {"notify": {"background": True}}


def test_cli_project_install_and_uninstall_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _install(SimpleNamespace(host="claude-code", scope="project", dry_run=False)) == 0
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.is_file()
    assert "spec-driven-claude" in settings.read_text(encoding="utf-8")
    receipt_path = tmp_path / ".spec-driven" / "install-receipts" / "claude-code.json"
    assert receipt_path.is_file()
    assert _uninstall(SimpleNamespace(receipt=str(receipt_path), root=tmp_path)) == 0
    assert not settings.exists()
```

- [ ] **Step 6: Run the hardened install suite and commit**

Run:

```bash
python -m pytest tests/unit/test_install.py tests/integration/test_install_round_trip.py -q
python -m pytest -q
```

Expected: escaping receipt paths are rejected, unknown settings survive real-manifest installs, rollback restores byte-equivalent originals, and the project-scope CLI round trip persists and consumes the receipt under `.spec-driven/install-receipts/`.

```bash
git add src/spec_driven/install.py src/spec_driven/cli.py tests/unit/test_install.py tests/integration/test_install_round_trip.py
git commit -m "feat: verify install receipts and prove real-manifest round trips"
```

---

### Task 3: Add deterministic config and state migrations

**Files:**
- Create: `src/spec_driven/migrate.py`
- Create: `tests/unit/test_migrate.py`
- Create: `migrations/README.md`
- Modify: `src/spec_driven/cli.py`

**Interfaces:**
- `Migration(kind: Literal["config", "state"], from_version: int, to_version: int, transform: Callable[[dict[str, object]], dict[str, object]])`.
- `MigrationRegistry.register(migration: Migration) -> None`.
- `MigrationRegistry.migrate(kind: str, document: dict[str, object], target_version: int) -> dict[str, object]`.
- `migrate_file(path: Path, kind: str, target_version: int, backup_dir: Path, registry: MigrationRegistry) -> None`.
- CLI `migrate --project PATH --target-version N --dry-run`.

- [ ] **Step 1: Write failing sequential and rollback tests**

```python
from pathlib import Path

import pytest

from spec_driven.migrate import Migration, MigrationRegistry, migrate_file


def test_registry_applies_each_version_once() -> None:
    registry = MigrationRegistry()
    registry.register(Migration("state", 1, 2, lambda value: {**value, "schema_version": 2, "v2": True}))
    registry.register(Migration("state", 2, 3, lambda value: {**value, "schema_version": 3, "v3": True}))
    migrated = registry.migrate("state", {"schema_version": 1}, 3)
    assert migrated == {"schema_version": 3, "v2": True, "v3": True}
    assert registry.migrate("state", migrated, 3) == migrated


def test_missing_migration_path_is_rejected() -> None:
    registry = MigrationRegistry()
    with pytest.raises(ValueError, match="no migration"):
        registry.migrate("state", {"schema_version": 1}, 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_migrate.py -q
```

Expected: import error for `migrate`.

- [ ] **Step 3: Implement the pure migration registry**

`src/spec_driven/migrate.py`:

```python
from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Migration:
    kind: Literal["config", "state"]
    from_version: int
    to_version: int
    transform: Callable[[dict[str, object]], dict[str, object]]


class MigrationRegistry:
    def __init__(self) -> None:
        self._migrations: dict[tuple[str, int], Migration] = {}

    def register(self, migration: Migration) -> None:
        if migration.to_version != migration.from_version + 1:
            raise ValueError("migrations must advance exactly one version")
        key = (migration.kind, migration.from_version)
        if key in self._migrations:
            raise ValueError(f"duplicate migration: {key}")
        self._migrations[key] = migration

    def migrate(self, kind: str, document: dict[str, object], target_version: int) -> dict[str, object]:
        current = int(document.get("schema_version", 0))
        result = dict(document)
        while current < target_version:
            migration = self._migrations.get((kind, current))
            if migration is None:
                raise ValueError(f"no migration for {kind} schema {current}")
            result = migration.transform(dict(result))
            current = int(result.get("schema_version", 0))
            if current != migration.to_version:
                raise ValueError("migration returned the wrong schema version")
        if current != target_version:
            raise ValueError("downgrade migrations are not supported")
        return result
```

- [ ] **Step 4: Implement backed-up atomic file migration**

Continue `migrate.py`:

```python
def migrate_file(
    path: Path,
    kind: str,
    target_version: int,
    backup_dir: Path,
    registry: MigrationRegistry,
) -> None:
    original = json.loads(path.read_text(encoding="utf-8"))
    migrated = registry.migrate(kind, original, target_version)
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)
    temporary = path.with_suffix(path.suffix + ".migrating")
    temporary.write_text(json.dumps(migrated, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
```

- [ ] **Step 5: Document migration authoring rules**

`migrations/README.md`:

```markdown
# Machine-state migrations

Migrations apply only to `spec-driven.config.*` and `.spec-driven/state.json`.
They advance exactly one schema version, are pure functions, preserve unknown keys,
and must have tests for source input, target output, repeat invocation, invalid input,
and interrupted file replacement. Migrations never read or write spec/plan documents.
```

- [ ] **Step 6: Run migration tests and commit**

Run:

```bash
python -m pytest tests/unit/test_migrate.py -q
python -m pytest -q
```

Expected: sequential, idempotent, missing-path, and backup tests pass.

```bash
git add src/spec_driven/migrate.py src/spec_driven/cli.py tests/unit/test_migrate.py migrations/README.md
git commit -m "feat: add versioned machine-state migrations"
```

---

### Task 4: Implement `doctor` and offline `self-test`

**Files:**
- Create: `src/spec_driven/diagnostics.py`
- Create: `tests/integration/test_doctor.py`
- Create: `tests/e2e/test_self_test.py`
- Modify: `src/spec_driven/cli.py`

**Interfaces:**
- `DoctorCheck(name: str, status: Literal["pass", "warn", "fail"], message: str, remediation: str | None)`.
- `run_doctor(project_root: Path, host: str) -> tuple[DoctorCheck, ...]`.
- `run_self_test(work_root: Path) -> dict[str, object]` copies fixtures to a temporary local directory and runs start → evidence → checkpoint → confirmation → document verification without a network call.
- CLI `doctor --json` exits `0` for pass/warn and `1` for any fail; `self-test --json` exits `0` only for a complete workflow.

- [ ] **Step 1: Write failing diagnostic tests**

```python
from pathlib import Path

from spec_driven.diagnostics import run_doctor


def test_doctor_reports_ambiguous_documents_as_failure(tmp_path: Path) -> None:
    (tmp_path / "one-spec.md").write_text("# One", encoding="utf-8")
    (tmp_path / "two-spec.md").write_text("# Two", encoding="utf-8")
    checks = run_doctor(tmp_path, "generic")
    discovery = next(check for check in checks if check.name == "document_discovery")
    assert discovery.status == "fail"
    assert discovery.remediation == "set spec.paths and plan.paths in spec-driven.config.yaml"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/integration/test_doctor.py tests/e2e/test_self_test.py -q
```

Expected: import error for `diagnostics`.

- [ ] **Step 3: Implement explicit, non-throwing diagnostic checks**

`src/spec_driven/diagnostics.py`:

```python
from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .config import load_config
from .discovery import discover_documents, infer_test_commands
from .documents import builtin_registry
from .errors import SpecDrivenError


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    remediation: str | None


def run_doctor(project_root: Path, host: str) -> tuple[DoctorCheck, ...]:
    checks: list[DoctorCheck] = []
    try:
        config = load_config(project_root)
        checks.append(DoctorCheck("configuration", "pass", "schema version 1 loaded", None))
        discover_documents(project_root, config, builtin_registry())
        checks.append(DoctorCheck("document_discovery", "pass", "one spec and one plan selected", None))
    except SpecDrivenError as error:
        checks.append(DoctorCheck(
            "document_discovery",
            "fail",
            f"{error.code}: {error}",
            "set spec.paths and plan.paths in spec-driven.config.yaml",
        ))
        return tuple(checks)
    try:
        infer_test_commands(project_root, config)
        checks.append(DoctorCheck("test_commands", "pass", "unit and regression commands configured", None))
    except SpecDrivenError as error:
        checks.append(DoctorCheck("test_commands", "fail", str(error), "configure tests.unit.command and tests.regression.command"))
    checks.append(DoctorCheck("host_adapter", "pass" if host in {"generic", "claude-code", "codex"} else "warn", host, None))
    return tuple(checks)
```

- [ ] **Step 4: Implement self-test as a fixture workflow**

`run_self_test` must copy `fixtures/markdown-project` into `work_root / "self-test"`, run the same public `CoreEngine` operations used by adapters, inspect both updated documents, verify `documents_updated` exists, and return:

```python
{
    "schema_version": 1,
    "status": "pass",
    "checks": {
        "gate": True,
        "spec_updated": True,
        "plan_updated": True,
        "audit_event": True,
        "next_module": "M2",
    },
}
```

It must catch `SpecDrivenError` and return `status: "fail"` with the stable error code instead of a traceback.

- [ ] **Step 5: Wire JSON and human-readable CLI output**

Extend `cli.py` so both commands serialize dataclasses via `asdict` for `--json`; human mode prints one line per check. Set exit status exactly as specified in the Interfaces block.

- [ ] **Step 6: Run diagnostics and commit**

Run:

```bash
python -m pytest tests/integration/test_doctor.py tests/e2e/test_self_test.py -q
python -m spec_driven.cli self-test --json
python -m pytest -q
```

Expected: JSON has `status: pass`, every check is true, and the full suite passes.

```bash
git add src/spec_driven/diagnostics.py src/spec_driven/cli.py tests/integration/test_doctor.py tests/e2e/test_self_test.py
git commit -m "feat: add host diagnostics and offline self-test"
```

---

### Task 5: Add package validation, documentation, and CI release gates

**Files:**
- Create: `src/spec_driven/release.py`
- Create: `tests/unit/test_release.py`
- Create: `README.md`
- Create: `CHANGELOG.md`
- Create: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`

**Interfaces:**
- `validate_release(root: Path) -> tuple[str, ...]` returns error strings; an empty tuple is releasable.
- Validation requires non-empty host manifests, all skill files, migration documentation, fixture self-test, and an adapter compatibility report for each supported host.
- CI supports Python 3.11, 3.12, and 3.13.

- [ ] **Step 1: Write failing release-validation tests**

```python
from pathlib import Path

from spec_driven.release import validate_release


def test_repository_has_no_release_validation_errors() -> None:
    assert validate_release(Path.cwd()) == ()


def test_empty_host_settings_fragment_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "install" / "manifests"
    manifest.mkdir(parents=True)
    (manifest / "host.json").write_text(
        '{"schema_version":1,"host":"h","adapter_module":"m","skill_source":"s",'
        '"settings_target":"x","settings_fragment":{}}', encoding="utf-8"
    )
    assert "host manifest settings_fragment is empty: host.json" in validate_release(tmp_path)
```

- [ ] **Step 2: Run the release test to verify it fails**

Run:

```bash
python -m pytest tests/unit/test_release.py -q
```

Expected: import error for `release`.

- [ ] **Step 3: Implement release validation**

`src/spec_driven/release.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


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
    if not list(manifest_dir.glob("*.json")):
        errors.append("no host manifests found")
    return tuple(errors)
```

- [ ] **Step 4: Document exact installation and workflow commands**

`README.md` must include:

```markdown
# Spec-Driven Development

## Install

```bash
python -m pip install spec-driven-development
spec-driven install --host claude-code --scope user --dry-run
spec-driven install --host claude-code --scope user
spec-driven doctor --project /path/to/project --json
```

## Project configuration

Provide one complete `spec-driven.config.yaml`, Markdown marker example, YAML example,
and JSON example. Explain that both unit and regression commands are mandatory and
must be explicitly confirmed after inference.

## Module workflow

Document `start`, `status`, `checkpoint`, and `confirm-next`; state clearly that
natural-language confirmation does not authorize document changes.

## Recovery and uninstall

Document `recover`, `migrate --dry-run`, receipt paths, rollback, and `self-test`.
```

`CHANGELOG.md` starts with version `0.1.0` and lists the core, three adapters, installation, migration, diagnostics, and supported Python versions.

- [ ] **Step 5: Add build metadata and CI**

Add package data for skill and manifests to `pyproject.toml`. Add `.github/workflows/ci.yml` that checks out code, sets up each Python version, installs `.[test]`, runs `python -m pytest -q`, runs `python -m spec_driven.cli self-test --json`, builds the wheel, installs the wheel into a clean virtual environment, and runs `spec-driven --version`.

- [ ] **Step 6: Run final release verification**

Run:

```bash
python -m pytest -q
python -m spec_driven.cli self-test --json
python -m build
python -m pip install --force-reinstall dist/*.whl
spec-driven --version
```

Expected: all tests pass, self-test reports `pass`, wheel builds and installs, and the CLI prints `0.1.0`.

- [ ] **Step 7: Commit productization**

```bash
git add src/spec_driven/release.py tests/unit/test_release.py README.md CHANGELOG.md .github/workflows/ci.yml pyproject.toml
git commit -m "chore: add release and compatibility gates"
```

## Productization acceptance checklist

- [ ] User and project installs both produce a dry-run preview before mutation.
- [ ] Install preserves unknown host settings and rollback restores originals.
- [ ] No manifest contains an unverified or empty host mechanism.
- [ ] Config/state migrations are sequential, backed up, and idempotent.
- [ ] Spec/plan files are never migration targets.
- [ ] `doctor --json` accurately distinguishes pass, warning, and failure.
- [ ] `self-test` runs offline and proves the complete gated update path.
- [ ] Release CI passes on Python 3.11–3.13 and validates the built wheel.
