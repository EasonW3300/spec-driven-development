# Claude Code Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the core engine to Claude Code’s supported hook lifecycle so real Bash test results and an explicit `confirm-next` user submission produce validated events and document updates without prompt-only enforcement.

**Architecture:** A thin adapter consists of a capability probe, pure event normalizers, and one hook entrypoint that reads Claude Code’s JSON stdin and writes the host’s documented JSON decision/context response. `PostToolUse`/failure events record Bash evidence; `UserPromptSubmit` matches only the exact confirmation command and delegates the transaction to the core CLI. All hook behavior is fixture-tested and the generated settings fragment is installed only after capability validation.

**Tech Stack:** Python 3.11+, standard `json`/`re`/`subprocess`, existing `spec_driven` event/engine interfaces, Claude Code hook settings JSON, `pytest`.

## Global Constraints

- Requires `2026-08-26-spec-driven-core-baseline.md`.
- The adapter never parses arbitrary natural-language confirmation as authorization.
- Only an exact configured command `confirm-next` with the current session/module context can create `next_module_confirmed`.
- Bash evidence is accepted only from the host hook payload’s actual tool response/exit status; agent-reported “passed” text is insufficient.
- Hook failures fail closed for confirmation and emit a diagnostic context; they do not silently update documents.
- Settings merge preserves unrelated user keys and is covered by an installation round-trip test.
- Exact hook names, matcher syntax, input fields, and output decision fields must be copied from the current Claude Code documentation during implementation and locked by contract fixtures; no guessed field is permitted.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
src/spec_driven/adapters/claude_code.py
src/spec_driven/adapters/claude_code_hook.py
src/spec_driven/adapters/__init__.py
docs/adapters/claude-code-capabilities.md
install/manifests/claude-code.json
adapters/claude-code/settings.fragment.json
tests/contract/test_claude_code_contract.py
tests/unit/test_claude_code_adapter.py
tests/integration/test_claude_code_hooks.py
fixtures/claude-code/
  session-start.json
  bash-post-tool-use.json
  bash-post-tool-use-failure.json
  confirmation-prompt.json
  natural-language-prompt.json
  settings.json
```

`claude_code.py` contains pure capability and normalization functions. `claude_code_hook.py` is the only process entrypoint and contains no state policy beyond dispatching to the core CLI. The settings fragment is generated from the verified contract and is not hand-copied into a user settings file by the hook itself.

---

### Task 1: Lock the Claude Code hook contract and capability report

**Files:**
- Create: `src/spec_driven/adapters/claude_code.py`
- Create: `tests/contract/test_claude_code_contract.py`
- Create: `fixtures/claude-code/session-start.json`
- Create: `fixtures/claude-code/bash-post-tool-use.json`
- Create: `fixtures/claude-code/bash-post-tool-use-failure.json`
- Create: `fixtures/claude-code/confirmation-prompt.json`
- Create: `fixtures/claude-code/natural-language-prompt.json`
- Modify: `src/spec_driven/capabilities.py`

**Interfaces:**
- `ClaudeCodeCapabilities.detect(environment: Mapping[str, str], settings: Mapping[str, object]) -> CapabilityReport`.
- `normalize_session_start(payload: Mapping[str, object]) -> Event`.
- `normalize_bash_result(payload: Mapping[str, object], success: bool) -> TestEvidence | None`.
- `parse_explicit_confirmation(prompt: str, command: str) -> bool`.
- `normalize_confirmation(payload: Mapping[str, object], command: str) -> Event | None`.

- [ ] **Step 1: Save real contract fixtures from the host documentation**

The implementer must use the currently installed/documented Claude Code hook schemas and save one minimal valid payload per listed fixture. Each fixture must retain the host event discriminator and the fields used by the normalizer. Do not invent a synthetic field name; if the host payload changes, update the adapter and fixture together and record the version in `docs/adapters/claude-code-capabilities.md`.

- [ ] **Step 2: Write failing contract tests**

```python
import json
from pathlib import Path

from spec_driven.adapters.claude_code import (
    normalize_bash_result,
    normalize_confirmation,
    normalize_session_start,
    parse_explicit_confirmation,
)


FIXTURES = Path("fixtures/claude-code")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_session_start_normalizes_to_versioned_event() -> None:
    event = normalize_session_start(_load("session-start.json"))
    assert event.type == "session_started"
    assert event.schema_version == 1
    assert event.session_id


def test_successful_bash_hook_uses_actual_exit_code() -> None:
    evidence = normalize_bash_result(_load("bash-post-tool-use.json"), success=True)
    assert evidence is not None
    assert evidence.exit_code == 0
    assert evidence.command


def test_failed_bash_hook_preserves_nonzero_exit_code() -> None:
    evidence = normalize_bash_result(_load("bash-post-tool-use-failure.json"), success=False)
    assert evidence is not None
    assert evidence.exit_code != 0


def test_only_exact_confirmation_command_is_accepted() -> None:
    assert parse_explicit_confirmation("confirm-next", "confirm-next") is True
    assert parse_explicit_confirmation("confirm-next --extra", "confirm-next") is False
    assert parse_explicit_confirmation("继续下一个模块", "confirm-next") is False
    assert parse_explicit_confirmation("confirm-next", "advance") is False


def test_natural_language_prompt_does_not_create_event() -> None:
    assert normalize_confirmation(_load("natural-language-prompt.json"), "confirm-next") is None
```

- [ ] **Step 3: Run the contract tests to verify they fail**

Run:

```bash
python -m pytest tests/contract/test_claude_code_contract.py -q
```

Expected: import errors for the adapter functions.

- [ ] **Step 4: Implement normalization with explicit field validation**

`src/spec_driven/adapters/claude_code.py`:

```python
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from ..capabilities import Capability, CapabilityReport
from ..errors import InvalidEventError
from ..models import Event, TestEvidence


class ClaudeCodeCapabilities:
    @staticmethod
    def detect(environment: Mapping[str, str], settings: Mapping[str, object]) -> CapabilityReport:
        hook_input = environment.get("CLAUDE_CODE_HOOK_INPUT", "")
        configured = bool(settings.get("hooks"))
        status = "available" if hook_input and configured else "degraded"
        return CapabilityReport(
            schema_version=1,
            host="claude-code",
            adapter_version="0.1.0",
            capabilities=(
                Capability("session_events", status, "Claude Code hooks", "session lifecycle is observable", "install SessionStart hook"),
                Capability("bash_exit_status", status, "PostToolUse/PostToolUseFailure", "real Bash result can be recorded", "install Bash matchers"),
                Capability("explicit_confirmation", status, "UserPromptSubmit exact command", "only confirm-next can authorize", "use the generic CLI command"),
                Capability("document_update", status, "local core CLI", "core gate controls writes", "run spec-driven doctor"),
            ),
        )


def _required(payload: Mapping[str, object], *keys: str) -> list[object]:
    values = [payload.get(key) for key in keys]
    if any(value in (None, "") for value in values):
        raise InvalidEventError(f"Claude Code hook payload is missing: {keys}")
    return values


def normalize_session_start(payload: Mapping[str, object]) -> Event:
    session_id, occurred_at = _required(payload, "session_id", "timestamp")
    return Event(
        event_id=f"{session_id}:session_started",
        schema_version=1,
        session_id=str(session_id),
        type="session_started",
        occurred_at=str(occurred_at),
        source="claude-code",
        actor="host",
        module_id=None,
        payload={"cwd": str(payload.get("cwd", ""))},
    )


def normalize_bash_result(payload: Mapping[str, object], success: bool) -> TestEvidence | None:
    session_id, command, module_id, started_at, finished_at = _required(
        payload, "session_id", "command", "module_id", "started_at", "finished_at"
    )
    exit_code = int(payload.get("exit_code", 0 if success else 1))
    kind = str(payload.get("test_kind", ""))
    if kind not in {"unit", "regression"}:
        return None
    return TestEvidence(
        kind=kind,
        module_id=str(module_id),
        command=str(command),
        working_directory=str(payload.get("cwd", ".")),
        started_at=str(started_at),
        finished_at=str(finished_at),
        exit_code=exit_code,
        output_path=str(payload["output_path"]) if payload.get("output_path") else None,
        output_summary=str(payload.get("output_summary", "")),
        attempt=int(payload.get("attempt", 1)),
    )


def parse_explicit_confirmation(prompt: str, command: str) -> bool:
    return bool(re.fullmatch(re.escape(command), prompt.strip()))


def normalize_confirmation(payload: Mapping[str, object], command: str) -> Event | None:
    prompt = str(payload.get("prompt", ""))
    if not parse_explicit_confirmation(prompt, command):
        return None
    session_id, module_id, occurred_at = _required(payload, "session_id", "module_id", "timestamp")
    return Event(
        event_id=f"{session_id}:confirm:{module_id}:{occurred_at}",
        schema_version=1,
        session_id=str(session_id),
        type="next_module_confirmed",
        occurred_at=str(occurred_at),
        source="claude-code",
        actor="user",
        module_id=str(module_id),
        payload={"confirmation": "explicit_command"},
    )
```

The implementer must adapt the extraction keys to the verified host fixture. The invariant is that `normalize_bash_result` rejects missing real identity fields and never reads a prose “passed” marker as an exit code.

- [ ] **Step 5: Run contract tests and the full suite**

Run:

```bash
python -m pytest tests/contract/test_claude_code_contract.py -q
python -m pytest -q
```

Expected: contract fixtures pass and all core tests remain green.

- [ ] **Step 6: Commit the contract adapter**

```bash
git add src/spec_driven/adapters/claude_code.py src/spec_driven/capabilities.py tests/contract/test_claude_code_contract.py fixtures/claude-code
git commit -m "feat: add Claude Code event normalization"
```

---

### Task 2: Implement the hook dispatcher and fail-closed confirmation path

**Files:**
- Create: `src/spec_driven/adapters/claude_code_hook.py`
- Create: `tests/unit/test_claude_code_adapter.py`
- Create: `tests/integration/test_claude_code_hooks.py`

**Interfaces:**
- `dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult`.
- `HookResult(exit_code: int, response: Mapping[str, object], emitted: tuple[Event | TestEvidence, ...])`.
- `main(argv: list[str] | None = None) -> int` reads one JSON object from stdin and writes one JSON response.

- [ ] **Step 1: Write tests for dispatch decisions**

```python
import json
from pathlib import Path

from spec_driven.adapters.claude_code_hook import dispatch


def test_natural_language_is_non_mutating_context(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s1",
        "timestamp": "2026-08-26T00:00:00Z",
        "module_id": "M1",
        "prompt": "可以，继续",
    }
    result = dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.exit_code == 0
    assert result.emitted == ()
    assert "confirm-next" in str(result.response)


def test_confirmation_dispatches_core_event_only_for_exact_command(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s1",
        "timestamp": "2026-08-26T00:00:00Z",
        "module_id": "M1",
        "prompt": "confirm-next",
    }
    result = dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.emitted[0].type == "next_module_confirmed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_claude_code_adapter.py tests/integration/test_claude_code_hooks.py -q
```

Expected: import error for `claude_code_hook`.

- [ ] **Step 3: Implement event dispatch and host response mapping**

`src/spec_driven/adapters/claude_code_hook.py`:

```python
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..errors import SpecDrivenError
from ..models import Event, TestEvidence
from .claude_code import normalize_bash_result, normalize_confirmation, normalize_session_start


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    response: Mapping[str, object]
    emitted: tuple[Event | TestEvidence, ...]


def dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult:
    del project_root
    hook_name = str(payload.get("hook_event_name", ""))
    command = env.get("SPECDRIVEN_CONFIRMATION_COMMAND", "confirm-next")
    try:
        if hook_name == "SessionStart":
            emitted = (normalize_session_start(payload),)
            return HookResult(0, {"continue": True}, emitted)
        if hook_name in {"PostToolUse", "PostToolUseFailure"} and payload.get("tool_name") == "Bash":
            evidence = normalize_bash_result(payload, hook_name == "PostToolUse")
            return HookResult(0, {"continue": True}, (evidence,) if evidence else ())
        if hook_name == "UserPromptSubmit":
            confirmation = normalize_confirmation(payload, command)
            if confirmation is None:
                return HookResult(0, {
                    "continue": True,
                    "systemMessage": f"Spec-driven workflow requires explicit `{command}` after both test gates pass.",
                }, ())
            return HookResult(0, {"continue": True}, (confirmation,))
        return HookResult(0, {"continue": True}, ())
    except SpecDrivenError as error:
        return HookResult(2, {"continue": False, "stopReason": f"{error.code}: {error}"}, ())


def main(argv: list[str] | None = None) -> int:
    del argv
    payload = json.load(sys.stdin)
    result = dispatch(payload, Path.cwd(), os.environ)
    for event in result.emitted:
        if isinstance(event, Event):
            subprocess.run(["spec-driven", "ingest-event"], input=json.dumps(event.__dict__), text=True, check=False)
        else:
            subprocess.run(["spec-driven", "record-test"], input=json.dumps(event.__dict__), text=True, check=False)
    json.dump(result.response, sys.stdout)
    sys.stdout.write("\n")
    return result.exit_code
```

Replace the illustrative subprocess calls with a shared `emit_to_core` function that invokes the installed core CLI with a JSON stdin payload, captures its exit code, and turns a rejected confirmation into the host’s documented blocking response. The hook process must never write spec/plan itself.

- [ ] **Step 4: Add failure-path tests**

Cover: malformed JSON, unknown hook event, missing module ID, gate rejection from the core, and core CLI unavailable. Each case must return a stable nonzero exit code or a documented warning response and must leave the documents byte-identical.

- [ ] **Step 5: Run integration tests and the full suite**

Run:

```bash
python -m pytest tests/unit/test_claude_code_adapter.py tests/integration/test_claude_code_hooks.py -q
python -m pytest -q
```

Expected: exact confirmation reaches the core, natural language only receives context, and all failure paths fail closed.

- [ ] **Step 6: Commit the dispatcher**

```bash
git add src/spec_driven/adapters/claude_code_hook.py tests/unit/test_claude_code_adapter.py tests/integration/test_claude_code_hooks.py
git commit -m "feat: add fail-closed Claude Code hook dispatcher"
```

---

### Task 3: Register and install Claude Code hooks safely

**Files:**
- Create: `adapters/claude-code/settings.fragment.json`
- Create: `docs/adapters/claude-code-capabilities.md`
- Modify: `install/manifests/claude-code.json`
- Create: `tests/integration/test_claude_code_install.py`
- Modify: `src/spec_driven/install.py`

**Interfaces:**
- `claude_code_settings_fragment(hook_command: str) -> dict[str, object]` returns the verified hook registrations.
- The fragment contains separate registrations for session start, Bash success/failure, and user prompt submission, with exact matchers from the contract fixture.
- Installation uses the productization `merge_json` operation and returns a rollback receipt.

- [ ] **Step 1: Write a settings merge test**

```python
import json
from pathlib import Path

from spec_driven.install import apply_install, plan_install, rollback_install
from spec_driven.capabilities import HostManifest


def test_claude_settings_merge_keeps_existing_hooks(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "hooks": {"Notification": [{"command": "keep"}]}}), encoding="utf-8")
    manifest = HostManifest(1, "claude-code", "spec_driven.adapters.claude_code", "skills/spec-driven-development", ".claude/settings.json", {"hooks": {"UserPromptSubmit": [{"command": "spec-driven"}]}})
    plan = plan_install(manifest, tmp_path, tmp_path)
    receipt = apply_install(plan, tmp_path / ".backup")
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert merged["hooks"]["Notification"] == [{"command": "keep"}]
    rollback_install(receipt)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/integration/test_claude_code_install.py -q
```

Expected: missing settings fragment or installation integration failure.

- [ ] **Step 3: Generate the verified settings fragment**

The fragment must use the exact currently documented Claude Code settings shape. It must invoke a stable installed executable, pass the hook event JSON through stdin, set the project root from the host payload, and use no shell interpolation of untrusted prompt text. Store the generated output in `adapters/claude-code/settings.fragment.json` and make the manifest point to it.

- [ ] **Step 4: Add capability documentation**

`docs/adapters/claude-code-capabilities.md` records the documentation/version date, each hook event used, matcher, fields consumed, output decision fields, whether the hook can block, and the generic fallback when unavailable. Include a table with these rows: session lifecycle, Bash success, Bash failure, explicit confirmation, document update, and natural-language confirmation.

- [ ] **Step 5: Update installer to reject stale or duplicate registrations**

Make the merge operation identify registrations by `(event, matcher, command)`; rerunning install must not append a duplicate. It must preserve all unrelated hooks, write a backup before mutation, and return a receipt that restores the exact previous JSON.

- [ ] **Step 6: Run adapter installation tests and full regression**

Run:

```bash
python -m pytest tests/integration/test_claude_code_install.py tests/contract/test_claude_code_contract.py -q
python -m pytest -q
```

Expected: settings are merged idempotently, rollback is byte-equivalent, and the manifest contains a non-empty verified fragment.

- [ ] **Step 7: Commit Claude Code registration**

```bash
git add adapters/claude-code/settings.fragment.json docs/adapters/claude-code-capabilities.md install/manifests/claude-code.json src/spec_driven/install.py tests/integration/test_claude_code_install.py
git commit -m "feat: register Claude Code workflow hooks"
```

---

### Task 4: Prove the real end-to-end Claude Code gate

**Files:**
- Modify: `tests/e2e/test_claude_code_workflow.py`
- Create: `tests/e2e/test_claude_code_workflow.py`
- Modify: `fixtures/markdown-project/docs/specs/product.md`
- Modify: `fixtures/markdown-project/docs/plans/product-plan.md`

**Interfaces:**
- The E2E test drives hook fixtures through the adapter and inspects the core state, event files, and both documents.

- [ ] **Step 1: Write the E2E scenario**

```python
from pathlib import Path

from spec_driven.adapters.claude_code_hook import dispatch


def test_claude_code_hook_flow_updates_documents_only_after_confirmation() -> None:
    root = Path("fixtures/markdown-project")
    before_spec = (root / "docs/specs/product.md").read_bytes()
    before_plan = (root / "docs/plans/product-plan.md").read_bytes()
    natural = dispatch({"hook_event_name": "UserPromptSubmit", "prompt": "可以", "session_id": "s", "module_id": "M1", "timestamp": "t"}, root, {})
    assert natural.emitted == ()
    assert (root / "docs/specs/product.md").read_bytes() == before_spec
    assert (root / "docs/plans/product-plan.md").read_bytes() == before_plan
    # Drive both real passing test fixtures, checkpoint, and exact confirmation.
    # Assert plan status completed, spec completion record, next module M2, and audit event.
```

- [ ] **Step 2: Run the E2E test to verify it fails**

Run:

```bash
python -m pytest tests/e2e/test_claude_code_workflow.py -q
```

Expected: the adapter/core integration is incomplete.

- [ ] **Step 3: Complete fixture-driven assertions**

Use a copied temporary fixture project, never the repository fixture in place. Assert:

- failed Bash evidence leaves the module in `testing`;
- passing unit and regression evidence plus a complete checkpoint reaches `awaiting_confirmation`;
- natural language leaves both documents unchanged;
- exact `confirm-next` causes one `documents_updated` event, marks current module complete, updates spec and plan, and activates `M2`;
- repeating the same hook input/event ID does not append a second update;
- every event and state file remains under `.spec-driven/`.

- [ ] **Step 4: Run all tests**

Run:

```bash
python -m pytest tests/e2e/test_claude_code_workflow.py -q
python -m pytest -q
```

Expected: the complete Claude Code adapter gate passes offline using host-shaped fixtures.

- [ ] **Step 5: Commit the end-to-end proof**

```bash
git add tests/e2e/test_claude_code_workflow.py fixtures/markdown-project
git commit -m "test: prove Claude Code gated workflow"
```

## Claude Code acceptance checklist

- [ ] Capability report identifies each available/degraded hook guarantee.
- [ ] Bash success and failure hooks record real exit status and controlled output summaries.
- [ ] Natural-language confirmation cannot create an event.
- [ ] Exact confirmation is rejected by the core when either test gate is absent or failed.
- [ ] Hook installation preserves unrelated settings and is idempotent.
- [ ] A successful confirmation updates both spec and plan exactly once.
- [ ] Hook failures leave documents unchanged and provide actionable diagnostics.
