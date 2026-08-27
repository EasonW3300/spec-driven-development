# Codex Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give OpenAI Codex a safe, honest spec-driven workflow by reporting exactly which capabilities Codex lacks natively, installing prompt-level guidance plus desktop notifications, and routing every document mutation through the same explicit-command core gate the generic adapter uses.

**Architecture:** Codex exposes no hook/event stream equivalent to Claude Code's, so this adapter never pretends to observe Bash or intercept prompts natively. A capability probe reports native events and Bash observability as unavailable and the explicit CLI as the only confirmation/document path. The adapter packages an `AGENTS.md` instruction fragment and a notification settings fragment through the core baseline install primitives plus a tested AGENTS.md append helper, and the end-to-end proof drives the full gate through the public core CLI exactly as a scripted `codex exec` session would.

**Tech Stack:** Python 3.11+, standard `json`/`subprocess`/`shlex`, `tomlkit>=0.13,<0.14`, existing `spec_driven` core CLI, `pytest`.

## Global Constraints

- Requires completion of `docs/superpowers/plans/2026-08-26-spec-driven-core-baseline.md`; consumes the core CLI and `CoreEngine` exactly as defined there.
- Requires the core baseline install primitives (Task 7 of `2026-08-26-spec-driven-core-baseline.md`); this plan supplies `install/manifests/codex.json`, its settings fragment, and a tested AGENTS.md append helper.
- No fake capability: if Codex cannot natively observe an event, the report says `unavailable` and the plan relies on the explicit CLI.
- The adapter and its installed instructions never claim that natural language authorizes a document change.
- The `AGENTS.md` fragment teaches only the public CLI commands; it never instructs the agent to edit spec/plan directly.
- Settings merges preserve unknown Codex configuration and are covered by a round-trip test.
- Codex-specific file names, config keys, and command flags must be copied from current official documentation during implementation and locked by contract fixtures; no guessed key is permitted.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
src/spec_driven/adapters/
  codex.py
install/manifests/codex.json
adapters/codex/
  AGENTS.spec-driven.fragment.md
  notify.fragment.toml
  SKILL.md
docs/adapters/codex-capabilities.md
fixtures/codex/
  codex-version.txt
  config-with-notify.toml
  config-without-notify.toml
tests/contract/test_codex_contract.py
tests/unit/test_codex_adapter.py
tests/integration/test_codex_install.py
tests/e2e/test_codex_workflow.py
```

`codex.py` contains only pure capability, fragment-rendering, and AGENTS.md-append functions. Skill and notify-settings installation is delegated to the core `install.py`; the adapter never mutates spec/plan.

---

### Task 1: Lock the Codex capability report and contract fixtures

**Files:**
- Create: `src/spec_driven/adapters/codex.py`
- Create: `fixtures/codex/codex-version.txt`
- Create: `fixtures/codex/config-with-notify.toml`
- Create: `fixtures/codex/config-without-notify.toml`
- Create: `tests/contract/test_codex_contract.py`
- Modify: `src/spec_driven/capabilities.py`

**Interfaces:**
- `CodexCapabilities.detect(environment: Mapping[str, str], config_toml: str | None) -> CapabilityReport`.
- `parse_codex_config(content: str) -> dict[str, object]` returns the merged TOML as plain data.
- `explicit_workflow_capabilities() -> tuple[Capability, ...]` is the stable shared capability set.

- [ ] **Step 1: Save real contract fixtures from official documentation**

`fixtures/codex/codex-version.txt` records the exact `codex --version` output observed on the implementation machine, e.g.:

```text
codex-cli 0.144.6
```

`fixtures/codex/config-with-notify.toml`:

```toml
model = "gpt-5.1-codex-mini"

[notify]
background = true
```

`fixtures/codex/config-without-notify.toml`:

```toml
model = "gpt-5.1-codex-mini"
```

The implementer must verify the exact notify key shape (`notify = true` versus a `[notify]` table) against current official documentation and update these fixtures accordingly. The tests below only assert presence/absence of the parsed notify flag, so they are stable across the two documented shapes.

- [ ] **Step 2: Write failing contract tests**

```python
import json
from pathlib import Path

from spec_driven.adapters.codex import CodexCapabilities, parse_codex_config

FIXTURES = Path("fixtures/codex")


def test_detect_reports_native_events_unavailable() -> None:
    report = CodexCapabilities.detect(
        {"CODEX_HOME": "/tmp/codex-home"},
        (FIXTURES / "config-with-notify.toml").read_text(encoding="utf-8"),
    )
    capabilities = {item.name: item.status for item in report.capabilities}
    assert capabilities["session_events"] == "unavailable"
    assert capabilities["bash_exit_status"] == "degraded"
    assert capabilities["explicit_confirmation"] == "available"
    assert capabilities["document_update"] == "available"
    assert capabilities["notifications"] == "available"
    assert report.host == "codex"


def test_parse_codex_config_detects_notify_and_preserves_model() -> None:
    parsed = parse_codex_config((FIXTURES / "config-with-notify.toml").read_text(encoding="utf-8"))
    assert parsed["model"] == "gpt-5.1-codex-mini"
    assert parsed.get("notify") is not None


def test_detect_degrades_notifications_when_config_is_absent() -> None:
    report = CodexCapabilities.detect({"CODEX_HOME": "/tmp/nonexistent"}, None)
    capabilities = {item.name: item.status for item in report.capabilities}
    assert capabilities["notifications"] == "degraded"
```

- [ ] **Step 3: Run the contract tests to verify they fail**

Run:

```bash
python -m pytest tests/contract/test_codex_contract.py -q
```

Expected: import errors for `codex` and `parse_codex_config`.

- [ ] **Step 4: Implement the probe and pure TOML parsing**

`src/spec_driven/adapters/codex.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import tomlkit

from ..capabilities import Capability, CapabilityReport


def parse_codex_config(content: str) -> dict[str, object]:
    document = tomlkit.parse(content)
    return {key: value for key, value in document.items()}


def explicit_workflow_capabilities() -> tuple[Capability, ...]:
    return (
        Capability("session_events", "unavailable", "none", "Codex exposes no session event stream", "use explicit CLI"),
        Capability("bash_exit_status", "degraded", "agent shell", "tests run inside Codex are not host-observable", "record exit codes with the core CLI"),
        Capability("explicit_confirmation", "available", "core CLI confirm-next", "only the literal command authorizes", None),
        Capability("document_update", "available", "core CLI transaction", "the core gate controls writes", None),
        Capability("notifications", "degraded", "config notify", "desktop notification when awaiting confirmation", "enable [notify] in config.toml"),
    )


class CodexCapabilities:
    @staticmethod
    def detect(environment: Mapping[str, str], config_toml: str | None) -> CapabilityReport:
        parsed = parse_codex_config(config_toml) if config_toml else {}
        notify = bool(parsed.get("notify"))
        capabilities = list(explicit_workflow_capabilities())
        capabilities[4] = Capability(
            "notifications",
            "available" if notify else "degraded",
            "config notify",
            "desktop notification when awaiting confirmation",
            None if notify else "enable [notify] in config.toml",
        )
        return CapabilityReport(
            schema_version=1,
            host="codex",
            adapter_version="0.1.0",
            capabilities=tuple(capabilities),
        )
```

The invariant is that the report never marks `session_events` or `bash_exit_status` as `available`; those guarantees are physically absent in Codex and the report must say so.

- [ ] **Step 5: Run contract tests and the full suite**

Run:

```bash
python -m pytest tests/contract/test_codex_contract.py -q
python -m pytest -q
```

Expected: contract fixtures pass and all core tests remain green.

- [ ] **Step 6: Commit the capability probe**

```bash
git add src/spec_driven/adapters/codex.py src/spec_driven/capabilities.py tests/contract/test_codex_contract.py fixtures/codex
git commit -m "feat: add Codex capability report"
```

---

### Task 2: Render and install the Codex instruction and notification fragments

**Files:**
- Create: `adapters/codex/AGENTS.spec-driven.fragment.md`
- Create: `adapters/codex/notify.fragment.toml`
- Create: `adapters/codex/SKILL.md`
- Create: `install/manifests/codex.json`
- Create: `docs/adapters/codex-capabilities.md`
- Create: `tests/unit/test_codex_adapter.py`
- Create: `tests/integration/test_codex_install.py`

**Interfaces:**
- `render_agenda_fragment(confirmation_command: str) -> str` returns the complete AGENTS.md instruction block.
- `codex_settings_fragment(notify: bool) -> dict[str, object]` returns `{"notify": {"background": True}}` or `{}`.
- `append_agents_fragment(project_root: Path, fragment_text: str) -> None` appends the instruction block to `<project>/AGENTS.md` inside a stable marker, creating the file if needed and never duplicating on re-run.
- Installation uses the core baseline `copy` and `merge_toml` operations and returns a rollback receipt.

- [ ] **Step 1: Write failing render and merge tests**

```python
from pathlib import Path

from spec_driven.adapters.codex import append_agents_fragment, codex_settings_fragment, render_agenda_fragment
from spec_driven.capabilities import HostManifest
from spec_driven.install import apply_install, plan_install, rollback_install


def test_render_agenda_fragment_requires_literal_command() -> None:
    fragment = render_agenda_fragment("confirm-next")
    assert "confirm-next" in fragment
    assert "继续" in fragment or "自然语言" in fragment


def test_codex_settings_fragment_is_idempotent_merge(tmp_path: Path) -> None:
    package = tmp_path / "package"
    (package / "adapters" / "codex").mkdir(parents=True)
    (package / "adapters" / "codex" / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    config = home / ".codex" / "config.toml"
    config.write_text('model = "keep"\n[notify]\nbackground = false\n', encoding="utf-8")
    manifest = HostManifest(
        1, "codex", "spec_driven.adapters.codex", "adapters/codex",
        ".codex/skills/spec-driven-development", ".codex/config.toml", codex_settings_fragment(True),
    )
    plan = plan_install(manifest, package, home)
    receipt = apply_install(plan, home / ".spec-driven-install-backups")
    merged = config.read_text(encoding="utf-8")
    assert 'model = "keep"' in merged
    assert "background = true" in merged
    assert (home / ".codex/skills/spec-driven-development" / "SKILL.md").is_file()
    rollback_install(receipt)
    assert config.read_text(encoding="utf-8") == 'model = "keep"\n[notify]\nbackground = false\n'


def test_append_agents_fragment_is_idempotent_and_preserves_existing(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# Project\n", encoding="utf-8")
    append_agents_fragment(root, "## Spec-Driven workflow\n\n- confirm-next is the only authorization.\n")
    append_agents_fragment(root, "## Spec-Driven workflow\n\n- confirm-next is the only authorization.\n")
    content = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert content.count("## Spec-Driven workflow") == 1
    assert content.startswith("# Project\n")
```
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_codex_adapter.py tests/integration/test_codex_install.py -q
```

Expected: import errors for `codex` helpers and missing manifest/fragments.

- [ ] **Step 3: Write the complete instruction fragment**

`adapters/codex/AGENTS.spec-driven.fragment.md`:

```markdown
## Spec-Driven Development workflow

This project follows spec-driven development. Follow every step; never skip a test gate.

1. When the user starts the workflow, run `spec-driven start --project <root>`.
2. If discovery is ambiguous (multiple spec/plan candidates or unclear modules/tests), show the candidates and wait for the user to choose; never guess.
3. Start the current module by submitting a `module_started` event JSON to `spec-driven start-module --input -`.
4. Implement only the current module's MVP.
5. Run the configured unit command and the full regression command, one after the other.
6. Submit each real exit code and a short output summary through `spec-driven record-test --input -`.
7. A nonzero exit code means the module stays in `testing`. Fix the failure and rerun BOTH commands.
8. After both gates pass, submit a checkpoint through `spec-driven checkpoint --input -` containing completed points and notes for later modules.
9. Ask the user to type exactly `confirm-next`. The literal command is the ONLY authorization to advance.
10. Replies such as "继续" or "可以" are not authorization. Repeat the exact-command request; do not edit spec or plan.
11. When the user types the exact command, run `spec-driven confirm-next --input -`.
12. Run `spec-driven status` after each transition and `spec-driven recover` after any interruption.
```

`adapters/codex/SKILL.md` frontmatter plus the same twelve steps, written as a skill the agent can load on demand.

`adapters/codex/notify.fragment.toml`:

```toml
[notify]
background = true
```

- [ ] **Step 4: Implement the pure renderers**

`src/spec_driven/adapters/codex.py` continues:

```python
def render_agenda_fragment(confirmation_command: str) -> str:
    return (
        "## Spec-Driven Development workflow\n\n"
        "This project follows spec-driven development. Follow every step; never skip a test gate.\n\n"
        "1. When the user starts the workflow, run `spec-driven start --project <root>`.\n"
        "2. If discovery is ambiguous, show the candidates and wait for the user to choose; never guess.\n"
        "3. Start the current module by submitting a `module_started` event JSON to `spec-driven start-module --input -`.\n"
        "4. Implement only the current module's MVP.\n"
        "5. Run the configured unit command and the full regression command, one after the other.\n"
        "6. Submit each real exit code and a short output summary through `spec-driven record-test --input -`.\n"
        "7. A nonzero exit code means the module stays in `testing`. Fix the failure and rerun BOTH commands.\n"
        "8. After both gates pass, submit a checkpoint through `spec-driven checkpoint --input -` with completed points and later-module notes.\n"
        f"9. Ask the user to type exactly `{confirmation_command}`. The literal command is the ONLY authorization to advance.\n"
        '10. Replies such as "继续" or "可以" are not authorization. Repeat the exact-command request; do not edit spec or plan.\n'
        f"11. When the user types the exact command, run `spec-driven {confirmation_command} --input -`.\n"
        "12. Run `spec-driven status` after each transition and `spec-driven recover` after any interruption.\n"
    )


def codex_settings_fragment(notify: bool) -> dict[str, object]:
    return {"notify": {"background": True}} if notify else {}


AGENTS_MARKER = "<!-- spec-driven:codex-instructions -->"


def append_agents_fragment(project_root: Path, fragment_text: str) -> None:
    """Append the instruction block to AGENTS.md inside a stable marker.

    Re-running is a no-op (idempotent), existing content before the marker is
    preserved, and the file is created when missing.
    """
    agents = project_root / "AGENTS.md"
    existing = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if AGENTS_MARKER in existing:
        return
    block = f"{AGENTS_MARKER}\n{fragment_text.strip()}\n{AGENTS_MARKER}\n"
    agents.write_text((existing.rstrip() + "\n\n" + block) if existing.strip() else block, encoding="utf-8")
```
```

- [ ] **Step 5: Add the Codex host manifest**

`install/manifests/codex.json`:

```json
{
  "schema_version": 1,
  "host": "codex",
  "adapter_module": "spec_driven.adapters.codex",
  "skill_source": "adapters/codex",
  "skill_target": ".codex/skills/spec-driven-development",
  "settings_target": ".codex/config.toml",
  "settings_fragment": {
    "notify": {
      "background": true
    }
  }
}
```

Verify `plan_install` maps `settings_target` `.codex/config.toml` to a TOML merge (suffix `.toml`) and `skill_source` `adapters/codex` to a directory copy into `.codex/skills/spec-driven-development`. Add a `merge_toml` round-trip test for this exact fragment in `tests/integration/test_codex_install.py` that also runs `rollback_install` and asserts byte-equivalent restoration, plus a test that `append_agents_fragment` wires the rendered `AGENTS.spec-driven.fragment.md` content into a fresh project's `AGENTS.md` exactly once.

- [ ] **Step 6: Write capability documentation**

`docs/adapters/codex-capabilities.md` records the documentation/version date and a table with rows: session lifecycle, Bash success, Bash failure, explicit confirmation, document update, notifications, and natural-language confirmation. For each row state whether the mechanism is native, the exact config/CLI used, the guarantee, and the generic fallback. The table must match `explicit_workflow_capabilities()` statuses exactly.

- [ ] **Step 7: Run adapter tests and the full regression**

Run:

```bash
python -m pytest tests/unit/test_codex_adapter.py tests/integration/test_codex_install.py tests/contract/test_codex_contract.py -q
python -m pytest -q
```

Expected: the notify fragment merges without losing existing keys, the skill is copied, the AGENTS.md fragment appends exactly once, rollback is byte-equivalent, and the capability report is stable.

- [ ] **Step 8: Commit the Codex packaging**

```bash
git add adapters/codex install/manifests/codex.json docs/adapters/codex-capabilities.md src/spec_driven/adapters/codex.py tests/unit/test_codex_adapter.py tests/integration/test_codex_install.py
git commit -m "feat: install Codex workflow instructions"
```

---

### Task 3: Prove the explicit-CLI gate end to end on a Codex-shaped project

**Files:**
- Create: `tests/e2e/test_codex_workflow.py`

**Interfaces:**
- The test drives the full gate through the public CLI the way a scripted `codex exec` session would: `start`, `start-module`, `record-test`, `checkpoint`, `confirm-next`, `status`, `recover`.
- It asserts that a natural-language event is rejected before any document write.

- [ ] **Step 1: Write the complete end-to-end proof**

```python
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from spec_driven.adapters.generic import GenericAdapter
from spec_driven.errors import InvalidEventError


def _run(root: Path, subcommand: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    result = subprocess.run(
        ["spec-driven", "--project", str(root), subcommand],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{subcommand} failed: {result.stdout} {result.stderr}"
    return json.loads(result.stdout)


def _event(event_id: str, session_id: str, event_type: str, actor: str = "agent") -> dict[str, object]:
    return {
        "event_id": event_id,
        "schema_version": 1,
        "session_id": session_id,
        "type": event_type,
        "occurred_at": "2026-08-26T00:00:00Z",
        "source": "generic",
        "actor": actor,
        "module_id": "M1",
        "payload": {"confirmation": "explicit_command"} if event_type == "next_module_confirmed" else {},
    }


def _evidence(kind: str, code: int) -> dict[str, object]:
    return {
        "event_id": f"{kind}-{code}",
        "evidence": {
            "kind": kind,
            "module_id": "M1",
            "command": f"python -m pytest {'tests/unit -q' if kind == 'unit' else '-q'}",
            "working_directory": ".",
            "started_at": "2026-08-26T00:00:00Z",
            "finished_at": "2026-08-26T00:01:00Z",
            "exit_code": code,
            "output_path": None,
            "output_summary": "summary",
            "attempt": 1,
        },
    }


def _checkpoint(session_id: str) -> dict[str, object]:
    return {
        "event_id": "cp-event",
        "checkpoint": {
            "checkpoint_id": "cp1",
            "module_id": "M1",
            "completed_points": ["MVP works"],
            "notes": ["reuse API"],
        },
    }


def test_codex_explicit_cli_gate_completes_only_after_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    started = _run(root, "start")
    session_id = started["session_id"]
    assert started["current_module_id"] == "M1"

    _run(root, "start-module", _event("start-1", session_id, "module_started"))

    _run(root, "record-test", _evidence("unit", 1))
    assert _run(root, "status")["module_states"]["M1"] == "testing"

    _run(root, "record-test", _evidence("unit", 0))
    _run(root, "record-test", _evidence("regression", 0))
    _run(root, "checkpoint", _checkpoint(session_id))
    assert _run(root, "status")["module_states"]["M1"] == "awaiting_confirmation"

    confirmation = _event("confirm-1", session_id, "next_module_confirmed", actor="user")
    first = _run(root, "confirm-next", confirmation)
    second = _run(root, "confirm-next", confirmation)
    assert first == second
    assert first["current_module_id"] == "M2"
    for relative in ("docs/specs/product.md", "docs/plans/product-plan.md"):
        content = (root / relative).read_text(encoding="utf-8")
        assert content.count("Status: completed") == 1

    updated = [p for p in (root / ".spec-driven" / "events").glob("*.json") if "documents-updated" in p.name]
    assert len(updated) == 1


def test_natural_language_confirmation_is_rejected_before_write(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    session_id = _run(root, "start")["session_id"]
    before_spec = (root / "docs/specs/product.md").read_bytes()
    before_plan = (root / "docs/plans/product-plan.md").read_bytes()
    with pytest.raises(InvalidEventError):
        GenericAdapter().normalize({
            "event_id": "e1",
            "schema_version": 1,
            "session_id": session_id,
            "type": "next_module_confirmed",
            "occurred_at": "t",
            "actor": "user",
            "module_id": "M1",
            "payload": {"confirmation": "继续"},
        })
    assert (root / "docs/specs/product.md").read_bytes() == before_spec
    assert (root / "docs/plans/product-plan.md").read_bytes() == before_plan

- [ ] **Step 3: Run the end-to-end test to verify it passes**

Run:

```bash
python -m pytest tests/e2e/test_codex_workflow.py -q
python -m pytest -q
```

Expected: the complete explicit-CLI gate passes offline on the Codex-shaped fixture and the natural-language path is rejected with no document change.

- [ ] **Step 4: Commit the end-to-end proof**

```bash
git add tests/e2e/test_codex_workflow.py
git commit -m "test: prove Codex explicit-CLI gate"
```

## Codex acceptance checklist

- [ ] The capability report marks native session events and Bash observability as unavailable; no fake guarantee is reported.
- [ ] The `AGENTS.md` fragment and skill teach only the public CLI and never authorize natural language.
- [ ] Notification settings merge idempotently and roll back byte-for-byte.
- [ ] The full gate (start → start-module → record-test ×2 → checkpoint → confirm-next) completes through the explicit CLI.
- [ ] Repeating a confirmation is idempotent and produces exactly one document update.
- [ ] A natural-language confirmation is rejected before any write.
- [ ] Every event and state file stays under `.spec-driven/`.
