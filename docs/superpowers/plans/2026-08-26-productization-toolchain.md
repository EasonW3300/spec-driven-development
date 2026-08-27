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
  capabilities.py
  diagnostics.py
  install.py
  migrate.py
  release.py
install/manifests/
  claude-code.json
  codex.json
migrations/
  README.md
tests/unit/test_capabilities.py
tests/unit/test_install.py
tests/unit/test_migrate.py
tests/integration/test_doctor.py
tests/integration/test_install_round_trip.py
tests/e2e/test_self_test.py
.github/workflows/ci.yml
README.md
CHANGELOG.md
```

`capabilities.py` owns the cross-host capability vocabulary. `install.py` plans, previews, applies, and rolls back filesystem/settings changes. `migrate.py` owns pure version transitions. `diagnostics.py` renders reports and runs fixture self-tests. `release.py` validates package contents and compatibility metadata.

---

### Task 1: Define versioned capability and compatibility reports

**Files:**
- Modify: `src/spec_driven/capabilities.py`
- Modify: `tests/unit/test_capabilities.py`
- Modify: `install/manifests/claude-code.json`
- Modify: `install/manifests/codex.json`

**Interfaces:**
- `CapabilityStatus` values: `available`, `degraded`, `unavailable`.
- `Capability(name: str, status: str, mechanism: str, guarantee: str, remediation: str | None)`.
- `CapabilityReport(schema_version: int, host: str, adapter_version: str, capabilities: tuple[Capability, ...])`.
- `HostManifest(schema_version: int, host: str, adapter_module: str, skill_source: str, settings_target: str, settings_fragment: dict[str, object])`.
- `load_host_manifest(path: Path) -> HostManifest` rejects missing or empty install mechanisms.

- [ ] **Step 1: Write failing report and manifest validation tests**

```python
from pathlib import Path

import pytest

from spec_driven.capabilities import Capability, CapabilityReport, load_host_manifest
from spec_driven.errors import ConfigError


def test_capability_report_has_stable_json_shape() -> None:
    report = CapabilityReport(1, "generic", "0.1.0", (Capability("confirmation", "available", "CLI", "exact command", None),))
    assert report.to_dict()["capabilities"][0]["status"] == "available"


def test_existing_host_manifest_has_a_real_install_mechanism() -> None:
    manifest = load_host_manifest(Path("install/manifests/claude-code.json"))
    assert manifest.schema_version == 1
    assert manifest.host == "claude-code"
    assert manifest.settings_fragment


def test_empty_settings_fragment_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "host.json"
    path.write_text(
        '{"schema_version":1,"host":"h","adapter_module":"m",'
        '"skill_source":"s","settings_target":"settings.json",'
        '"settings_fragment":{}}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="settings_fragment"):
        load_host_manifest(path)
```

- [ ] **Step 2: Run tests to verify the capability module or validation is incomplete**

```bash
python -m pytest tests/unit/test_capabilities.py -q
```

Expected: import error before `capabilities.py` exists, or a validation failure before the existing adapter manifests are complete.

- [ ] **Step 3: Extend the core capability model with validated host manifests**

Add `HostManifest` and `load_host_manifest` to `src/spec_driven/capabilities.py`. Parse JSON, require `schema_version == 1`, require non-empty `host`, `adapter_module`, `skill_source`, and `settings_target`, and require a non-empty `settings_fragment`. Preserve the existing `Capability` and `CapabilityReport` definitions from the core plan unchanged. Raise `ConfigError` with the manifest path and missing field name.

- [ ] **Step 4: Verify both adapter plans provide non-empty manifests**

The Claude Code and Codex adapter plans must commit their real, contract-tested manifest files before this task starts. Do not replace those files with examples here. Load both files in `tests/unit/test_capabilities.py` and assert their hosts are exactly `claude-code` and `codex`, their adapter modules are importable, and their settings fragments contain at least one concrete registration.

- [ ] **Step 5: Run tests and commit the compatibility model**

```bash
python -m pytest tests/unit/test_capabilities.py -q
python -m pytest -q
git add src/spec_driven/capabilities.py tests/unit/test_capabilities.py install/manifests
git commit -m "feat: validate host capability manifests"
```

---

### Task 2: Build previewable and reversible installation plans

**Files:**
- Create: `src/spec_driven/install.py`
- Create: `tests/unit/test_install.py`
- Create: `tests/integration/test_install_round_trip.py`
- Modify: `src/spec_driven/cli.py`

**Interfaces:**
- `InstallOperation(kind: Literal["copy", "merge_json", "merge_toml"], source: Path | None, target: Path, fragment: Mapping[str, object] | None)`.
- `InstallPlan(host: str, root: Path, operations: tuple[InstallOperation, ...])`.
- `plan_install(manifest: HostManifest, package_root: Path, target_root: Path) -> InstallPlan`.
- `apply_install(plan: InstallPlan, backup_root: Path) -> InstallReceipt`.
- `rollback_install(receipt: InstallReceipt) -> None`.
- CLI `install --host {claude-code,codex} --scope {user,project} --dry-run` and `uninstall --receipt PATH`.

- [ ] **Step 1: Write failing planner and rollback tests**

```python
import json
from pathlib import Path

from spec_driven.capabilities import HostManifest
from spec_driven.install import apply_install, plan_install, rollback_install


def test_install_merges_settings_without_losing_unknown_keys(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "skill").mkdir()
    (package / "skill" / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    target = tmp_path / "home"
    (target / ".claude").mkdir(parents=True)
    settings = target / ".claude" / "settings.json"
    settings.write_text(json.dumps({"theme": "dark", "hooks": {}}), encoding="utf-8")
    manifest = HostManifest(1, "claude-code", "module", "skill", ".claude/settings.json", {"hooks": {"SessionStart": []}})
    plan = plan_install(manifest, package, target)
    receipt = apply_install(plan, target / ".spec-driven-install-backups")
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert "SessionStart" in merged["hooks"]
    rollback_install(receipt)
    assert json.loads(settings.read_text(encoding="utf-8")) == {"theme": "dark", "hooks": {}}


def test_install_rejects_target_escape(tmp_path: Path) -> None:
    manifest = HostManifest(1, "bad", "module", "skill", "../outside.json", {})
    with pytest.raises(ValueError, match="escapes target root"):
        plan_install(manifest, tmp_path, tmp_path / "home")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_install.py tests/integration/test_install_round_trip.py -q
```

Expected: import error for `install`.

- [ ] **Step 3: Implement installation values and safe path resolution**

`src/spec_driven/install.py` begins with:

```python
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Mapping

import tomlkit

from .capabilities import HostManifest


@dataclass(frozen=True)
class InstallOperation:
    kind: Literal["copy", "merge_json", "merge_toml"]
    source: Path | None
    target: Path
    fragment: Mapping[str, object] | None


@dataclass(frozen=True)
class InstallPlan:
    host: str
    root: Path
    operations: tuple[InstallOperation, ...]


@dataclass(frozen=True)
class InstallReceipt:
    host: str
    backups: tuple[tuple[str, str | None], ...]
    created_paths: tuple[str, ...]


def _inside(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path escapes target root: {path}")
    return resolved


def plan_install(manifest: HostManifest, package_root: Path, target_root: Path) -> InstallPlan:
    settings = _inside(target_root, target_root / manifest.settings_target)
    skill_target = _inside(target_root, target_root / ".agents" / "skills" / "spec-driven-development")
    return InstallPlan(manifest.host, target_root.resolve(), (
        InstallOperation("copy", package_root / manifest.skill_source, skill_target, None),
        InstallOperation("merge_json" if settings.suffix == ".json" else "merge_toml", None, settings, manifest.settings_fragment),
    ))
```

- [ ] **Step 4: Implement deep merge, backup receipt, apply, and rollback**

Continue `install.py`:

```python
def _deep_merge(base: dict[str, object], fragment: Mapping[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in fragment.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _merge_toml(container: object, fragment: Mapping[str, object]) -> None:
    for key, value in fragment.items():
        if isinstance(value, Mapping):
            current = container.get(key)
            if current is None:
                current = tomlkit.table()
                container[key] = current
            _merge_toml(current, value)
        else:
            container[key] = value


def apply_install(plan: InstallPlan, backup_root: Path) -> InstallReceipt:
    backup_root.mkdir(parents=True, exist_ok=True)
    backups: list[tuple[str, str | None]] = []
    created: list[str] = []
    for index, operation in enumerate(plan.operations):
        _inside(plan.root, operation.target)
        backup = backup_root / f"{index}-{operation.target.name}"
        if operation.target.exists():
            if operation.target.is_dir():
                shutil.copytree(operation.target, backup)
            else:
                shutil.copy2(operation.target, backup)
            backups.append((str(operation.target), str(backup)))
        else:
            backups.append((str(operation.target), None))
            created.append(str(operation.target))
        operation.target.parent.mkdir(parents=True, exist_ok=True)
        if operation.kind == "copy":
            if operation.target.exists():
                shutil.rmtree(operation.target)
            shutil.copytree(operation.source, operation.target)
        elif operation.kind == "merge_json":
            current = json.loads(operation.target.read_text(encoding="utf-8")) if operation.target.exists() else {}
            merged = _deep_merge(current, operation.fragment or {})
            operation.target.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        elif operation.kind == "merge_toml":
            document = tomlkit.parse(operation.target.read_text(encoding="utf-8")) if operation.target.exists() else tomlkit.document()
            _merge_toml(document, operation.fragment or {})
            operation.target.write_text(tomlkit.dumps(document), encoding="utf-8")
        else:
            raise ValueError(f"unsupported install operation: {operation.kind}")
    return InstallReceipt(plan.host, tuple(backups), tuple(created))


def rollback_install(receipt: InstallReceipt) -> None:
    for target_text, backup_text in reversed(receipt.backups):
        target = Path(target_text)
        if target.exists():
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        if backup_text:
            backup = Path(backup_text)
            if backup.is_dir():
                shutil.copytree(backup, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
```

- [ ] **Step 5: Add CLI dry-run and receipt output**

Extend `cli.py` so `install --dry-run` serializes `InstallPlan` without applying it, while an actual install writes the receipt as JSON under the selected target root at `.spec-driven/install-receipts/<host>.json`. `uninstall` reads exactly that receipt and calls `rollback_install`.

- [ ] **Step 6: Run install tests and commit**

Run:

```bash
python -m pytest tests/unit/test_install.py tests/integration/test_install_round_trip.py -q
python -m pytest -q
```

Expected: unknown settings survive install, rollback restores byte-equivalent originals, and path escape is rejected.

```bash
git add src/spec_driven/install.py src/spec_driven/cli.py tests/unit/test_install.py tests/integration/test_install_round_trip.py
git commit -m "feat: add reversible host installation"
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
