# Spec-Driven Core Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, host-neutral core CLI that discovers Markdown spec/plan files, enforces the unit-plus-regression test gate, records versioned events, and performs recoverable idempotent updates through a generic explicit-command path.

**Architecture:** Immutable domain values and a deterministic state machine are isolated from filesystem code. An append-only event store and atomic snapshot repository persist machine state under `.spec-driven/`. A Markdown adapter owns managed document blocks, while a multi-file transaction coordinator hash-checks, backs up, stages, applies, and rolls back spec/plan patches. `CoreEngine` is the only orchestration boundary; the CLI and generic adapter only normalize inputs and call it.

**Tech Stack:** Python 3.11+, `argparse`, `dataclasses`, `json`, `hashlib`, `pathlib`, `tempfile`, `uuid`, `ruamel.yaml>=0.18,<0.19`, `pytest`, `hatchling`.

## Global Constraints

- The core accepts only schema-version-1 events and never infers advancement from arbitrary natural language.
- A module cannot enter `awaiting_confirmation` or `completed` unless current-module unit and regression evidence both have exit code `0`.
- Only an event with `type="next_module_confirmed"`, `actor="user"`, and `payload.confirmation="explicit_command"` can authorize the document transaction.
- Spec and plan writes are SHA-256 checked, backed up, staged, rolled back together on failure, and restricted to configured project-relative document paths.
- Runtime writes are restricted to the configured `.spec-driven/` directory; test output is summarized and no remote service is called.
- Configuration precedence is built-in defaults → global config → project config → session override.
- Ambiguous document candidates, module boundaries, or inferred test commands stop the workflow and return stable errors.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
pyproject.toml
.gitignore
src/spec_driven/
  __init__.py
  capabilities.py
  cli.py
  config.py
  discovery.py
  engine.py
  errors.py
  events.py
  models.py
  state.py
  transactions.py
  adapters/
    __init__.py
    generic.py
  documents/
    __init__.py
    base.py
    markdown.py
  modules.py
  patches.py
skills/spec-driven-development/SKILL.md
fixtures/markdown-project/
tests/unit/
tests/contract/
tests/integration/
tests/e2e/
```

`models.py` contains immutable values only. `config.py`, `discovery.py`, and `modules.py` do not write. `events.py` and `state.py` own machine persistence. `documents/` owns format syntax. `transactions.py` owns multi-file durability. `engine.py` alone coordinates state, event, and document changes.

---

### Task 1: Bootstrap the package and test runner

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/spec_driven/__init__.py`
- Create: `src/spec_driven/cli.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_package.py`

**Interfaces:**
- Produces `spec_driven.__version__: str`.
- Produces `spec_driven.cli.main(argv: list[str] | None = None) -> int`.

- [x] **Step 1: Write the failing package test**

```python
from spec_driven import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [x] **Step 2: Run it and verify the package is missing**

Run:

```bash
python -m pytest tests/unit/test_package.py -q
```

Expected: `ModuleNotFoundError: No module named 'spec_driven'`.

- [x] **Step 3: Add build configuration and the minimal package**

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.25,<2"]
build-backend = "hatchling.build"

[project]
name = "spec-driven-development"
version = "0.1.0"
description = "Host-neutral spec-driven development workflow engine"
requires-python = ">=3.11"
dependencies = ["ruamel.yaml>=0.18,<0.19"]

[project.optional-dependencies]
test = ["pytest>=8,<9"]

[project.scripts]
spec-driven = "spec_driven.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/spec_driven"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

`src/spec_driven/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/spec_driven/cli.py`:

```python
from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    del argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path
```

`.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
*.egg-info/
.spec-driven/
```

- [x] **Step 4: Install editable dependencies and pass the test**

Run:

```bash
python -m pip install -e '.[test]'
python -m pytest tests/unit/test_package.py -q
```

Expected: `1 passed`.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src tests/conftest.py tests/unit/test_package.py
git commit -m "chore: bootstrap spec-driven package"
```

---

> **Implementation notes (Task 1 complete):** Tests/CLI must run through the uv-managed `.venv` (Python 3.12): `.venv/bin/python -m pytest -q` and `.venv/bin/spec-driven`. System `python` is absent and system `python3` is 3.9.

### Task 2: Define domain values, errors, and layered configuration

**Files:**
- Create: `src/spec_driven/models.py`
- Create: `src/spec_driven/capabilities.py`
- Create: `src/spec_driven/errors.py`
- Create: `src/spec_driven/config.py`
- Create: `tests/unit/test_models.py`
- Create: `tests/unit/test_capabilities.py`
- Create: `tests/unit/test_config.py`

**Interfaces:**
- Produces frozen `Module`, `DocumentRef`, `TestEvidence`, `Checkpoint`, `DocumentUpdate`, `Event`, `ProjectConfig`, and `StateSnapshot`.
- Produces `Capability` and `CapabilityReport.to_dict()` for every host adapter.
- `load_config(project_root: Path, global_path: Path | None = None, session_override: Mapping[str, object] | None = None) -> ProjectConfig`.
- Every raised `SpecDrivenError` has stable `code`, `retryable`, and `remediation` fields.

- [x] **Step 1: Write failing immutability and precedence tests**

```python
from pathlib import Path

import pytest

from spec_driven.config import load_config
from spec_driven.models import Module


def test_module_is_immutable() -> None:
    module = Module("M1", "Core", 1, "Build core", (), (), ("unit", "regression"))
    with pytest.raises(AttributeError):
        module.order = 2  # type: ignore[misc]


def test_project_and_session_override_global_config(tmp_path: Path) -> None:
    global_path = tmp_path / "global.yaml"
    global_path.write_text("tests:\n  unit:\n    command: global-unit\n", encoding="utf-8")
    (tmp_path / "spec-driven.config.yaml").write_text(
        "tests:\n  unit:\n    command: project-unit\n", encoding="utf-8"
    )
    project = load_config(tmp_path, global_path)
    session = load_config(
        tmp_path,
        global_path,
        {"tests": {"unit": {"command": "session-unit"}}},
    )
    assert project.unit_test_command == "project-unit"
    assert session.unit_test_command == "session-unit"
```

- [x] **Step 2: Run tests and verify imports fail**

Run:

```bash
python -m pytest tests/unit/test_models.py tests/unit/test_config.py -q
```

Expected: import errors for missing modules.

- [x] **Step 3: Implement immutable domain values**

`src/spec_driven/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModuleState = Literal["pending", "implementing", "testing", "awaiting_confirmation", "completed"]
SessionState = Literal["active", "paused", "completed"]


@dataclass(frozen=True)
class Module:
    module_id: str
    title: str
    order: int
    goal: str
    prerequisites: tuple[str, ...]
    acceptance: tuple[str, ...]
    test_requirements: tuple[str, ...]


@dataclass(frozen=True)
class DocumentRef:
    kind: Literal["spec", "plan"]
    path: str
    sha256: str


@dataclass(frozen=True)
class TestEvidence:
    kind: Literal["unit", "regression"]
    module_id: str
    command: str
    working_directory: str
    started_at: str
    finished_at: str
    exit_code: int
    output_path: str | None
    output_summary: str
    attempt: int


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    module_id: str
    completed_points: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class DocumentUpdate:
    module_id: str
    status: str
    next_module_id: str | None
    completed_points: tuple[str, ...]
    notes: tuple[str, ...]
    evidence_summary: tuple[str, ...]


@dataclass(frozen=True)
class Event:
    event_id: str
    schema_version: int
    session_id: str
    type: str
    occurred_at: str
    source: str
    actor: str
    module_id: str | None
    payload: dict[str, object]


@dataclass(frozen=True)
class ProjectConfig:
    schema_version: int
    spec_paths: tuple[str, ...]
    plan_paths: tuple[str, ...]
    unit_test_command: str | None
    regression_test_command: str | None
    document_adapters: tuple[str, ...]
    host_adapter: str
    confirmation_command: str
    state_dir: str
    allow_module_inference: bool


@dataclass(frozen=True)
class StateSnapshot:
    schema_version: int
    session_id: str
    session_state: SessionState
    current_module_id: str | None
    module_order: tuple[str, ...]
    module_states: dict[str, ModuleState]
    documents: tuple[DocumentRef, ...]
    evidence: tuple[TestEvidence, ...]
    checkpoint: Checkpoint | None
    processed_event_ids: frozenset[str]
```

- [x] **Step 4: Add the shared capability report model**

`tests/unit/test_capabilities.py`:

```python
from spec_driven.capabilities import Capability, CapabilityReport


def test_capability_report_serializes_stable_fields() -> None:
    report = CapabilityReport(1, "generic", "0.1.0", (Capability("confirmation", "available", "CLI", "exact command", None),))
    assert report.to_dict()["capabilities"][0]["status"] == "available"
```

`src/spec_driven/capabilities.py`:

```python
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
```

- [x] **Step 5: Implement stable errors**

`src/spec_driven/errors.py`:

```python
class SpecDrivenError(Exception):
    code = "SPEC_DRIVEN_ERROR"

    def __init__(self, message: str, *, retryable: bool = False, remediation: str | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.remediation = remediation


class ConfigError(SpecDrivenError):
    code = "CONFIG_INVALID"


class DiscoveryAmbiguousError(SpecDrivenError):
    code = "DISCOVERY_AMBIGUOUS"


class InvalidEventError(SpecDrivenError):
    code = "EVENT_INVALID"


class GateBlockedError(SpecDrivenError):
    code = "TEST_GATE_BLOCKED"


class StateConflictError(SpecDrivenError):
    code = "STATE_CONFLICT"


class DocumentConflictError(SpecDrivenError):
    code = "DOCUMENT_CONFLICT"


class RecoveryRequiredError(SpecDrivenError):
    code = "RECOVERY_REQUIRED"
```

- [x] **Step 6: Implement layered YAML configuration**

`src/spec_driven/config.py`:

```python
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
```

- [x] **Step 7: Pass focused and full tests, then commit**

```bash
python -m pytest tests/unit/test_models.py tests/unit/test_capabilities.py tests/unit/test_config.py -q
python -m pytest -q
git add src/spec_driven/models.py src/spec_driven/capabilities.py src/spec_driven/errors.py src/spec_driven/config.py tests/unit/test_models.py tests/unit/test_capabilities.py tests/unit/test_config.py
git commit -m "feat: add domain values and configuration"
```

---

> **Implementation notes (Task 2 complete):** `TestEvidence` starts with `Test`, so importing it directly into a test module triggers PytestCollectionWarning — import via `spec_driven.models as models` instead (done in existing tests). Adapter plans consume these exact dataclass field orders.

### Task 3: Discover Markdown documents and parse explicit module boundaries

**Files:**
- Create: `src/spec_driven/discovery.py`
- Create: `src/spec_driven/modules.py`
- Create: `fixtures/markdown-project/spec-driven.config.yaml`
- Create: `fixtures/markdown-project/docs/specs/product.md`
- Create: `fixtures/markdown-project/docs/plans/product-plan.md`
- Create: `tests/unit/test_discovery.py`
- Create: `tests/unit/test_modules.py`

**Interfaces:**
- `discover_documents(project_root: Path, config: ProjectConfig) -> tuple[DocumentRef, DocumentRef]` returns spec then plan.
- `infer_test_commands(project_root: Path, config: ProjectConfig) -> tuple[str, str]` returns only an unambiguous pair.
- `parse_plan_modules(path: Path, allow_inference: bool) -> tuple[Module, ...]` accepts explicit managed markers and contiguous order.

- [x] **Step 1: Write failing discovery and module tests**

```python
from pathlib import Path

import pytest

from spec_driven.config import load_config
from spec_driven.discovery import discover_documents
from spec_driven.errors import DiscoveryAmbiguousError
from spec_driven.modules import parse_plan_modules


def test_fixture_has_one_spec_and_one_plan() -> None:
    root = Path("fixtures/markdown-project")
    refs = discover_documents(root, load_config(root))
    assert [(ref.kind, ref.path) for ref in refs] == [
        ("spec", "docs/specs/product.md"),
        ("plan", "docs/plans/product-plan.md"),
    ]


def test_equal_candidates_stop_discovery(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a-spec.md").write_text("# A", encoding="utf-8")
    (tmp_path / "docs/b-spec.md").write_text("# B", encoding="utf-8")
    (tmp_path / "docs/plan.md").write_text("# Plan", encoding="utf-8")
    with pytest.raises(DiscoveryAmbiguousError):
        discover_documents(tmp_path, load_config(tmp_path))


def test_explicit_markers_produce_contiguous_modules() -> None:
    modules = parse_plan_modules(Path("fixtures/markdown-project/docs/plans/product-plan.md"), True)
    assert [(module.module_id, module.order) for module in modules] == [("M1", 1), ("M2", 2)]
```

- [x] **Step 2: Run tests and verify missing imports**

```bash
python -m pytest tests/unit/test_discovery.py tests/unit/test_modules.py -q
```

Expected: import errors.

- [x] **Step 3: Add a complete fixture**

`fixtures/markdown-project/spec-driven.config.yaml`:

```yaml
schema_version: 1
spec:
  paths: [docs/specs/product.md]
plan:
  paths: [docs/plans/product-plan.md]
tests:
  unit:
    command: python -m pytest tests/unit -q
  regression:
    command: python -m pytest -q
documents:
  adapters: [markdown]
```

Both fixture documents contain these managed module blocks for `M1` and `M2`; prose outside the blocks differs between spec and plan:

```markdown
<!-- spec-driven:module id="M1" order="1" status="pending" -->
## M1: Core workflow

Goal: Create the core workflow.

Acceptance:
- State transitions are validated.
- Both test gates are recorded.

Tests: unit, regression

<!-- spec-driven:completion -->
Status: pending
Next module: M2
Completed points:
Notes:
Evidence:
<!-- /spec-driven:completion -->
<!-- /spec-driven:module -->
```

The `M2` block has `order="2"`, `status="pending"`, goal `Translate host events`, and `Next module:` with an empty value.

- [x] **Step 4: Implement discovery with configured paths before scanning**

`src/spec_driven/discovery.py`:

```python
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
```

- [x] **Step 5: Implement marker-first module parsing**

`src/spec_driven/modules.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

from .errors import DiscoveryAmbiguousError
from .models import Module

_START = re.compile(r'<!--\s*spec-driven:module\s+id="([^"]+)"\s+order="(\d+)"\s+status="[^"]+"\s*-->')
_END = "<!-- /spec-driven:module -->"


def _single(lines: list[str], prefix: str) -> str:
    matches = [line[len(prefix):].strip() for line in lines if line.startswith(prefix)]
    if len(matches) != 1:
        raise DiscoveryAmbiguousError(f"module requires exactly one {prefix.rstrip(':')} field")
    return matches[0]


def parse_plan_modules(path: Path, allow_inference: bool) -> tuple[Module, ...]:
    del allow_inference
    lines = path.read_text(encoding="utf-8").splitlines()
    modules: list[Module] = []
    index = 0
    while index < len(lines):
        match = _START.fullmatch(lines[index].strip())
        if match is None:
            index += 1
            continue
        body: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip() != _END:
            body.append(lines[index])
            index += 1
        if index == len(lines):
            raise DiscoveryAmbiguousError(f"unterminated module marker: {match.group(1)}")
        title_line = next((line for line in body if line.startswith("## ")), "")
        acceptance_start = body.index("Acceptance:") if "Acceptance:" in body else -1
        tests_index = next((position for position, line in enumerate(body) if line.startswith("Tests:")), len(body))
        acceptance = tuple(
            line[2:].strip() for line in body[acceptance_start + 1:tests_index]
            if line.startswith("- ")
        ) if acceptance_start >= 0 else ()
        modules.append(Module(
            module_id=match.group(1),
            title=title_line.split(": ", 1)[-1],
            order=int(match.group(2)),
            goal=_single(body, "Goal:"),
            prerequisites=(),
            acceptance=acceptance,
            test_requirements=tuple(item.strip() for item in _single(body, "Tests:").split(",")),
        ))
        index += 1
    ordered = tuple(sorted(modules, key=lambda module: module.order))
    if not ordered or [module.order for module in ordered] != list(range(1, len(ordered) + 1)):
        raise DiscoveryAmbiguousError("plan requires explicit modules ordered contiguously from 1")
    if len({module.module_id for module in ordered}) != len(ordered):
        raise DiscoveryAmbiguousError("module ids must be unique")
    return ordered
```

- [x] **Step 6: Pass tests and commit**

```bash
python -m pytest tests/unit/test_discovery.py tests/unit/test_modules.py -q
python -m pytest -q
git add src/spec_driven/discovery.py src/spec_driven/modules.py fixtures/markdown-project tests/unit/test_discovery.py tests/unit/test_modules.py
git commit -m "feat: discover documents and parse modules"
```

---

> **Implementation notes (Task 3 complete):** `fixtures/markdown-project` bytes are load-bearing: transactions/E2E hash-compare against them. Never edit prose inside managed blocks; only `MarkdownAdapter.plan_update` may rewrite those regions. Discovery scans use filename tokens (`spec|design`, `plan|roadmap`) when config paths are empty — keep repo-root scanning tests in tmp_path copies.

### Task 4: Persist versioned events, typed snapshots, and test-gated transitions

**Files:**
- Create: `src/spec_driven/events.py`
- Create: `src/spec_driven/state.py`
- Create: `tests/unit/test_events.py`
- Create: `tests/unit/test_state.py`

**Interfaces:**
- `EventStore.append(event: Event) -> bool` atomically returns `False` for duplicate IDs.
- `EventStore.read(event_id: str) -> Event` and `all() -> tuple[Event, ...]`.
- `StateRepository.load() -> StateSnapshot | None`, `save(snapshot: StateSnapshot) -> None` preserve nested types.
- `start_module`, `record_test_result`, `record_checkpoint`, and `complete_current_module` are pure state transforms.

- [x] **Step 1: Write failing persistence and gate tests**

```python
from pathlib import Path

import pytest

from spec_driven.errors import GateBlockedError
from spec_driven.events import EventStore
from spec_driven.models import Checkpoint, DocumentRef, Event, StateSnapshot, TestEvidence
from spec_driven.state import StateRepository, complete_current_module, record_checkpoint, record_test_result


def snapshot() -> StateSnapshot:
    return StateSnapshot(1, "s1", "active", "M1", ("M1", "M2"), {"M1": "implementing", "M2": "pending"}, (DocumentRef("spec", "spec.md", "h"),), (), None, frozenset())


def evidence(kind: str, code: int = 0) -> TestEvidence:
    return TestEvidence(kind, "M1", kind, ".", "t0", "t1", code, None, "summary", 1)


def test_snapshot_round_trip_preserves_nested_values(tmp_path: Path) -> None:
    repository = StateRepository(tmp_path / "state.json")
    repository.save(snapshot())
    assert repository.load() == snapshot()


def test_duplicate_event_id_is_not_rewritten(tmp_path: Path) -> None:
    event = Event("e1", 1, "s1", "module_started", "t", "test", "agent", "M1", {})
    store = EventStore(tmp_path / "events")
    assert store.append(event) is True
    assert store.append(event) is False


def test_checkpoint_requires_both_passing_tests() -> None:
    current = record_test_result(snapshot(), evidence("unit"), "unit-1")
    with pytest.raises(GateBlockedError):
        record_checkpoint(current, Checkpoint("cp1", "M1", ("done",), ()), "cp-event")


def test_last_module_completion_finishes_session() -> None:
    current = snapshot()
    current = record_test_result(current, evidence("unit"), "unit-1")
    current = record_test_result(current, evidence("regression"), "reg-1")
    current = record_checkpoint(current, Checkpoint("cp1", "M1", ("done",), ()), "cp-event")
    completed = complete_current_module(current, "confirm-1")
    assert completed.module_states["M1"] == "completed"
    assert completed.current_module_id == "M2"
```

- [x] **Step 2: Run tests and verify imports fail**

```bash
python -m pytest tests/unit/test_events.py tests/unit/test_state.py -q
```

Expected: import errors.

- [x] **Step 3: Implement event validation and append-only storage**

`src/spec_driven/events.py`:

```python
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from .errors import InvalidEventError
from .models import Event


def validate_event(event: Event) -> None:
    required = (event.event_id, event.session_id, event.type, event.occurred_at, event.source, event.actor)
    if event.schema_version != 1 or any(not value for value in required):
        raise InvalidEventError("event requires schema_version 1 and all identity fields")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", event.event_id) is None:
        raise InvalidEventError("event_id contains unsafe characters")
    if event.type == "next_module_confirmed":
        if event.actor != "user" or event.payload.get("confirmation") != "explicit_command":
            raise InvalidEventError("confirmation requires user actor and explicit_command payload")


class EventStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> bool:
        validate_event(event)
        path = self.directory / f"{event.event_id}.json"
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(asdict(event), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
            return True
        except FileExistsError:
            return False

    def read(self, event_id: str) -> Event:
        return Event(**json.loads((self.directory / f"{event_id}.json").read_text(encoding="utf-8")))

    def all(self) -> tuple[Event, ...]:
        return tuple(self.read(path.stem) for path in sorted(self.directory.glob("*.json")))
```

- [x] **Step 4: Implement typed snapshot serialization**

`src/spec_driven/state.py` begins with:

```python
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from .errors import GateBlockedError, StateConflictError
from .models import Checkpoint, DocumentRef, StateSnapshot, TestEvidence


def _decode(raw: dict[str, object]) -> StateSnapshot:
    documents = tuple(DocumentRef(**item) for item in raw["documents"])
    evidence = tuple(TestEvidence(**item) for item in raw["evidence"])
    checkpoint_raw = raw.get("checkpoint")
    checkpoint = (
        Checkpoint(
            checkpoint_id=str(checkpoint_raw["checkpoint_id"]),
            module_id=str(checkpoint_raw["module_id"]),
            completed_points=tuple(checkpoint_raw["completed_points"]),
            notes=tuple(checkpoint_raw["notes"]),
        )
        if checkpoint_raw
        else None
    )
    return StateSnapshot(
        schema_version=int(raw["schema_version"]),
        session_id=str(raw["session_id"]),
        session_state=raw["session_state"],
        current_module_id=raw.get("current_module_id"),
        module_order=tuple(raw["module_order"]),
        module_states=dict(raw["module_states"]),
        documents=documents,
        evidence=evidence,
        checkpoint=checkpoint,
        processed_event_ids=frozenset(raw["processed_event_ids"]),
    )


class StateRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> StateSnapshot | None:
        if not self.path.is_file():
            return None
        return _decode(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, snapshot: StateSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(snapshot)
        payload["processed_event_ids"] = sorted(snapshot.processed_event_ids)
        fd, temporary = tempfile.mkstemp(prefix="state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
```

- [x] **Step 5: Implement pure gate and transition functions**

Append to `state.py`:

```python
def _ensure_current(snapshot: StateSnapshot, module_id: str) -> None:
    if snapshot.current_module_id != module_id or snapshot.session_state != "active":
        raise StateConflictError(f"module is not current: {module_id}")


def _gate_passes(snapshot: StateSnapshot, module_id: str) -> bool:
    latest = {item.kind: item for item in snapshot.evidence if item.module_id == module_id}
    return all(kind in latest and latest[kind].exit_code == 0 for kind in ("unit", "regression"))


def start_module(snapshot: StateSnapshot, module_id: str, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    _ensure_current(snapshot, module_id)
    if snapshot.module_states[module_id] != "pending":
        raise StateConflictError("module can start only from pending")
    states = dict(snapshot.module_states)
    states[module_id] = "implementing"
    return replace(snapshot, module_states=states, processed_event_ids=snapshot.processed_event_ids | {event_id})


def record_test_result(snapshot: StateSnapshot, item: TestEvidence, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    _ensure_current(snapshot, item.module_id)
    if snapshot.module_states[item.module_id] not in {"implementing", "testing"}:
        raise StateConflictError("test result requires implementing or testing state")
    kept = tuple(value for value in snapshot.evidence if not (value.module_id == item.module_id and value.kind == item.kind))
    states = dict(snapshot.module_states)
    states[item.module_id] = "testing"
    return replace(snapshot, module_states=states, evidence=kept + (item,), processed_event_ids=snapshot.processed_event_ids | {event_id})


def record_checkpoint(snapshot: StateSnapshot, checkpoint: Checkpoint, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    _ensure_current(snapshot, checkpoint.module_id)
    if snapshot.module_states[checkpoint.module_id] != "testing" or not _gate_passes(snapshot, checkpoint.module_id):
        raise GateBlockedError("checkpoint requires passing unit and regression evidence")
    if not checkpoint.completed_points:
        raise StateConflictError("checkpoint requires at least one completed point")
    states = dict(snapshot.module_states)
    states[checkpoint.module_id] = "awaiting_confirmation"
    return replace(snapshot, module_states=states, checkpoint=checkpoint, processed_event_ids=snapshot.processed_event_ids | {event_id})


def complete_current_module(snapshot: StateSnapshot, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    current = snapshot.current_module_id
    if current is None or snapshot.module_states[current] != "awaiting_confirmation" or snapshot.checkpoint is None:
        raise StateConflictError("current module is not awaiting confirmation")
    if not _gate_passes(snapshot, current):
        raise GateBlockedError("confirmation requires passing unit and regression evidence")
    states = dict(snapshot.module_states)
    states[current] = "completed"
    index = snapshot.module_order.index(current)
    next_id = snapshot.module_order[index + 1] if index + 1 < len(snapshot.module_order) else None
    return replace(
        snapshot,
        session_state="active" if next_id else "completed",
        current_module_id=next_id,
        module_states=states,
        checkpoint=None,
        processed_event_ids=snapshot.processed_event_ids | {event_id},
    )
```

- [x] **Step 6: Pass focused and full tests, then commit**

```bash
python -m pytest tests/unit/test_events.py tests/unit/test_state.py -q
python -m pytest -q
git add src/spec_driven/events.py src/spec_driven/state.py tests/unit/test_events.py tests/unit/test_state.py
git commit -m "feat: persist gated module state"
```

---

> **Implementation notes (Task 4 complete):** State transforms are pure; the persistence order used by `CoreEngine`: transform first, append the event only if the snapshot changed (`updated is not snapshot`), then save. Host adapters must mirror this ordering or duplicates will accumulate.

### Task 5: Add the Markdown plugin and recoverable two-document transactions

**Files:**
- Create: `src/spec_driven/documents/base.py`
- Create: `src/spec_driven/documents/markdown.py`
- Create: `src/spec_driven/documents/__init__.py`
- Create: `src/spec_driven/patches.py`
- Create: `src/spec_driven/transactions.py`
- Create: `tests/contract/test_document_adapter.py`
- Create: `tests/unit/test_markdown.py`
- Create: `tests/unit/test_transactions.py`

**Interfaces:**
- `DocumentAdapter` exposes `name`, `suffixes`, `parse_modules`, `plan_update`, and `apply`.
- `DocumentPatch(path: Path, expected_sha256: str, replacement: str, description: str)`.
- `apply_transaction(patches: tuple[DocumentPatch, ...], runtime_root: Path, event_id: str, save_state: Callable[[], None]) -> None`.
- Transaction journal states are `prepared`, `documents_applied`, `committed`, `rolled_back`.

- [x] **Step 1: Write failing adapter and rollback tests**

```python
from pathlib import Path

import pytest

from spec_driven.documents.markdown import MarkdownAdapter
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256
from spec_driven.transactions import apply_transaction


def managed(module_id: str) -> str:
    return (
        f'<!-- spec-driven:module id="{module_id}" order="1" status="pending" -->\n'
        f"## {module_id}: Core\n\nGoal: Build.\n\nTests: unit, regression\n\n"
        "<!-- spec-driven:completion -->\nStatus: pending\nNext module: M2\n"
        "Completed points:\nNotes:\nEvidence:\n<!-- /spec-driven:completion -->\n"
        "<!-- /spec-driven:module -->\n"
    )


def test_markdown_update_is_idempotent_and_preserves_prose(tmp_path: Path) -> None:
    path = tmp_path / "plan.md"
    path.write_text("# Plan\n\n" + managed("M1") + "\nKeep this.\n", encoding="utf-8")
    update = DocumentUpdate("M1", "completed", "M2", ("gate works",), ("reuse API",), ("unit: exit 0", "regression: exit 0"))
    adapter = MarkdownAdapter()
    adapter.apply(adapter.plan_update(path, update, sha256(path)))
    first = path.read_text(encoding="utf-8")
    adapter.apply(adapter.plan_update(path, update, sha256(path)))
    assert path.read_text(encoding="utf-8") == first
    assert "Keep this." in first
    assert "- gate works" in first


def test_transaction_restores_first_document_when_state_save_fails(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("old spec\n", encoding="utf-8")
    plan.write_text("old plan\n", encoding="utf-8")
    from spec_driven.patches import DocumentPatch
    patches = (
        DocumentPatch(spec, sha256(spec), "new spec\n", "spec"),
        DocumentPatch(plan, sha256(plan), "new plan\n", "plan"),
    )
    with pytest.raises(RuntimeError, match="state failed"):
        apply_transaction(patches, tmp_path / ".spec-driven", "e1", lambda: (_ for _ in ()).throw(RuntimeError("state failed")))
    assert spec.read_text(encoding="utf-8") == "old spec\n"
    assert plan.read_text(encoding="utf-8") == "old plan\n"
```

- [x] **Step 2: Run tests and verify imports fail**

```bash
python -m pytest tests/contract/test_document_adapter.py tests/unit/test_markdown.py tests/unit/test_transactions.py -q
```

Expected: import errors.

- [x] **Step 3: Define patch primitives and plugin protocol**

`src/spec_driven/patches.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class DocumentPatch:
    path: Path
    expected_sha256: str
    replacement: str
    description: str
```

`src/spec_driven/documents/base.py`:

```python
from pathlib import Path
from typing import Protocol

from ..models import DocumentUpdate, Module
from ..patches import DocumentPatch


class DocumentAdapter(Protocol):
    name: str
    suffixes: frozenset[str]

    def parse_modules(self, path: Path) -> tuple[Module, ...]: ...
    def plan_update(self, path: Path, update: DocumentUpdate, expected_sha256: str) -> DocumentPatch: ...
    def apply(self, patch: DocumentPatch) -> None: ...
```

- [x] **Step 4: Implement managed-block Markdown updates**

`src/spec_driven/documents/markdown.py`:

```python
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from ..errors import DocumentConflictError
from ..models import DocumentUpdate, Module
from ..modules import parse_plan_modules
from ..patches import DocumentPatch, sha256

_START = re.compile(r'(<!--\s*spec-driven:module\s+id="(?P<id>[^"]+)"\s+order="(?P<order>\d+)"\s+status=")(?P<status>[^"]+)("\s*-->)')
_COMPLETION = re.compile(r'<!-- spec-driven:completion -->.*?<!-- /spec-driven:completion -->', re.DOTALL)


class MarkdownAdapter:
    name = "markdown"
    suffixes = frozenset({".md", ".markdown"})

    def parse_modules(self, path: Path) -> tuple[Module, ...]:
        return parse_plan_modules(path, allow_inference=True)

    def plan_update(self, path: Path, update: DocumentUpdate, expected_sha256: str) -> DocumentPatch:
        if sha256(path) != expected_sha256:
            raise DocumentConflictError(f"stale document hash: {path}")
        content = path.read_text(encoding="utf-8")
        starts = list(_START.finditer(content))
        target = next((item for item in starts if item.group("id") == update.module_id), None)
        if target is None:
            raise DocumentConflictError(f"managed module not found: {update.module_id}")
        end_token = "<!-- /spec-driven:module -->"
        end = content.find(end_token, target.end())
        if end < 0:
            raise DocumentConflictError(f"unterminated managed module: {update.module_id}")
        block = content[target.start():end]
        block = _START.sub(lambda match: f'{match.group(1)}{update.status}{match.group(5)}', block, count=1)
        completion = "\n".join((
            "<!-- spec-driven:completion -->",
            f"Status: {update.status}",
            f"Next module: {update.next_module_id or ''}",
            "Completed points:",
            *(f"- {item}" for item in update.completed_points),
            "Notes:",
            *(f"- {item}" for item in update.notes),
            "Evidence:",
            *(f"- {item}" for item in update.evidence_summary),
            "<!-- /spec-driven:completion -->",
        ))
        if _COMPLETION.search(block):
            block = _COMPLETION.sub(completion, block, count=1)
        else:
            block = block.rstrip() + "\n\n" + completion + "\n"
        replacement = content[:target.start()] + block + content[end:]
        return DocumentPatch(path, expected_sha256, replacement, f"complete {update.module_id}")

    def apply(self, patch: DocumentPatch) -> None:
        if sha256(patch.path) != patch.expected_sha256:
            raise DocumentConflictError(f"stale document hash: {patch.path}")
        fd, temporary = tempfile.mkstemp(prefix=f"{patch.path.name}.", dir=patch.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(patch.replacement)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, patch.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
```

- [x] **Step 5: Implement the multi-file journaled transaction**

`src/spec_driven/transactions.py`:

```python
from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from .errors import DocumentConflictError
from .patches import DocumentPatch, sha256


def _write_journal(path: Path, status: str, patches: tuple[DocumentPatch, ...]) -> None:
    payload = {
        "schema_version": 1,
        "status": status,
        "paths": [str(patch.path) for patch in patches],
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def apply_transaction(
    patches: tuple[DocumentPatch, ...],
    runtime_root: Path,
    event_id: str,
    save_state: Callable[[], None],
) -> None:
    transaction = runtime_root / "transactions" / event_id
    backups = transaction / "backups"
    staged = transaction / "staged"
    journal = transaction / "journal.json"
    backups.mkdir(parents=True, exist_ok=True)
    staged.mkdir(parents=True, exist_ok=True)
    if journal.is_file() and json.loads(journal.read_text(encoding="utf-8"))["status"] == "committed":
        return
    for patch in patches:
        if sha256(patch.path) != patch.expected_sha256:
            raise DocumentConflictError(f"stale document hash: {patch.path}")
    for index, patch in enumerate(patches):
        shutil.copy2(patch.path, backups / f"{index}.bak")
        (staged / f"{index}.new").write_text(patch.replacement, encoding="utf-8")
    _write_journal(journal, "prepared", patches)
    replaced: list[int] = []
    try:
        for index, patch in enumerate(patches):
            (staged / f"{index}.new").replace(patch.path)
            replaced.append(index)
        _write_journal(journal, "documents_applied", patches)
        save_state()
        _write_journal(journal, "committed", patches)
    except BaseException:
        for index in replaced:
            shutil.copy2(backups / f"{index}.bak", patches[index].path)
        _write_journal(journal, "rolled_back", patches)
        raise
```

- [x] **Step 6: Add the adapter contract test and pass all tests**

`tests/contract/test_document_adapter.py` verifies `MarkdownAdapter.name`, suffixes, module parsing, `DocumentUpdate` planning, stale-hash rejection, and idempotent apply.

Run:

```bash
python -m pytest tests/contract/test_document_adapter.py tests/unit/test_markdown.py tests/unit/test_transactions.py -q
python -m pytest -q
git add src/spec_driven/documents src/spec_driven/patches.py src/spec_driven/transactions.py tests/contract/test_document_adapter.py tests/unit/test_markdown.py tests/unit/test_transactions.py
git commit -m "feat: add recoverable Markdown transactions"
```

---

> **Implementation notes (Task 5 complete):** Transaction journals live at `<state_dir>/transactions/<event_id>/journal.json`; `recover()` treats status `documents_applied` as requiring manual recovery. YAML/JSON adapters (structured-documents plan) must implement the same `DocumentAdapter` Protocol — idempotent regeneration of managed content is what keeps replays byte-stable.

### Task 6: Coordinate the engine, generic adapter, and JSON CLI

**Files:**
- Create: `src/spec_driven/engine.py`
- Create: `src/spec_driven/adapters/__init__.py`
- Create: `src/spec_driven/adapters/generic.py`
- Modify: `src/spec_driven/cli.py`
- Create: `tests/integration/test_engine.py`
- Create: `tests/integration/test_generic_adapter.py`
- Create: `tests/integration/test_cli.py`

**Interfaces:**
- `CoreEngine.start()`, `start_module(event)`, `record_test(event_id, evidence)`, `record_checkpoint(event_id, checkpoint)`, `confirm_next(event)`, `status()`, `recover()`.
- `GenericAdapter.normalize(raw: Mapping[str, object]) -> Event` rejects non-explicit confirmation.
- CLI commands accept structured JSON through `--input PATH` or stdin `-`: `start`, `status`, `start-module`, `record-test`, `checkpoint`, `confirm-next`, `recover`, `doctor`.
- JSON errors contain `code`, `message`, `retryable`, and `remediation` and map to exit code `1`; malformed CLI input maps to `2`.

- [x] **Step 1: Write failing engine integration tests**

```python
import shutil
from pathlib import Path

import pytest

from spec_driven.engine import CoreEngine
from spec_driven.errors import GateBlockedError
from spec_driven.models import Checkpoint, Event, TestEvidence


def event(event_id: str, event_type: str, actor: str = "agent") -> Event:
    return Event(event_id, 1, "session-1", event_type, "2026-08-26T00:00:00Z", "generic", actor, "M1", {"confirmation": "explicit_command"} if event_type == "next_module_confirmed" else {})


def evidence(kind: str, code: int = 0) -> TestEvidence:
    return TestEvidence(kind, "M1", kind, ".", "t0", "t1", code, None, "summary", 1)


def test_engine_updates_both_documents_only_after_gate(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(event("start-1", "module_started"))
    engine.record_test("unit-1", evidence("unit"))
    with pytest.raises(GateBlockedError):
        engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("state works",), ()))
    engine.record_test("reg-1", evidence("regression"))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("state works",), ("reuse API",)))
    engine.confirm_next(event("confirm-1", "next_module_confirmed", "user"))
    assert 'status="completed"' in (root / "docs/specs/product.md").read_text(encoding="utf-8")
    assert 'status="completed"' in (root / "docs/plans/product-plan.md").read_text(encoding="utf-8")
    assert engine.status().current_module_id == "M2"
```

- [x] **Step 2: Run tests and verify engine import fails**

```bash
python -m pytest tests/integration/test_engine.py -q
```

Expected: import error for `CoreEngine`.

- [x] **Step 3: Implement the engine as the only transaction coordinator**

`src/spec_driven/engine.py`:

```python
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .config import load_config
from .discovery import discover_documents
from .documents.markdown import MarkdownAdapter
from .errors import InvalidEventError, RecoveryRequiredError
from .events import EventStore, validate_event
from .models import Checkpoint, DocumentUpdate, Event, StateSnapshot, TestEvidence
from .patches import sha256
from .state import StateRepository, complete_current_module, record_checkpoint, record_test_result, start_module
from .transactions import apply_transaction


class CoreEngine:
    def __init__(self, project_root: Path, session_id_factory: Callable[[], str] | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = load_config(self.project_root)
        self.runtime = (self.project_root / self.config.state_dir).resolve()
        if self.project_root not in self.runtime.parents:
            raise InvalidEventError("runtime directory must be inside project")
        self.state_repository = StateRepository(self.runtime / "state.json")
        self.event_store = EventStore(self.runtime / "events")
        self.adapter = MarkdownAdapter()
        self.session_id_factory = session_id_factory or (lambda: uuid4().hex)

    @classmethod
    def from_project(cls, project_root: Path, session_id_factory: Callable[[], str] | None = None) -> "CoreEngine":
        return cls(project_root, session_id_factory)

    def status(self) -> StateSnapshot:
        snapshot = self.state_repository.load()
        if snapshot is None:
            raise InvalidEventError("session has not started", remediation="run spec-driven start")
        return snapshot

    def start(self) -> StateSnapshot:
        existing = self.state_repository.load()
        if existing is not None:
            return existing
        spec, plan = discover_documents(self.project_root, self.config)
        modules = self.adapter.parse_modules(self.project_root / plan.path)
        snapshot = StateSnapshot(
            1,
            self.session_id_factory(),
            "active",
            modules[0].module_id,
            tuple(module.module_id for module in modules),
            {module.module_id: "pending" for module in modules},
            (spec, plan),
            (),
            None,
            frozenset(),
        )
        self.state_repository.save(snapshot)
        return snapshot

    def start_module(self, event: Event) -> StateSnapshot:
        snapshot = self.status()
        validate_event(event)
        updated = start_module(snapshot, event.module_id or "", event.event_id)
        self.event_store.append(event)
        self.state_repository.save(updated)
        return updated

    def record_test(self, event_id: str, item: TestEvidence) -> StateSnapshot:
        snapshot = self.status()
        updated = record_test_result(snapshot, item, event_id)
        self.event_store.append(Event(event_id, 1, snapshot.session_id, "test_finished", item.finished_at, "core", "host", item.module_id, {"kind": item.kind, "exit_code": item.exit_code}))
        self.state_repository.save(updated)
        return updated

    def record_checkpoint(self, event_id: str, checkpoint: Checkpoint) -> StateSnapshot:
        snapshot = self.status()
        updated = record_checkpoint(snapshot, checkpoint, event_id)
        self.event_store.append(Event(event_id, 1, snapshot.session_id, "checkpoint_recorded", "local", "core", "agent", checkpoint.module_id, {"checkpoint_id": checkpoint.checkpoint_id}))
        self.state_repository.save(updated)
        return updated

    def confirm_next(self, event: Event) -> StateSnapshot:
        snapshot = self.status()
        validate_event(event)
        if event.session_id != snapshot.session_id or event.module_id != snapshot.current_module_id:
            raise InvalidEventError("confirmation session/module does not match current state")
        if event.event_id in snapshot.processed_event_ids:
            return snapshot
        updated = complete_current_module(snapshot, event.event_id)
        checkpoint = snapshot.checkpoint
        if checkpoint is None:
            raise InvalidEventError("confirmation requires checkpoint")
        latest = {item.kind: item for item in snapshot.evidence if item.module_id == event.module_id}
        update = DocumentUpdate(
            event.module_id,
            "completed",
            updated.current_module_id,
            checkpoint.completed_points,
            checkpoint.notes,
            (f"unit: exit {latest['unit'].exit_code}", f"regression: exit {latest['regression'].exit_code}"),
        )
        patches = tuple(
            self.adapter.plan_update(self.project_root / ref.path, update, sha256(self.project_root / ref.path))
            for ref in snapshot.documents
        )
        self.event_store.append(event)
        apply_transaction(patches, self.runtime, event.event_id, lambda: self.state_repository.save(updated))
        self.event_store.append(Event(f"{event.event_id}-documents-updated", 1, snapshot.session_id, "documents_updated", event.occurred_at, "core", "core", event.module_id, {"paths": [ref.path for ref in snapshot.documents]}))
        return updated

    def recover(self) -> StateSnapshot:
        snapshot = self.status()
        incomplete = [path for path in (self.runtime / "transactions").glob("*/journal.json") if __import__("json").loads(path.read_text(encoding="utf-8"))["status"] == "documents_applied"]
        if incomplete:
            raise RecoveryRequiredError("transaction requires explicit recovery", remediation=f"inspect {incomplete[0].parent}")
        return snapshot
```

- [x] **Step 4: Implement generic normalization**

`src/spec_driven/adapters/generic.py`:

```python
from collections.abc import Mapping

from ..errors import InvalidEventError
from ..models import Event


class GenericAdapter:
    def normalize(self, raw: Mapping[str, object]) -> Event:
        payload = raw.get("payload")
        if not isinstance(payload, Mapping):
            raise InvalidEventError("event payload must be a mapping")
        event = Event(
            event_id=str(raw.get("event_id", "")),
            schema_version=int(raw.get("schema_version", 0)),
            session_id=str(raw.get("session_id", "")),
            type=str(raw.get("type", "")),
            occurred_at=str(raw.get("occurred_at", "")),
            source="generic",
            actor=str(raw.get("actor", "")),
            module_id=str(raw["module_id"]) if raw.get("module_id") is not None else None,
            payload=dict(payload),
        )
        if event.type == "next_module_confirmed" and event.payload.get("confirmation") != "explicit_command":
            raise InvalidEventError("generic confirmation requires explicit_command")
        return event
```

- [x] **Step 5: Implement JSON CLI parsing and errors**

Replace `src/spec_driven/cli.py` with an `argparse` parser whose subcommands share `--project`, whose structured commands share `--input` defaulting to `-`, and whose handlers decode exact `Event`, `TestEvidence`, and `Checkpoint` dataclasses. Serialize dataclasses with `dataclasses.asdict`; print errors as:

```python
{
    "code": error.code,
    "message": str(error),
    "retryable": error.retryable,
    "remediation": error.remediation,
}
```

The command-to-engine mapping is:

```python
{
    "start": engine.start,
    "status": engine.status,
    "start-module": lambda: engine.start_module(Event(**payload)),
    "record-test": lambda: engine.record_test(str(payload["event_id"]), TestEvidence(**payload["evidence"])),
    "checkpoint": lambda: engine.record_checkpoint(str(payload["event_id"]), Checkpoint(**payload["checkpoint"])),
    "confirm-next": lambda: engine.confirm_next(GenericAdapter().normalize(payload)),
    "recover": engine.recover,
}
```

`cli.py` must also implement the `doctor` handler without modifying files:

```python
def doctor(project: Path) -> dict[str, object]:
    config = load_config(project)
    spec, plan = discover_documents(project, config)
    modules = MarkdownAdapter().parse_modules(project / plan.path)
    unit, regression = infer_test_commands(project, config)
    return {
        "status": "ok",
        "documents": {"spec": spec.path, "plan": plan.path},
        "modules": [module.module_id for module in modules],
        "tests": {"unit": unit, "regression": regression},
    }
```

The `doctor` subcommand prints this mapping as JSON and returns `0`; discovery/configuration errors use the standard error shape and return `1`.

- [x] **Step 6: Pass engine/CLI tests and commit**

```bash
python -m pytest tests/integration/test_engine.py tests/integration/test_generic_adapter.py tests/integration/test_cli.py -q
python -m pytest -q
git add src/spec_driven/engine.py src/spec_driven/adapters src/spec_driven/cli.py tests/integration
git commit -m "feat: expose the gated core engine"
```

---

> **Implementation notes (Task 6 complete):** `confirm_next` hard-verifies `session_id` + `module_id` against the live snapshot — hosts must echo back the session id from `start` output. Structured CLI inputs must carry every `Event` field including `source`. CLI errors: exit 1 domain failures with `{code,message,retryable,remediation}`; exit 2 malformed input (`CLI_INPUT_INVALID`). Snapshot JSON emission converts frozensets to sorted lists (`_jsonable`).

### Task 7: Add the agent-facing skill and end-to-end recovery tests

**Files:**
- Create: `skills/spec-driven-development/SKILL.md`
- Create: `tests/e2e/test_markdown_workflow.py`
- Create: `tests/e2e/test_recovery.py`

**Interfaces:**
- Skill invokes only public CLI commands and explicitly requests `confirm-next` after both gates pass.
- E2E proves pass, failure, duplicate, stale-hash, rollback, final-module, and natural-language paths.

- [ ] **Step 1: Write the complete skill**

`skills/spec-driven-development/SKILL.md`:

```markdown
---
name: spec-driven-development
description: Drive modular coding work from spec and plan with unit and regression gates.
---

# Spec-Driven Development

1. Run `spec-driven start --project <root>` when the user explicitly starts this workflow.
2. If discovery reports multiple candidates or unclear modules/tests, show the candidates and wait for a user selection; do not guess.
3. Submit `module_started` through `spec-driven start-module`, then implement only the current module MVP.
4. Run the configured module unit command and full regression command. Submit each real exit code and controlled summary through `spec-driven record-test`.
5. If either test fails, remain in `testing`, report the failure, fix it, and rerun both required commands.
6. After both pass, submit a checkpoint containing completed points and later-module notes.
7. Show the evidence and ask the user to type exactly `confirm-next`.
8. Replies such as “继续” or “可以” are not authorization. Repeat the exact-command request without editing spec or plan.
9. Submit the exact confirmation through `spec-driven confirm-next`; only the core may update documents.
10. Run `spec-driven status` after each transition and `spec-driven recover` after interruption.
```

- [ ] **Step 2: Write the E2E matrix**

`tests/e2e/test_markdown_workflow.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from spec_driven.adapters.generic import GenericAdapter
from spec_driven.engine import CoreEngine
from spec_driven.errors import GateBlockedError, InvalidEventError
from spec_driven.models import Checkpoint, Event, TestEvidence


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def _event(event_id: str, event_type: str, actor: str = "agent", module_id: str = "M1") -> Event:
    return Event(
        event_id,
        1,
        "session-1",
        event_type,
        "2026-08-26T00:00:00Z",
        "generic",
        actor,
        module_id,
        {"confirmation": "explicit_command"} if event_type == "next_module_confirmed" else {},
    )


def _evidence(kind: str, code: int) -> TestEvidence:
    return TestEvidence(kind, "M1", kind, ".", "t0", "t1", code, None, "summary", 1)


@pytest.mark.parametrize(
    ("unit_code", "regression_code", "can_checkpoint"),
    [(0, 0, True), (1, 0, False), (0, 1, False)],
)
def test_two_test_gate(
    unit_code: int,
    regression_code: int,
    can_checkpoint: bool,
    tmp_path: Path,
) -> None:
    engine = CoreEngine.from_project(_root(tmp_path), session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_event("start-1", "module_started"))
    engine.record_test("unit-1", _evidence("unit", unit_code))
    engine.record_test("reg-1", _evidence("regression", regression_code))
    checkpoint = Checkpoint("cp1", "M1", ("MVP works",), ("reuse API",))
    if can_checkpoint:
        assert engine.record_checkpoint("cp-event", checkpoint).module_states["M1"] == "awaiting_confirmation"
    else:
        with pytest.raises(GateBlockedError):
            engine.record_checkpoint("cp-event", checkpoint)


def test_exact_confirmation_updates_both_documents_once(tmp_path: Path) -> None:
    root = _root(tmp_path)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_event("start-1", "module_started"))
    engine.record_test("unit-1", _evidence("unit", 0))
    engine.record_test("reg-1", _evidence("regression", 0))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("MVP works",), ("reuse API",)))
    confirmation = _event("confirm-1", "next_module_confirmed", "user")
    first = engine.confirm_next(confirmation)
    second = engine.confirm_next(confirmation)
    assert first == second
    assert first.current_module_id == "M2"
    for relative in ("docs/specs/product.md", "docs/plans/product-plan.md"):
        content = (root / relative).read_text(encoding="utf-8")
        assert content.count("Status: completed") == 1
        assert "- MVP works" in content
        assert "- reuse API" in content


def test_natural_language_cannot_normalize_as_confirmation() -> None:
    adapter = GenericAdapter()
    with pytest.raises(InvalidEventError):
        adapter.normalize({
            "event_id": "e1",
            "schema_version": 1,
            "session_id": "session-1",
            "type": "next_module_confirmed",
            "occurred_at": "t",
            "actor": "user",
            "module_id": "M1",
            "payload": {"confirmation": "继续"},
        })
```

- [ ] **Step 3: Write recovery and conflict tests**

`tests/e2e/test_recovery.py` injects a `save_state` failure into `apply_transaction`, asserts both files roll back, repeats the same event ID, and verifies a successful retry produces one committed journal. It then edits a document after patch planning and asserts `DOCUMENT_CONFLICT` without overwriting that edit.

- [ ] **Step 4: Run baseline verification**

```bash
python -m pytest tests/e2e/test_markdown_workflow.py tests/e2e/test_recovery.py -q
python -m pytest -q
python -m spec_driven.cli doctor --project fixtures/markdown-project
python -m spec_driven.cli start --project fixtures/markdown-project
```

Expected: all tests pass; `start` creates `.spec-driven/state.json` with `M1` pending; `doctor` reports one spec, one plan, and both configured test commands.

- [ ] **Step 5: Commit the baseline**

```bash
git add skills/spec-driven-development/SKILL.md tests/e2e/test_markdown_workflow.py tests/e2e/test_recovery.py
git commit -m "test: prove core gated workflow"
```

> **Implementation notes (Task 7 complete, core baseline finished):** `start` tolerates empty stdin (allow_empty) so roadmap verification commands run bare. CLI `--project` is accepted both before and after the subcommand (subparser uses SUPPRESS default). Never leave a real `.spec-driven/` inside `fixtures/markdown-project` — E2E tests copytree it and a stale state.json would resume instead of starting fresh. Adapter plans (Claude Code / Codex) must route every document mutation through `CoreEngine.confirm_next`; they never call `MarkdownAdapter` directly.

## Baseline acceptance checklist

- [x] Configured Markdown spec/plan are discovered without network access.
- [x] Multiple candidates and unclear modules/tests stop with stable errors.
- [x] Unit-only, regression-only, or any failed evidence blocks the checkpoint.
- [x] Natural language cannot create confirmation or change documents.
- [x] Exact user confirmation updates both spec and plan and activates the next module.
- [x] Repeated event IDs and transactions are idempotent.
- [x] Stale hashes and state-save failures preserve user content.
- [x] Completing the last module produces `session_state="completed"` without a fabricated module.
- [x] Audit events, transaction journals, state, and diagnostics stay under `.spec-driven/`.
