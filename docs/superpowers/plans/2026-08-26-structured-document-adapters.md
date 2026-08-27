# Structured Document Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add YAML and JSON spec/plan adapters that share the core document contract, preserve unknown user content, and pass round-trip, hash-conflict, and end-to-end workflow tests.

**Architecture:** Each format plugin converts only a namespaced `spec_driven` section into the core `Module` and `DocumentUpdate` values. YAML uses `ruamel.yaml` round-trip mode to preserve comments, anchors, ordering, and quoting. JSON loads ordered mappings and writes deterministic UTF-8 JSON. The registry selects adapters by configured name and file suffix; the core continues to own gate decisions and transaction ordering.

**Tech Stack:** Python 3.11+, `ruamel.yaml>=0.18,<0.19`, standard `json`, existing `DocumentAdapter`, `DocumentPatch`, `DocumentUpdate`, `pytest`.

## Global Constraints

- Requires completion of `docs/superpowers/plans/2026-08-26-spec-driven-core-baseline.md`.
- Format plugins only parse and write; they never decide whether a module may advance.
- YAML and JSON documents expose managed state under the top-level `spec_driven` key.
- Unknown keys, array items, YAML comments, anchors, ordering, and scalar quoting must survive a managed update.
- Every patch checks the expected SHA-256 before writing and uses the core atomic writer and backup directory.
- An adapter never executes text found in a document and never writes outside the configured document path.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
src/spec_driven/documents/
  registry.py
  structured.py
  yaml.py
  json.py
fixtures/yaml-project/
fixtures/json-project/
tests/unit/test_document_registry.py
tests/contract/test_structured_document_adapter.py
tests/unit/test_yaml_document.py
tests/unit/test_json_document.py
tests/e2e/test_structured_workflow.py
```

`structured.py` owns format-independent validation and conversion between mappings and core values. `yaml.py` and `json.py` own serialization only. `registry.py` is the single adapter selection point.

---

### Task 1: Register format plugins without changing the core contract

**Files:**
- Create: `src/spec_driven/documents/registry.py`
- Create: `tests/unit/test_document_registry.py`
- Modify: `tests/contract/test_document_adapter.py`

**Interfaces:**
- Consumes baseline `DocumentUpdate`, `Module`, `DocumentPatch`, and `DocumentAdapter` exactly as defined in the core plan.
- `DocumentRegistry.register(adapter: DocumentAdapter) -> None` rejects duplicate names.
- `DocumentRegistry.for_path(path: Path, enabled: tuple[str, ...]) -> DocumentAdapter` requires exactly one enabled suffix match.
- `DocumentRegistry.enabled_suffixes(enabled: tuple[str, ...]) -> frozenset[str]` supports discovery.

- [ ] **Step 1: Write failing registry tests**

```python
from pathlib import Path

import pytest

from spec_driven.documents.registry import DocumentRegistry
from spec_driven.errors import ConfigError


class StubAdapter:
    name = "stub"
    suffixes = frozenset({".stub"})

    def parse_modules(self, path: Path):
        return ()

    def plan_update(self, path, update, expected_sha256):
        raise AssertionError("registry test does not plan updates")

    def apply(self, patch):
        raise AssertionError("registry test does not apply patches")


def test_registry_selects_enabled_suffix() -> None:
    registry = DocumentRegistry()
    registry.register(StubAdapter())
    assert registry.for_path(Path("plan.stub"), ("stub",)).name == "stub"
    assert registry.enabled_suffixes(("stub",)) == frozenset({".stub"})


def test_registry_rejects_disabled_and_duplicate_adapters() -> None:
    registry = DocumentRegistry()
    registry.register(StubAdapter())
    with pytest.raises(ConfigError, match="already registered"):
        registry.register(StubAdapter())
    with pytest.raises(ConfigError, match="no enabled document adapter"):
        registry.for_path(Path("plan.stub"), ("markdown",))
```

- [ ] **Step 2: Run tests and verify the registry is missing**

```bash
python -m pytest tests/unit/test_document_registry.py tests/contract/test_document_adapter.py -q
```

Expected: import error for `DocumentRegistry`; the baseline Markdown contract remains green.

- [ ] **Step 3: Implement duplicate-safe registration and suffix selection**

`src/spec_driven/documents/registry.py`:

```python
from __future__ import annotations

from pathlib import Path

from ..errors import ConfigError
from .base import DocumentAdapter


class DocumentRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, DocumentAdapter] = {}

    def register(self, adapter: DocumentAdapter) -> None:
        if adapter.name in self._adapters:
            raise ConfigError(f"document adapter already registered: {adapter.name}")
        self._adapters[adapter.name] = adapter

    def for_path(self, path: Path, enabled: tuple[str, ...]) -> DocumentAdapter:
        matches = [
            adapter
            for name, adapter in self._adapters.items()
            if name in enabled and path.suffix.lower() in adapter.suffixes
        ]
        if len(matches) != 1:
            raise ConfigError(f"no enabled document adapter for {path}")
        return matches[0]

    def enabled_suffixes(self, enabled: tuple[str, ...]) -> frozenset[str]:
        missing = set(enabled) - set(self._adapters)
        if missing:
            raise ConfigError(f"unknown document adapters: {sorted(missing)}")
        return frozenset(
            suffix
            for name in enabled
            for suffix in self._adapters[name].suffixes
        )
```

- [ ] **Step 4: Extend the contract test with registry dispatch**

Append this assertion to `tests/contract/test_document_adapter.py`:

```python
from spec_driven.documents.registry import DocumentRegistry


def test_baseline_markdown_adapter_dispatches_by_contract() -> None:
    registry = DocumentRegistry()
    registry.register(MarkdownAdapter())
    adapter = registry.for_path(Path("plan.md"), ("markdown",))
    assert adapter.name == "markdown"
    assert callable(adapter.parse_modules)
    assert callable(adapter.plan_update)
    assert callable(adapter.apply)
```

- [ ] **Step 5: Run tests and commit the registry**

```bash
python -m pytest tests/unit/test_document_registry.py tests/contract/test_document_adapter.py -q
python -m pytest -q
git add src/spec_driven/documents/registry.py tests/unit/test_document_registry.py tests/contract/test_document_adapter.py
git commit -m "feat: register document format plugins"
```

---

> **Implementation notes (Task 1 complete):**
> - `for_path` failure message says "no enabled document adapter" even when suffix matches a DISABLED adapter or none — remediation points at `documents.adapters` config. Tests match on that exact phrase.
> - `enabled_suffixes` raises on unknown enabled names BEFORE returning suffixes; discovery (Task 5) depends on this ordering to fail fast on bad config.

### Task 2: Add shared structured-document validation and conversion

**Files:**
- Create: `src/spec_driven/documents/structured.py`
- Create: `tests/contract/test_structured_document_adapter.py`

**Interfaces:**
- `parse_structured_modules(root: Mapping[str, object]) -> tuple[Module, ...]`.
- `apply_structured_update(root: MutableMapping[str, object], update: DocumentUpdate) -> None` mutates only `root["spec_driven"]`.
- Raises `ConfigError` for missing, duplicate, malformed, or non-contiguous module definitions.

- [ ] **Step 1: Write failing conversion tests**

```python
import pytest

from spec_driven.documents.structured import apply_structured_update, parse_structured_modules
from spec_driven.errors import ConfigError
from spec_driven.models import DocumentUpdate


def _root() -> dict[str, object]:
    return {
        "title": "Keep me",
        "spec_driven": {
            "active_module_id": "M1",
            "modules": [
                {
                    "id": "M1",
                    "order": 1,
                    "title": "Core",
                    "goal": "Build core",
                    "status": "pending",
                    "prerequisites": [],
                    "acceptance": ["gate works"],
                    "tests": ["unit", "regression"],
                    "completed_points": [],
                    "notes": [],
                    "evidence": [],
                },
                {
                    "id": "M2",
                    "order": 2,
                    "title": "Adapter",
                    "goal": "Build adapter",
                    "status": "pending",
                    "prerequisites": ["M1"],
                    "acceptance": [],
                    "tests": ["unit", "regression"],
                    "completed_points": [],
                    "notes": [],
                    "evidence": [],
                },
            ],
        },
    }


def test_structured_modules_are_ordered() -> None:
    assert [module.module_id for module in parse_structured_modules(_root())] == ["M1", "M2"]


def test_update_changes_only_managed_values() -> None:
    root = _root()
    apply_structured_update(
        root,
        DocumentUpdate("M1", "completed", "M2", ("gate works",), ("reuse API",), ("unit: pass",)),
    )
    assert root["title"] == "Keep me"
    managed = root["spec_driven"]
    assert managed["active_module_id"] == "M2"
    assert managed["modules"][0]["status"] == "completed"
    assert managed["modules"][0]["notes"] == ["reuse API"]


def test_duplicate_module_ids_are_rejected() -> None:
    root = _root()
    root["spec_driven"]["modules"][1]["id"] = "M1"
    with pytest.raises(ConfigError, match="duplicate module id"):
        parse_structured_modules(root)
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run:

```bash
python -m pytest tests/contract/test_structured_document_adapter.py -q
```

Expected: import error for `documents.structured`.

- [ ] **Step 3: Implement strict structured parsing**

`src/spec_driven/documents/structured.py`:

```python
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
```

- [ ] **Step 4: Run the structured contract tests**

Run:

```bash
python -m pytest tests/contract/test_structured_document_adapter.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit shared structured conversion**

```bash
git add src/spec_driven/documents/structured.py tests/contract/test_structured_document_adapter.py
git commit -m "feat: add structured document conversion"
```

---

> **Implementation notes (Task 2 complete):**
> - `parse_structured_modules` returns modules SORTED by order and rejects non-contiguous/missing `order` — module ids come back in execution order; yaml/json adapters must not re-sort.
> - ruamel round-trip objects are dict subclasses, so `isinstance(raw, Mapping)`/`MutableMapping` checks cover both plain python data and rt-CommentedMap; do NOT tighten to `dict` or YAML round-trip breaks.
> - `apply_structured_update` writes `DocumentUpdate.evidence_summary` into the doc-side `evidence` list field; keep that name mapping when touching this.

### Task 3: Implement comment-preserving YAML support

**Files:**
- Create: `src/spec_driven/documents/yaml.py`
- Create: `fixtures/yaml-project/spec-driven.config.yaml`
- Create: `fixtures/yaml-project/docs/spec.yaml`
- Create: `fixtures/yaml-project/docs/plan.yaml`
- Create: `tests/unit/test_yaml_document.py`

**Interfaces:**
- `YamlAdapter.name == "yaml"` and suffixes `.yaml`, `.yml`.
- Uses `YAML(typ="rt")`, `preserve_quotes = True`, and the core `apply_atomic` writer.

- [ ] **Step 1: Write failing round-trip and hash tests**

```python
from pathlib import Path

from spec_driven.documents.yaml import YamlAdapter
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256


def test_yaml_update_preserves_comments_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(
        "title: 'Keep quotes' # keep comment\n"
        "owner: platform\n"
        "spec_driven:\n"
        "  active_module_id: M1\n"
        "  modules:\n"
        "    - id: M1\n"
        "      order: 1\n"
        "      title: Core\n"
        "      goal: Build\n"
        "      status: pending\n"
        "      prerequisites: []\n"
        "      acceptance: []\n"
        "      tests: [unit, regression]\n"
        "      completed_points: []\n"
        "      notes: []\n"
        "      evidence: []\n",
        encoding="utf-8",
    )
    adapter = YamlAdapter()
    patch = adapter.plan_update(
        path,
        DocumentUpdate("M1", "completed", None, ("done",), ("note",), ("unit: pass",)),
        sha256(path),
    )
    adapter.apply(patch)
    content = path.read_text(encoding="utf-8")
    assert "# keep comment" in content
    assert "title: 'Keep quotes'" in content
    assert "owner: platform" in content
    assert "status: completed" in content
```

- [ ] **Step 2: Run the YAML tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_yaml_document.py -q
```

Expected: import error for `YamlAdapter`.

- [ ] **Step 3: Implement the YAML adapter**

`src/spec_driven/documents/yaml.py`:

```python
from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from ..errors import DocumentConflictError
from ..models import DocumentUpdate, Module
from ..patches import DocumentPatch, apply_atomic, sha256
from .structured import apply_structured_update, parse_structured_modules


class YamlAdapter:
    name = "yaml"
    suffixes = frozenset({".yaml", ".yml"})

    def __init__(self) -> None:
        self.yaml = YAML(typ="rt")
        self.yaml.preserve_quotes = True

    def _load(self, path: Path):
        root = self.yaml.load(path.read_text(encoding="utf-8"))
        if not isinstance(root, dict):
            raise DocumentConflictError(f"YAML root must be a mapping: {path}")
        return root

    def parse_modules(self, path: Path) -> tuple[Module, ...]:
        return parse_structured_modules(self._load(path))

    def plan_update(
        self,
        path: Path,
        update: DocumentUpdate,
        expected_sha256: str,
    ) -> DocumentPatch:
        if sha256(path) != expected_sha256:
            raise DocumentConflictError(f"document hash is stale: {path}")
        root = self._load(path)
        apply_structured_update(root, update)
        output = StringIO()
        self.yaml.dump(root, output)
        return DocumentPatch(path, expected_sha256, output.getvalue(), f"update {update.module_id}")

    def apply(self, patch: DocumentPatch) -> None:
        apply_atomic(patch)
```

- [ ] **Step 4: Add fixture files with a two-module managed section**

`fixtures/yaml-project/spec-driven.config.yaml`:

```yaml
schema_version: 1
spec:
  paths: [docs/spec.yaml]
plan:
  paths: [docs/plan.yaml]
tests:
  unit:
    command: python -m pytest tests/unit -q
  regression:
    command: python -m pytest -q
documents:
  adapters: [yaml]
```

`fixtures/yaml-project/docs/spec.yaml`:

```yaml
title: Product specification
owner: platform
spec_driven:
  active_module_id: M1
  modules:
    - id: M1
      order: 1
      title: Core workflow
      goal: Build the core workflow.
      status: pending
      prerequisites: []
      acceptance:
        - State transitions are validated.
      tests: [unit, regression]
      completed_points: []
      notes: []
      evidence: []
    - id: M2
      order: 2
      title: Host adapter
      goal: Translate host events.
      status: pending
      prerequisites: [M1]
      acceptance: []
      tests: [unit, regression]
      completed_points: []
      notes: []
      evidence: []
```

`fixtures/yaml-project/docs/plan.yaml` has the same `spec_driven` section as `docs/spec.yaml` with `title: Product plan`. Both documents carry the exact same two modules (`M1`/`M2`), fields (`id`, `order`, `title`, `goal`, `status`, `prerequisites`, `acceptance`, `tests`, `completed_points`, `notes`, `evidence`), and `active_module_id: M1`; the prose outside `spec_driven` differs so spec/plan stay distinct files. The `M2` block has `order: 2` and no `acceptance` items.

- [ ] **Step 5: Run YAML tests and the full regression suite**

Run:

```bash
python -m pytest tests/unit/test_yaml_document.py tests/contract/test_structured_document_adapter.py -q
python -m pytest -q
```

Expected: YAML comment/quote preservation and all prior behavior pass.

- [ ] **Step 6: Commit YAML support**

```bash
git add src/spec_driven/documents/yaml.py fixtures/yaml-project tests/unit/test_yaml_document.py
git commit -m "feat: add round-trip YAML documents"
```

---

> **Implementation notes (Task 3 complete):**
> - `apply_atomic` was added to `patches.py` as the shared writer (hash re-check + temp file + fsync + rename); MarkdownAdapter still uses its own inline apply — consolidating it is optional cleanup, do NOT change Markdown bytes behavior casually.
> - ruamel `YAML(typ="rt")` must dump to StringIO, not a path; the patch carries TEXT and atomicity comes from `apply_atomic`.
> - YAML fixtures deliberately mix quoting styles (single/double-quoted scalars, trailing comments) — these bytes are load-bearing for round-trip assertions. Never "tidy" fixture formatting.
> - Stale-hash raises DocumentConflictError before parse (fail fast) — error text contains "stale", matching the core Markdown adapter and the external-edit E2E contract.

### Task 4: Implement deterministic JSON support

**Files:**
- Create: `src/spec_driven/documents/json.py`
- Create: `fixtures/json-project/spec-driven.config.yaml`
- Create: `fixtures/json-project/docs/spec.json`
- Create: `fixtures/json-project/docs/plan.json`
- Create: `tests/unit/test_json_document.py`

**Interfaces:**
- `JsonAdapter.name == "json"` and suffix `.json`.
- JSON output uses `ensure_ascii=False`, `indent=2`, and a final newline; input key order is preserved.

- [ ] **Step 1: Write failing JSON preservation and idempotence tests**

```python
import json
from pathlib import Path

from spec_driven.documents.json import JsonAdapter
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256


def test_json_update_preserves_unknown_fields_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({
        "title": "用户计划",
        "unknown": {"keep": True},
        "spec_driven": {
            "active_module_id": "M1",
            "modules": [{
                "id": "M1", "order": 1, "title": "Core", "goal": "Build",
                "status": "pending", "prerequisites": [], "acceptance": [],
                "tests": ["unit", "regression"], "completed_points": [],
                "notes": [], "evidence": []
            }]
        }
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    adapter = JsonAdapter()
    update = DocumentUpdate("M1", "completed", None, ("done",), (), ("unit: pass",))
    adapter.apply(adapter.plan_update(path, update, sha256(path)))
    first = path.read_text(encoding="utf-8")
    assert json.loads(first)["unknown"] == {"keep": True}
    assert "用户计划" in first
    adapter.apply(adapter.plan_update(path, update, sha256(path)))
    assert path.read_text(encoding="utf-8") == first
```

- [ ] **Step 2: Run the JSON test to verify it fails**

Run:

```bash
python -m pytest tests/unit/test_json_document.py -q
```

Expected: import error for `JsonAdapter`.

- [ ] **Step 3: Implement the JSON adapter**

`src/spec_driven/documents/json.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from ..errors import DocumentConflictError
from ..models import DocumentUpdate, Module
from ..patches import DocumentPatch, apply_atomic, sha256
from .structured import apply_structured_update, parse_structured_modules


class JsonAdapter:
    name = "json"
    suffixes = frozenset({".json"})

    def _load(self, path: Path) -> dict[str, object]:
        root = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(root, dict):
            raise DocumentConflictError(f"JSON root must be an object: {path}")
        return root

    def parse_modules(self, path: Path) -> tuple[Module, ...]:
        return parse_structured_modules(self._load(path))

    def plan_update(
        self,
        path: Path,
        update: DocumentUpdate,
        expected_sha256: str,
    ) -> DocumentPatch:
        if sha256(path) != expected_sha256:
            raise DocumentConflictError(f"document hash is stale: {path}")
        root = self._load(path)
        apply_structured_update(root, update)
        replacement = json.dumps(root, ensure_ascii=False, indent=2) + "\n"
        return DocumentPatch(path, expected_sha256, replacement, f"update {update.module_id}")

    def apply(self, patch: DocumentPatch) -> None:
        apply_atomic(patch)
```

- [ ] **Step 4: Add JSON fixture files**

`fixtures/json-project/spec-driven.config.yaml`:

```yaml
schema_version: 1
spec:
  paths: [docs/spec.json]
plan:
  paths: [docs/plan.json]
tests:
  unit:
    command: python -m pytest tests/unit -q
  regression:
    command: python -m pytest -q
documents:
  adapters: [json]
```

`fixtures/json-project/docs/spec.json`:

```json
{
  "title": "产品规格",
  "owner": "platform",
  "spec_driven": {
    "active_module_id": "M1",
    "modules": [
      {
        "id": "M1",
        "order": 1,
        "title": "Core workflow",
        "goal": "Build the core workflow.",
        "status": "pending",
        "prerequisites": [],
        "acceptance": ["State transitions are validated."],
        "tests": ["unit", "regression"],
        "completed_points": [],
        "notes": [],
        "evidence": []
      },
      {
        "id": "M2",
        "order": 2,
        "title": "Host adapter",
        "goal": "Translate host events.",
        "status": "pending",
        "prerequisites": ["M1"],
        "acceptance": [],
        "tests": ["unit", "regression"],
        "completed_points": [],
        "notes": [],
        "evidence": []
      }
    ]
  }
}
```

`fixtures/json-project/docs/plan.json` mirrors `docs/spec.json` with `"title": "产品计划"`. Both documents carry the exact same two modules (`M1`/`M2`), fields, and `active_module_id: M1`; the top-level title differs so spec/plan stay distinct files. Every file ends with a newline and uses `ensure_ascii=False` Chinese prose.

- [ ] **Step 5: Run JSON tests and regression**

Run:

```bash
python -m pytest tests/unit/test_json_document.py tests/contract/test_structured_document_adapter.py -q
python -m pytest -q
```

Expected: all tests pass with deterministic non-ASCII output.

- [ ] **Step 6: Commit JSON support**

```bash
git add src/spec_driven/documents/json.py fixtures/json-project tests/unit/test_json_document.py
git commit -m "feat: add deterministic JSON documents"
```

---

> **Implementation notes (Task 4 complete):**
> - JSON output is `json.dumps(..., ensure_ascii=False, indent=2) + "\n"` — deterministic, Unicode preserved. Idempotence holds because re-encoding the already-updated doc is byte-stable.
> - Non-object root raises DocumentConflictError "JSON root must be an object" (message contains "object"/"mapping" — both tests and code reference this).
> - JSON fixtures carry `ensure_ascii=False` Chinese prose; any future re-formatting must keep `ensure_ascii=False` or round-trip tests will fail.

### Task 5: Wire format plugins into discovery and the engine

**Files:**
- Modify: `src/spec_driven/documents/__init__.py`
- Modify: `src/spec_driven/discovery.py`
- Modify: `src/spec_driven/engine.py`
- Create: `tests/e2e/test_structured_workflow.py` (consolidated parametrized E2E for both YAML and JSON)

**Interfaces:**
- `builtin_registry() -> DocumentRegistry` registers Markdown, YAML, and JSON exactly once.
- Discovery includes enabled adapter suffixes instead of hardcoding Markdown.
- `CoreEngine` resolves the adapter for each configured document and applies one shared `DocumentUpdate` to both spec and plan.

- [ ] **Step 1: Write failing end-to-end tests for both formats**

`tests/e2e/test_structured_workflow.py` (one parametrized file proving both YAML and JSON start, parse, and complete the full gated transaction):

```python
import shutil
from pathlib import Path

import pytest

from spec_driven.adapters.generic import GenericAdapter
from spec_driven.engine import CoreEngine
from spec_driven.models import Checkpoint, Event, TestEvidence

_PARAMS = [
    ("yaml-project", ".yaml"),
    ("json-project", ".json"),
]


@pytest.mark.parametrize("fixture,suffix", _PARAMS)
def test_structured_fixture_can_start_and_parse_modules(tmp_path: Path, fixture: str, suffix: str) -> None:
    root = tmp_path / "project"
    shutil.copytree(Path("fixtures") / fixture, root)
    snapshot = CoreEngine.from_project(root).start()
    assert snapshot.current_module_id == "M1"
    assert snapshot.module_states == {"M1": "pending", "M2": "pending"}
    assert snapshot.documents[0].path.endswith(suffix)
    assert snapshot.documents[1].path.endswith(suffix)


@pytest.mark.parametrize("fixture", ["yaml-project", "json-project"])
def test_structured_fixture_runs_full_gated_transaction(tmp_path: Path, fixture: str) -> None:
    root = tmp_path / "project"
    shutil.copytree(Path("fixtures") / fixture, root)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(Event("start-1", 1, "session-1", "module_started", "t0", "core", "agent", "M1", {}))
    engine.record_test("unit-1", TestEvidence("unit", "M1", "unit", ".", "t0", "t1", 0, None, "", 1))
    engine.record_test("reg-1", TestEvidence("regression", "M1", "regression", ".", "t0", "t1", 0, None, "", 1))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("done",), ("note",)))
    before = (root / "docs/plan.yaml" if "yaml" in fixture else root / "docs/plan.json").read_bytes()
    engine.confirm_next(
        GenericAdapter().normalize(
            {
                "event_id": "confirm-1",
                "schema_version": 1,
                "session_id": "session-1",
                "type": "next_module_confirmed",
                "occurred_at": "t2",
                "source": "generic",
                "actor": "user",
                "module_id": "M1",
                "payload": {"confirmation": "explicit_command"},
            }
        )
    )
    assert engine.status().current_module_id == "M2"
    assert engine.status().module_states["M1"] == "completed"
    after = (root / "docs/plan.yaml" if "yaml" in fixture else root / "docs/plan.json").read_bytes()
    assert after != before
```

- [ ] **Step 2: Run the end-to-end tests to verify they fail**

Run:

```bash
python -m pytest tests/e2e/test_structured_workflow.py -q
```

Expected: discovery or adapter-selection failure because the core is still Markdown-only.

- [ ] **Step 3: Register built-in plugins**

`src/spec_driven/documents/__init__.py`:

```python
from .json import JsonAdapter
from .markdown import MarkdownAdapter
from .registry import DocumentRegistry
from .yaml import YamlAdapter


def builtin_registry() -> DocumentRegistry:
    registry = DocumentRegistry()
    registry.register(MarkdownAdapter())
    registry.register(YamlAdapter())
    registry.register(JsonAdapter())
    return registry
```

- [ ] **Step 4: Replace hard-coded suffix and parser selection**

In `src/spec_driven/discovery.py`, replace the `*.md`-only scan with a registry-aware scan. The `registry` parameter is optional; when omitted it falls back to `builtin_registry()` so the core baseline's two-argument calls (engine `start`, CLI `doctor`) keep working while still honoring `config.document_adapters`:

```python
from .documents import builtin_registry
from .documents.registry import DocumentRegistry


def _scan(root: Path, kind: str, tokens: tuple[str, ...], suffixes: frozenset[str]) -> list[DocumentRef]:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and ".spec-driven" not in path.parts
        and any(token in path.name.lower() for token in tokens)
    )
    return [DocumentRef(kind, str(path.relative_to(root)), _sha256(path)) for path in paths]


def discover_documents(
    root: Path,
    config: ProjectConfig,
    registry: DocumentRegistry | None = None,
) -> tuple[DocumentRef, DocumentRef]:
    registry = registry or builtin_registry()
    suffixes = registry.enabled_suffixes(config.document_adapters)
    specs = _configured(root, config.spec_paths, "spec") if config.spec_paths else _scan(root, "spec", ("spec", "design"), suffixes)
    plans = _configured(root, config.plan_paths, "plan") if config.plan_paths else _scan(root, "plan", ("plan", "roadmap"), suffixes)
    if len(specs) != 1 or len(plans) != 1:
        raise DiscoveryAmbiguousError(
            f"expected one spec and one plan; found {len(specs)} spec(s), {len(plans)} plan(s)",
            remediation="set spec.paths and plan.paths in spec-driven.config.yaml",
        )
    return specs[0], plans[0]
```

`CoreEngine` switches from a hard-coded `MarkdownAdapter` to the registry: replace `self.adapter = MarkdownAdapter()` with `self.registry = builtin_registry()` in `__init__`. In `start`, resolve the plan adapter per path:

```python
plan_path = self.project_root / plan.path
adapter = self.registry.for_path(plan_path, self.config.document_adapters)
modules = adapter.parse_modules(plan_path)
```

In `confirm_next`, resolve spec and plan adapters separately and apply the same update through the one transaction:

```python
update = DocumentUpdate(
    module_id=current,
    status="completed",
    next_module_id=next_module_id,
    completed_points=checkpoint.completed_points,
    notes=checkpoint.notes,
    evidence_summary=(
        f"unit: exit {unit.exit_code}",
        f"regression: exit {regression.exit_code}",
    ),
)
patches = tuple(
    self.registry.for_path(self.project_root / ref.path, self.config.document_adapters)
    .plan_update(self.project_root / ref.path, update, sha256(self.project_root / ref.path))
    for ref in snapshot.documents
)
```

Synchronize the core `doctor` handler in `src/spec_driven/cli.py` so it no longer assumes Markdown:

```python
from .documents import builtin_registry


def doctor(project: str) -> dict[str, object]:
    root = Path(project)
    config = load_config(root)
    spec, plan = discover_documents(root, config)
    registry = builtin_registry()
    modules = registry.for_path(root / plan.path, config.document_adapters).parse_modules(root / plan.path)
    unit, regression = infer_test_commands(root, config)
    return {
        "status": "ok",
        "documents": {"spec": spec.path, "plan": plan.path},
        "modules": [module.module_id for module in modules],
        "tests": {"unit": unit, "regression": regression},
    }
```

The optional `registry` keeps every existing two-argument call in core Task 3 and Task 6 valid; no other call site changes.

- [ ] **Step 5: Run all adapter contracts and end-to-end tests**

Run:

```bash
python -m pytest tests/contract/test_document_adapter.py tests/contract/test_structured_document_adapter.py -q
python -m pytest tests/e2e/test_structured_workflow.py -q
python -m pytest -q
```

Expected: all document formats start, parse modules, preserve unknown content, and update through the same gate.

- [ ] **Step 6: Commit the format integration**

```bash
git add src/spec_driven/documents/__init__.py src/spec_driven/discovery.py src/spec_driven/engine.py tests/e2e/test_structured_workflow.py
git commit -m "feat: integrate structured document plugins"
```

## Structured adapter acceptance checklist

- [ ] Markdown contract remains green.
- [ ] YAML comments, anchors, key order, and quoting survive managed updates.
- [ ] JSON unknown fields and Unicode survive managed updates.
- [ ] Duplicate, missing, or non-contiguous modules are rejected.
- [ ] Disabled adapters cannot be selected by suffix alone.
- [ ] Stale hashes prevent both YAML and JSON overwrite.
- [ ] Both structured fixtures complete the same gated document transaction as Markdown.
