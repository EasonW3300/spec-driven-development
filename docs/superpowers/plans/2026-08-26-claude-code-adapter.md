# Claude Code Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the core engine to Claude Code’s hook lifecycle so real Bash test results and an exact `confirm-next` user submission produce validated events and document updates without prompt-only enforcement.

**Architecture:** A thin adapter has a capability probe, pure event normalizers, one hook entrypoint that reads Claude Code’s JSON stdin and writes the documented JSON decision response, and a shared core bridge. `SessionStart` records an audit event. `PostToolUse`/`PostToolUseFailure` record Bash evidence, classified by matching the Bash command against the configured unit/regression commands. `UserPromptSubmit` matches only the exact configured confirmation command and delegates the transaction to the core CLI. Normalizers never read synthetic fields: `module_id` comes from a core `status` call, `occurred_at` from the hook process clock. All behavior is fixture-tested and the generated settings fragment is installed only after capability validation, using the core baseline’s `install.py`.

**Tech Stack:** Python 3.11+, standard `json`/`re`/`subprocess`, existing `spec_driven` event/engine interfaces, Claude Code hook settings JSON, `pytest`.

## Global Constraints

- Requires `2026-08-26-spec-driven-core-baseline.md` (Task 7 install primitives and Task 6 `ingest-event`).
- The adapter never parses arbitrary natural-language confirmation as authorization.
- Only an exact configured command `confirm-next` in the current session/module context can create `next_module_confirmed`; the core verifies session/module against live state.
- Bash evidence is accepted only from the hook payload’s real tool response/exit status; agent-reported “passed” prose is never read as an exit code.
- Hook failures fail closed for confirmation and emit a diagnostic `stopReason`; they never write spec/plan themselves.
- Settings merge preserves unrelated user keys and registrations, is idempotent on reinstall, and is covered by an installation round-trip test (core `_union_lists` semantics).
- Exact hook names, matcher syntax, input fields, and output decision fields must be copied from the currently installed Claude Code hook schema during implementation and locked by the contract fixtures; the fixtures below are the concrete starting point and any field-name difference must be fixed in fixture and adapter together.
- Every task ends with focused tests, `python -m pytest -q`, and a focused commit.

---

## File structure

```text
pyproject.toml  (add console script spec-driven-claude)
src/spec_driven/adapters/
  _core_bridge.py
  claude_code.py
  claude_code_hook.py
  __init__.py
docs/adapters/claude-code-capabilities.md
install/manifests/claude-code.json
adapters/claude-code/settings.fragment.json
tests/contract/test_claude_code_contract.py
tests/unit/test_claude_code_adapter.py
tests/integration/test_claude_code_hooks.py
tests/integration/test_claude_code_install.py
tests/e2e/test_claude_code_workflow.py
fixtures/claude-code/
  session-start.json
  bash-post-tool-use.json
  bash-post-tool-use-failure.json
  confirmation-prompt.json
  natural-language-prompt.json
```

`claude_code.py` contains pure capability, normalization, and settings-fragment functions. `claude_code_hook.py` is the only process entrypoint and contains no document-write policy beyond dispatching to the core CLI. `_core_bridge.py` is the single place that shells out to the installed `spec-driven` CLI; the Codex adapter imports it too. The settings fragment is generated from the verified contract and is not hand-copied into a user settings file by the hook itself.

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
- `normalize_session_start(payload: Mapping[str, object], occurred_at: str) -> Event`.
- `normalize_bash_result(payload, success: bool, unit_command: str | None, regression_command: str | None, module_id: str, occurred_at: str) -> TestEvidence | None`.
- `classify_test_kind(command: str, unit_command: str | None, regression_command: str | None) -> str | None`.
- `parse_explicit_confirmation(prompt: str, command: str) -> bool`.
- `normalize_confirmation(payload, command: str, session_id: str, module_id: str, occurred_at: str) -> Event | None`.
- `claude_code_settings_fragment(hook_command: str) -> dict[str, object]`.

- [ ] **Step 1: Save contract fixtures**

Save the five files below verbatim as the contract starting point, then verify every field against the currently installed Claude Code hook schema (`claude hooks` reference or the hook payload the CLI emits during a real Bash run). If a documented field differs, update the fixture and the adapter together and record the doc date in `docs/adapters/claude-code-capabilities.md`. Do not add synthetic fields (`module_id`, `timestamp`, `test_kind`) to these fixtures — the normalizers take those as parameters.

`fixtures/claude-code/session-start.json`:

```json
{
  "session_id": "session-id-1",
  "transcript_path": "/home/user/project/.claude/transcripts/session-id-1.jsonl",
  "cwd": "/home/user/project",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```

`fixtures/claude-code/bash-post-tool-use.json`:

```json
{
  "session_id": "session-id-1",
  "transcript_path": "/home/user/project/.claude/transcripts/session-id-1.jsonl",
  "cwd": "/home/user/project",
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "python -m pytest tests/unit -q"},
  "tool_response": {"output": "1 passed"}
}
```

`fixtures/claude-code/bash-post-tool-use-failure.json`:

```json
{
  "session_id": "session-id-1",
  "transcript_path": "/home/user/project/.claude/transcripts/session-id-1.jsonl",
  "cwd": "/home/user/project",
  "hook_event_name": "PostToolUseFailure",
  "tool_name": "Bash",
  "tool_input": {"command": "python -m pytest -q"},
  "tool_response": {"output": "3 failed"},
  "exit_code": 1
}
```

`fixtures/claude-code/confirmation-prompt.json`:

```json
{
  "session_id": "session-id-1",
  "transcript_path": "/home/user/project/.claude/transcripts/session-id-1.jsonl",
  "cwd": "/home/user/project",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "confirm-next",
  "stop_hook_active": false
}
```

`fixtures/claude-code/natural-language-prompt.json`:

```json
{
  "session_id": "session-id-1",
  "transcript_path": "/home/user/project/.claude/transcripts/session-id-1.jsonl",
  "cwd": "/home/user/project",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "可以，继续",
  "stop_hook_active": false
}
```

- [ ] **Step 2: Write failing contract tests**

```python
import json
from pathlib import Path

from spec_driven.adapters.claude_code import (
    classify_test_kind,
    normalize_bash_result,
    normalize_confirmation,
    normalize_session_start,
    parse_explicit_confirmation,
)


FIXTURES = Path("fixtures/claude-code")
OCCURRED = "2026-08-27T10:00:00.123456+00:00"
UNIT = "python -m pytest tests/unit -q"
REGRESSION = "python -m pytest -q"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_session_start_normalizes_to_audit_event() -> None:
    event = normalize_session_start(_load("session-start.json"), OCCURRED)
    assert event.type == "session_started"
    assert event.schema_version == 1
    assert event.event_id == "session-id-1:session_started"
    assert event.occurred_at == OCCURRED
    assert event.payload["cwd"] == "/home/user/project"


def test_successful_bash_hook_classifies_unit_and_uses_real_fields() -> None:
    evidence = normalize_bash_result(_load("bash-post-tool-use.json"), True, UNIT, REGRESSION, "M1", OCCURRED)
    assert evidence is not None
    assert evidence.kind == "unit"
    assert evidence.module_id == "M1"
    assert evidence.exit_code == 0
    assert evidence.command == UNIT
    assert evidence.started_at == OCCURRED and evidence.finished_at == OCCURRED


def test_failed_bash_hook_preserves_nonzero_exit_code() -> None:
    evidence = normalize_bash_result(_load("bash-post-tool-use-failure.json"), False, UNIT, REGRESSION, "M1", OCCURRED)
    assert evidence is not None
    assert evidence.kind == "regression"
    assert evidence.exit_code == 1


def test_classify_test_kind_prefers_specific_unit_prefix() -> None:
    assert classify_test_kind("python -m pytest tests/unit -q", UNIT, REGRESSION) == "unit"
    assert classify_test_kind("python -m pytest -q", UNIT, REGRESSION) == "regression"
    assert classify_test_kind("ls", UNIT, REGRESSION) is None


def test_only_exact_confirmation_command_is_accepted() -> None:
    assert parse_explicit_confirmation("confirm-next", "confirm-next") is True
    assert parse_explicit_confirmation("confirm-next --extra", "confirm-next") is False
    assert parse_explicit_confirmation("继续下一个模块", "confirm-next") is False
    assert parse_explicit_confirmation("confirm-next", "advance") is False


def test_natural_language_prompt_does_not_create_event() -> None:
    payload = _load("natural-language-prompt.json")
    assert normalize_confirmation(payload, "confirm-next", "session-id-1", "M1", OCCURRED) is None


def test_exact_confirmation_event_is_versioned_and_explicit() -> None:
    event = normalize_confirmation(_load("confirmation-prompt.json"), "confirm-next", "session-id-1", "M1", OCCURRED)
    assert event is not None
    assert event.type == "next_module_confirmed"
    assert event.actor == "user"
    assert event.module_id == "M1"
    assert event.payload == {"confirmation": "explicit_command"}
    assert event.event_id == "session-id-1:confirm:M1:2026-08-27T10-00-00.123456+00-00"
```

- [ ] **Step 3: Run the contract tests to verify they fail**

Run:

```bash
python -m pytest tests/contract/test_claude_code_contract.py -q
```

Expected: import errors for the adapter functions.

- [ ] **Step 4: Implement normalization with explicit parameterization**

`src/spec_driven/adapters/claude_code.py`:

```python
from __future__ import annotations

import re
from collections.abc import Mapping

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
                Capability("session_events", status, "SessionStart hook", "session lifecycle is observable", "install SessionStart hook"),
                Capability("bash_exit_status", status, "PostToolUse/PostToolUseFailure", "real Bash result can be recorded", "install Bash matchers"),
                Capability("explicit_confirmation", status, "UserPromptSubmit exact command", "only confirm-next can authorize", "use the generic CLI command"),
                Capability("document_update", status, "local core CLI", "core gate controls writes", "run spec-driven doctor"),
            ),
        )


def _safe_ts(value: str) -> str:
    """Event ids double as filenames, so timestamps must keep the safe charset."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", value)


def _summary(payload: Mapping[str, object]) -> str:
    tool_response = payload.get("tool_response")
    output = str(tool_response.get("output", "")) if isinstance(tool_response, Mapping) else ""
    return " ".join(output.split())[:200]


def normalize_session_start(payload: Mapping[str, object], occurred_at: str) -> Event:
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        raise InvalidEventError("SessionStart payload is missing session_id")
    return Event(
        event_id=f"{session_id}:session_started",
        schema_version=1,
        session_id=session_id,
        type="session_started",
        occurred_at=occurred_at,
        source="claude-code",
        actor="host",
        module_id=None,
        payload={"cwd": str(payload.get("cwd", ""))},
    )


def classify_test_kind(command: str, unit_command: str | None, regression_command: str | None) -> str | None:
    if unit_command and command.startswith(unit_command):
        return "unit"
    if regression_command and command.startswith(regression_command):
        return "regression"
    return None


def normalize_bash_result(
    payload: Mapping[str, object],
    success: bool,
    unit_command: str | None,
    regression_command: str | None,
    module_id: str,
    occurred_at: str,
) -> TestEvidence | None:
    if str(payload.get("tool_name")) != "Bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return None
    command = str(tool_input.get("command", ""))
    kind = classify_test_kind(command, unit_command, regression_command)
    if kind is None:
        return None
    exit_code = int(payload["exit_code"]) if payload.get("exit_code") is not None else (0 if success else 1)
    return TestEvidence(
        kind=kind,
        module_id=module_id,
        command=command,
        working_directory=str(payload.get("cwd", ".")),
        started_at=occurred_at,
        finished_at=occurred_at,
        exit_code=exit_code,
        output_path=None,
        output_summary=_summary(payload),
        attempt=1,
    )


def parse_explicit_confirmation(prompt: str, command: str) -> bool:
    return bool(re.fullmatch(re.escape(command), prompt.strip()))


def normalize_confirmation(
    payload: Mapping[str, object],
    command: str,
    session_id: str,
    module_id: str,
    occurred_at: str,
) -> Event | None:
    prompt = str(payload.get("prompt", ""))
    if not parse_explicit_confirmation(prompt, command):
        return None
    return Event(
        event_id=f"{session_id}:confirm:{module_id}:{_safe_ts(occurred_at)}",
        schema_version=1,
        session_id=session_id,
        type="next_module_confirmed",
        occurred_at=occurred_at,
        source="claude-code",
        actor="user",
        module_id=module_id,
        payload={"confirmation": "explicit_command"},
    )


def _registration(matcher: str, hook_command: str) -> dict[str, object]:
    return {
        "matcher": matcher,
        "hooks": [{"type": "command", "command": hook_command}],
    }


def claude_code_settings_fragment(hook_command: str) -> dict[str, object]:
    return {
        "hooks": {
            "SessionStart": [_registration("SessionStart", hook_command)],
            "PostToolUse": [_registration("PostToolUse(Bash(...))", hook_command)],
            "PostToolUseFailure": [_registration("PostToolUseFailure(Bash(...))", hook_command)],
            "UserPromptSubmit": [_registration('UserPromptSubmit(prompt contains "confirm-next")', hook_command)],
        }
    }
```

The invariant is that `normalize_bash_result` rejects missing real identity fields and never reads prose “passed” text as an exit code, and `normalize_session_start`/`normalize_confirmation` never read `module_id` or a timestamp from the hook payload.

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

> **Implementation notes (Task 1 complete):** `occurred_at` is the hook-process clock (`datetime.now(timezone.utc).isoformat()`), never a payload field; `module_id` always comes from a core `status` call. Event ids must stay in `[A-Za-z0-9._-]` (`_safe_ts`) because they double as filenames under `.spec-driven/events/`. The Codex adapter’s normalizers share the same parameterized shape.

### Task 2: Implement the core bridge, hook dispatcher, and fail-closed confirmation path

**Files:**
- Create: `src/spec_driven/adapters/_core_bridge.py`
- Create: `src/spec_driven/adapters/claude_code_hook.py`
- Create: `tests/unit/test_claude_code_adapter.py`
- Create: `tests/integration/test_claude_code_hooks.py`
- Modify: `pyproject.toml`

**Interfaces:**
- `emit_to_core(project_root: Path, subcommand: str, payload: Mapping[str, object] | None = None, executable: str = "spec-driven") -> dict[str, object]` returns parsed JSON on exit `0` and raises `CoreCLIError(code, message)` on nonzero exit.
- `CoreCLIError(code: str, message: str)`.
- `dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult`.
- `HookResult(exit_code: int, response: Mapping[str, object], emitted: tuple[Event | TestEvidence, ...])`.
- `main(argv: list[str] | None = None) -> int` reads one JSON object from stdin and writes one JSON response.

- [ ] **Step 1: Write the core bridge and the dispatch unit tests**

`src/spec_driven/adapters/_core_bridge.py`:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Mapping


class CoreCLIError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _invoke(executable: str, project_root: Path, subcommand: str, payload: Mapping[str, object] | None) -> subprocess.CompletedProcess[str]:
    if payload is None:
        return subprocess.run(
            [executable, "--project", str(project_root), subcommand],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
    return subprocess.run(
        [executable, "--project", str(project_root), subcommand],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def emit_to_core(project_root: Path, subcommand: str, payload: Mapping[str, object] | None = None, executable: str = "spec-driven") -> dict[str, object]:
    result = _invoke(executable, project_root, subcommand, payload)
    if result.returncode == 0:
        return json.loads(result.stdout) if result.stdout.strip() else {}
    try:
        error = json.loads(result.stdout)
        raise CoreCLIError(str(error.get("code", "CORE_CLI_ERROR")), str(error.get("message", "")))
    except json.JSONDecodeError:
        raise CoreCLIError("CORE_CLI_ERROR", (result.stderr or result.stdout).strip())
```

`tests/unit/test_claude_code_adapter.py`:

```python
from __future__ import annotations

from io import StringIO
from pathlib import Path

from spec_driven.adapters import claude_code_hook as hook
from spec_driven.adapters._core_bridge import CoreCLIError


def test_natural_language_is_non_mutating_context(tmp_path: Path, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("natural language must not reach the core")
    monkeypatch.setattr(hook, "emit_to_core", fail_if_called)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "可以，继续"}
    result = hook.dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.exit_code == 0
    assert result.emitted == ()
    assert "confirm-next" in str(result.response)


def test_exact_confirmation_dispatches_explicit_event(tmp_path: Path, monkeypatch) -> None:
    def fake_emit(project_root, subcommand, payload=None, executable="spec-driven"):
        if subcommand == "status":
            return {"current_module_id": "M1"}
        return {"current_module_id": "M2"}
    monkeypatch.setattr(hook, "emit_to_core", fake_emit)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "confirm-next"}
    result = hook.dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.exit_code == 0
    assert result.emitted[0].type == "next_module_confirmed"
    assert result.emitted[0].module_id == "M1"
    assert result.emitted[0].payload == {"confirmation": "explicit_command"}


def test_irrelevant_bash_command_is_ignored(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_emit(project_root, subcommand, payload=None, executable="spec-driven"):
        calls.append(subcommand)
        if subcommand == "status":
            return {"current_module_id": "M1"}
        raise AssertionError("record-test must not run for unrelated Bash commands")

    monkeypatch.setattr(hook, "emit_to_core", fake_emit)
    payload = {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    result = hook.dispatch(payload, tmp_path, {})
    assert result.exit_code == 0
    assert result.emitted == ()
    assert "record-test" not in calls


def test_unknown_hook_event_continues_without_emitting(tmp_path: Path, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("unknown hook events must not reach the core")
    monkeypatch.setattr(hook, "emit_to_core", fail_if_called)
    result = hook.dispatch({"hook_event_name": "Stop", "session_id": "s1"}, tmp_path, {})
    assert result.exit_code == 0
    assert result.emitted == ()
    assert result.response == {"continue": True}


def test_missing_session_id_fails_closed(tmp_path: Path) -> None:
    result = hook.dispatch({"hook_event_name": "SessionStart"}, tmp_path, {})
    assert result.exit_code != 0
    assert result.response["continue"] is False
    assert "EVENT_INVALID" in str(result.response["stopReason"])


def test_gate_rejection_blocks_confirmation(tmp_path: Path, monkeypatch) -> None:
    def reject(project_root, subcommand, payload=None, executable="spec-driven"):
        if subcommand == "confirm-next":
            raise CoreCLIError("TEST_GATE_BLOCKED", "unit gate failed")
        return {"current_module_id": "M1"}
    monkeypatch.setattr(hook, "emit_to_core", reject)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "confirm-next"}
    result = hook.dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.exit_code != 0
    assert result.response["continue"] is False
    assert "TEST_GATE_BLOCKED" in str(result.response["stopReason"])


def test_core_cli_unavailable_fails_closed(tmp_path: Path, monkeypatch) -> None:
    def unavailable(project_root, subcommand, payload=None, executable="spec-driven"):
        raise CoreCLIError("CORE_CLI_ERROR", "executable not found")
    monkeypatch.setattr(hook, "emit_to_core", unavailable)
    result = hook.dispatch({"hook_event_name": "SessionStart", "session_id": "s1"}, tmp_path, {})
    assert result.exit_code != 0
    assert result.response["continue"] is False


def test_malformed_json_returns_2(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("{not json"))
    out = StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert hook.main([]) == 2
    assert "CLI_INPUT_INVALID" in out.getvalue()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_claude_code_adapter.py -q
```

Expected: import error for `claude_code_hook`.

- [ ] **Step 3: Implement event dispatch and host response mapping**

`src/spec_driven/adapters/claude_code_hook.py`:

```python
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import load_config
from ..errors import SpecDrivenError
from ..models import Event, TestEvidence
from ._core_bridge import CoreCLIError, emit_to_core
from .claude_code import (
    _safe_ts,
    normalize_bash_result,
    normalize_confirmation,
    normalize_session_start,
    parse_explicit_confirmation,
)


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    response: Mapping[str, object]
    emitted: tuple[Event | TestEvidence, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult:
    executable = env.get("SPECDRIVEN_EXECUTABLE", "spec-driven")
    command = env.get("SPECDRIVEN_CONFIRMATION_COMMAND", "confirm-next")
    hook_name = str(payload.get("hook_event_name", ""))
    occurred_at = _now()
    try:
        if hook_name == "SessionStart":
            event = normalize_session_start(payload, occurred_at)
            emit_to_core(project_root, "ingest-event", asdict(event), executable)
            return HookResult(0, {"continue": True}, (event,))
        if hook_name in {"PostToolUse", "PostToolUseFailure"}:
            config = load_config(project_root)
            status = emit_to_core(project_root, "status", None, executable)
            evidence = normalize_bash_result(
                payload,
                hook_name == "PostToolUse",
                config.unit_test_command,
                config.regression_test_command,
                str(status.get("current_module_id") or ""),
                occurred_at,
            )
            if evidence is None:
                return HookResult(0, {"continue": True}, ())
            session_id = str(payload.get("session_id") or "")
            event_id = f"{session_id}:test:{evidence.kind}:{_safe_ts(occurred_at)}"
            emit_to_core(project_root, "record-test", {"event_id": event_id, "evidence": asdict(evidence)}, executable)
            return HookResult(0, {"continue": True}, (evidence,))
        if hook_name == "UserPromptSubmit":
            prompt = str(payload.get("prompt", ""))
            if not parse_explicit_confirmation(prompt, command):
                return HookResult(0, {
                    "continue": True,
                    "systemMessage": f"Spec-driven workflow requires explicit `{command}` after both test gates pass.",
                }, ())
            status = emit_to_core(project_root, "status", None, executable)
            session_id = str(payload.get("session_id") or "")
            module_id = str(status.get("current_module_id") or "")
            event = normalize_confirmation(payload, command, session_id, module_id, occurred_at)
            after = emit_to_core(project_root, "confirm-next", asdict(event), executable)
            return HookResult(0, {
                "continue": True,
                "hookSpecificOutput": {"next_module": after.get("current_module_id")},
            }, (event,))
        return HookResult(0, {"continue": True}, ())
    except (SpecDrivenError, CoreCLIError, OSError) as error:
        code = getattr(error, "code", "CORE_CLI_ERROR")
        return HookResult(2, {"continue": False, "stopReason": f"{code}: {error}"}, ())


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            raise json.JSONDecodeError("expected a JSON object", "", 0)
    except json.JSONDecodeError as error:
        json.dump({"continue": False, "stopReason": f"CLI_INPUT_INVALID: {error}"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    project_root = Path(payload.get("cwd") or os.getcwd())
    result = dispatch(payload, project_root, os.environ)
    json.dump(result.response, sys.stdout)
    sys.stdout.write("\n")
    return result.exit_code
```

The hook process never writes spec/plan itself — every mutation goes through `emit_to_core` and the core gate. Add the console script to `pyproject.toml` under `[project.scripts]`:

```toml
spec-driven-claude = "spec_driven.adapters.claude_code_hook:main"
```

- [ ] **Step 4: Write integration tests against the real core**

`tests/integration/test_claude_code_hooks.py` drives the dispatcher against a temporary copy of the fixture project with the real `emit_to_core` bridge (the package is installed editable, so `spec-driven` is on PATH):

```python
from __future__ import annotations

import shutil
from pathlib import Path

from spec_driven.adapters._core_bridge import emit_to_core
from spec_driven.adapters.claude_code_hook import dispatch


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def _start(session_id: str, root: Path) -> None:
    emit_to_core(root, "start-module", {
        "event_id": "start-module-1",
        "schema_version": 1,
        "session_id": session_id,
        "type": "module_started",
        "occurred_at": "2026-08-27T00:00:00Z",
        "source": "claude-code",
        "actor": "agent",
        "module_id": "M1",
        "payload": {},
    })


def _bash(session_id: str, root: Path, command: str, exit_code: int) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(root),
        "hook_event_name": "PostToolUse" if exit_code == 0 else "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"output": "ok"},
        **({"exit_code": exit_code} if exit_code != 0 else {}),
    }


def _prompt(session_id: str, root: Path, text: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
        "stop_hook_active": False,
    }


def test_session_start_is_recorded_as_audit_event(tmp_path: Path) -> None:
    root = _project(tmp_path)
    session_id = emit_to_core(root, "start", None)["session_id"]
    result = dispatch({
        "hook_event_name": "SessionStart",
        "session_id": session_id,
        "cwd": str(root),
        "transcript_path": str(root / ".claude/transcripts/t.jsonl"),
        "source": "startup",
    }, root, {})
    assert result.exit_code == 0
    assert list((root / ".spec-driven/events").glob("*session_started.json"))
    assert emit_to_core(root, "status", None)["current_module_id"] == "M1"


def test_bash_failure_records_real_exit_code(tmp_path: Path) -> None:
    root = _project(tmp_path)
    session_id = emit_to_core(root, "start", None)["session_id"]
    _start(session_id, root)
    assert dispatch(_bash(session_id, root, "python -m pytest tests/unit -q", 0), root, {}).exit_code == 0
    assert dispatch(_bash(session_id, root, "python -m pytest -q", 1), root, {}).exit_code == 0
    status = emit_to_core(root, "status", None)
    assert status["module_states"]["M1"] == "testing"
    regression = [item for item in status["evidence"] if item["kind"] == "regression"][-1]
    assert regression["exit_code"] == 1


def test_confirmation_before_gate_fails_closed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    session_id = emit_to_core(root, "start", None)["session_id"]
    _start(session_id, root)
    before = (root / "docs/plans/product-plan.md").read_bytes()
    result = dispatch(_prompt(session_id, root, "confirm-next"), root, {})
    assert result.exit_code != 0
    assert result.response["continue"] is False
    assert "STATE_CONFLICT" in str(result.response["stopReason"])
    assert (root / "docs/plans/product-plan.md").read_bytes() == before


def test_exact_confirmation_updates_documents(tmp_path: Path) -> None:
    root = _project(tmp_path)
    session_id = emit_to_core(root, "start", None)["session_id"]
    _start(session_id, root)
    assert dispatch(_bash(session_id, root, "python -m pytest tests/unit -q", 0), root, {}).exit_code == 0
    assert dispatch(_bash(session_id, root, "python -m pytest -q", 0), root, {}).exit_code == 0
    emit_to_core(root, "checkpoint", {
        "event_id": "cp-event",
        "checkpoint": {"checkpoint_id": "cp1", "module_id": "M1", "completed_points": ["gate works"], "notes": []},
    })
    result = dispatch(_prompt(session_id, root, "confirm-next"), root, {})
    assert result.exit_code == 0
    assert result.response["hookSpecificOutput"]["next_module"] == "M2"
    assert 'status="completed"' in (root / "docs/plans/product-plan.md").read_text(encoding="utf-8")
    assert (root / "docs/specs/product.md").read_text(encoding="utf-8").count("Status: completed") == 1
```

- [ ] **Step 5: Run unit and integration tests and the full suite**

Run:

```bash
python -m pytest tests/unit/test_claude_code_adapter.py tests/integration/test_claude_code_hooks.py -q
python -m pytest -q
```

Expected: exact confirmation reaches the core, natural language only receives context, unrelated Bash commands are ignored, and all failure paths fail closed.

- [ ] **Step 6: Commit the dispatcher**

```bash
git add src/spec_driven/adapters/_core_bridge.py src/spec_driven/adapters/claude_code_hook.py pyproject.toml tests/unit/test_claude_code_adapter.py tests/integration/test_claude_code_hooks.py
git commit -m "feat: add fail-closed Claude Code hook dispatcher"
```

---

> **Implementation notes (Task 2 complete):** `emit_to_core` is the only place that shells out; the Codex adapter imports it from `_core_bridge.py`. Core rejection of any forwarded item fails the hook closed with exit `2` plus a `stopReason` carrying the stable error code. `dispatch` itself is pure and never writes. Replaying a successful confirmation produces a new timestamped event id and is rejected by the core because the module is no longer current — never a second document update.

### Task 3: Register and install Claude Code hooks safely

**Files:**
- Create: `adapters/claude-code/settings.fragment.json`
- Create: `docs/adapters/claude-code-capabilities.md`
- Create: `install/manifests/claude-code.json`
- Create: `tests/integration/test_claude_code_install.py`

**Interfaces:**
- `claude_code_settings_fragment(hook_command: str) -> dict[str, object]` returns the verified hook registrations.
- The fragment contains separate registrations for session start, Bash success, Bash failure, and user prompt submission, with exact matchers from the contract fixtures.
- Installation uses the core baseline `install.py` primitives (`plan_install`/`apply_install`/`rollback_install`) and returns a rollback receipt; this task never modifies `install.py`.

- [ ] **Step 1: Write a settings merge and round-trip test**

```python
from __future__ import annotations

import json
from pathlib import Path

from spec_driven.adapters.claude_code import claude_code_settings_fragment
from spec_driven.capabilities import HostManifest, load_host_manifest
from spec_driven.install import apply_install, plan_install, rollback_install


HOOK_COMMAND = "spec-driven-claude"


def _package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    (package / "skills" / "spec-driven-development").mkdir(parents=True)
    (package / "skills" / "spec-driven-development" / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    return package


def _manifest(tmp_path: Path) -> HostManifest:
    path = tmp_path / "claude-code.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "host": "claude-code",
        "adapter_module": "spec_driven.adapters.claude_code",
        "skill_source": "skills/spec-driven-development",
        "skill_target": ".claude/skills/spec-driven-development",
        "settings_target": ".claude/settings.json",
        "settings_fragment": claude_code_settings_fragment(HOOK_COMMAND),
    }), encoding="utf-8")
    return load_host_manifest(path)


def test_settings_merge_keeps_existing_hooks(tmp_path: Path) -> None:
    target = tmp_path / "home"
    (target / ".claude").mkdir(parents=True)
    settings = target / ".claude" / "settings.json"
    original = {"theme": "dark", "hooks": {"Notification": [{"matcher": "Notification", "hooks": [{"type": "command", "command": "keep"}]}]}}
    settings.write_text(json.dumps(original), encoding="utf-8")
    manifest = _manifest(tmp_path)
    backup_root = target / ".spec-driven" / "install-receipts" / ".backups"
    receipt = apply_install(plan_install(manifest, _package(tmp_path), target), backup_root)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert merged["hooks"]["Notification"] == original["hooks"]["Notification"]
    assert len(merged["hooks"]["SessionStart"]) == 1
    assert (target / ".claude/skills/spec-driven-development" / "SKILL.md").is_file()
    rollback_install(receipt)
    assert json.loads(settings.read_text(encoding="utf-8")) == original


def test_reinstall_never_duplicates_registrations(tmp_path: Path) -> None:
    target = tmp_path / "home"
    (target / ".claude").mkdir(parents=True)
    settings = target / ".claude" / "settings.json"
    settings.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    manifest = _manifest(tmp_path)
    backup_root = target / ".spec-driven" / "install-receipts" / ".backups"
    first = apply_install(plan_install(manifest, _package(tmp_path), target), backup_root)
    apply_install(plan_install(manifest, _package(tmp_path), target), backup_root)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    for registrations in merged["hooks"].values():
        assert len(registrations) == 1
    rollback_install(first)
    assert json.loads(settings.read_text(encoding="utf-8")) == {"hooks": {}}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/integration/test_claude_code_install.py -q
```

Expected: missing settings fragment or installation integration failure.

- [ ] **Step 3: Generate the verified settings fragment and manifest**

Write `adapters/claude-code/settings.fragment.json` as the exact output of `claude_code_settings_fragment("spec-driven-claude")`:

```json
{
  "hooks": {
    "SessionStart": [
      {"matcher": "SessionStart", "hooks": [{"type": "command", "command": "spec-driven-claude"}]}
    ],
    "PostToolUse": [
      {"matcher": "PostToolUse(Bash(...))", "hooks": [{"type": "command", "command": "spec-driven-claude"}]}
    ],
    "PostToolUseFailure": [
      {"matcher": "PostToolUseFailure(Bash(...))", "hooks": [{"type": "command", "command": "spec-driven-claude"}]}
    ],
    "UserPromptSubmit": [
      {"matcher": "UserPromptSubmit(prompt contains \"confirm-next\")", "hooks": [{"type": "command", "command": "spec-driven-claude"}]}
    ]
  }
}
```

Write `install/manifests/claude-code.json` with `settings_fragment` equal to the same fragment. Reuse `claude_code_settings_fragment` as the single source of truth; generate both files from it and keep them byte-identical.

- [ ] **Step 4: Add capability documentation**

`docs/adapters/claude-code-capabilities.md` records the documentation/verification date, each hook event used, matcher, fields consumed, output decision fields, whether the hook can block, and the generic fallback when unavailable:

```markdown
# Claude Code adapter capabilities

Verified against Claude Code hook payloads on <date>. Re-verify field names and
matcher syntax against the currently installed CLI before installing in a repo.

| Capability | Hook event | Matcher | Fields consumed | Output decisions | Blocks? |
| --- | --- | --- | --- | --- | --- |
| session lifecycle | SessionStart | `SessionStart` | `session_id`, `cwd` | `continue` | no |
| Bash success | PostToolUse | `PostToolUse(Bash(...))` | `tool_input.command`, `tool_response.output` | `continue` | no |
| Bash failure | PostToolUseFailure | `PostToolUseFailure(Bash(...))` | `tool_input.command`, `exit_code` | `continue` | no |
| explicit confirmation | UserPromptSubmit | `UserPromptSubmit(prompt contains "confirm-next")` | `prompt` | `continue` / `stopReason` | yes |
| document update | (core CLI) | — | — | — | yes |
| natural-language confirmation | UserPromptSubmit | (no matcher) | `prompt` | `continue` + `systemMessage` | no |

When hooks are unavailable (no `CLAUDE_CODE_HOOK_INPUT`, no settings `hooks`), every
capability reports `degraded` and the workflow falls back to the generic CLI path in
`skills/spec-driven-development/SKILL.md`: the agent asks the user to type
`confirm-next` and runs `spec-driven confirm-next` itself.
```

- [ ] **Step 5: Prove idempotent, non-destructive installation**

Run the two tests from Step 1. Together they prove: unrelated hooks and settings survive, our registrations are installed exactly once no matter how many times `install` runs, the skill is copied, and `rollback_install` restores the previous settings byte-for-byte. No test may modify `src/spec_driven/install.py`.

- [ ] **Step 6: Run adapter installation tests and full regression**

Run:

```bash
python -m pytest tests/integration/test_claude_code_install.py tests/contract/test_claude_code_contract.py -q
python -m pytest -q
```

Expected: settings are merged idempotently, rollback is byte-equivalent, and the manifest contains a non-empty verified fragment.

- [ ] **Step 7: Commit Claude Code registration**

```bash
git add adapters/claude-code/settings.fragment.json docs/adapters/claude-code-capabilities.md install/manifests/claude-code.json tests/integration/test_claude_code_install.py
git commit -m "feat: register Claude Code workflow hooks"
```

---

> **Implementation notes (Task 3 complete):** The core baseline’s `_union_lists` gives registrations append semantics (same matcher + command is a reinstall no-op, a shared command upgrades in place, disjoint commands coexist), so this task only supplies manifest data and tests. The Codex plan follows the same receipt shape with a TOML merger.

### Task 4: Prove the real end-to-end Claude Code gate

**Files:**
- Create: `tests/e2e/test_claude_code_workflow.py`

**Interfaces:**
- The E2E test drives host-shaped hook payloads through `dispatch` with the real core bridge on a temporary copy of the fixture project, and inspects core state, event files, and both documents.

- [ ] **Step 1: Write the E2E scenario**

```python
from __future__ import annotations

import shutil
from pathlib import Path

from spec_driven.adapters._core_bridge import emit_to_core
from spec_driven.adapters.claude_code_hook import dispatch


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def _start_module(session_id: str, root: Path) -> None:
    emit_to_core(root, "start-module", {
        "event_id": "start-module-1",
        "schema_version": 1,
        "session_id": session_id,
        "type": "module_started",
        "occurred_at": "2026-08-27T00:00:00Z",
        "source": "claude-code",
        "actor": "agent",
        "module_id": "M1",
        "payload": {},
    })


def _bash(session_id: str, root: Path, command: str, exit_code: int) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(root),
        "hook_event_name": "PostToolUse" if exit_code == 0 else "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"output": "ok"},
        **({"exit_code": exit_code} if exit_code != 0 else {}),
    }


def _prompt(session_id: str, root: Path, text: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
        "stop_hook_active": False,
    }


def test_claude_code_hook_flow_updates_documents_only_after_confirmation(tmp_path: Path) -> None:
    root = _project(tmp_path)
    session_id = emit_to_core(root, "start", None)["session_id"]
    _start_module(session_id, root)

    # Natural language before any gate is a non-mutating context message.
    before_spec = (root / "docs/specs/product.md").read_bytes()
    natural = dispatch(_prompt(session_id, root, "可以，继续"), root, {})
    assert natural.exit_code == 0
    assert natural.emitted == ()
    assert "confirm-next" in str(natural.response)
    assert (root / "docs/specs/product.md").read_bytes() == before_spec

    # A failed regression gate leaves the module in testing; no checkpoint is allowed.
    assert dispatch(_bash(session_id, root, "python -m pytest tests/unit -q", 0), root, {}).exit_code == 0
    assert dispatch(_bash(session_id, root, "python -m pytest -q", 1), root, {}).exit_code == 0
    assert emit_to_core(root, "status", None)["module_states"]["M1"] == "testing"

    # Passing both gates then checkpointing reaches awaiting_confirmation.
    assert dispatch(_bash(session_id, root, "python -m pytest -q", 0), root, {}).exit_code == 0
    emit_to_core(root, "checkpoint", {
        "event_id": "cp-event",
        "checkpoint": {
            "checkpoint_id": "cp1",
            "module_id": "M1",
            "completed_points": ["hook gate works"],
            "notes": ["host adapter records real exit codes"],
        },
    })
    assert emit_to_core(root, "status", None)["module_states"]["M1"] == "awaiting_confirmation"

    # Exact confirmation updates both documents exactly once and activates M2.
    confirm = dispatch(_prompt(session_id, root, "confirm-next"), root, {})
    assert confirm.exit_code == 0
    assert confirm.response["hookSpecificOutput"]["next_module"] == "M2"
    for relative in ("docs/specs/product.md", "docs/plans/product-plan.md"):
        content = (root / relative).read_text(encoding="utf-8")
        assert content.count("Status: completed") == 1
        assert "- hook gate works" in content
    updated = [p for p in (root / ".spec-driven/events").glob("*documents-updated*.json")]
    assert len(updated) == 1

    # A second exact confirmation is rejected: the module is no longer current.
    again = dispatch(_prompt(session_id, root, "confirm-next"), root, {})
    assert again.exit_code != 0
    assert again.response["continue"] is False
    assert emit_to_core(root, "status", None)["current_module_id"] == "M2"
    updated = [p for p in (root / ".spec-driven/events").glob("*documents-updated*.json")]
    assert len(updated) == 1

    # Every generated file stays under .spec-driven/.
    top_level = {path.relative_to(root).parts[0] for path in root.rglob("*") if path.is_file()}
    assert top_level <= {".spec-driven", "docs", "spec-driven.config.yaml"}
```

- [ ] **Step 2: Run the E2E test to verify it fails**

Run:

```bash
python -m pytest tests/e2e/test_claude_code_workflow.py -q
```

Expected: the adapter/core integration is incomplete.

- [ ] **Step 3: Complete the scenario**

The test above is complete as written; implement until it passes. It uses a copied temporary fixture project, never the repository fixture in place. It covers: natural language is non-mutating, failed evidence stays in `testing`, both gates plus a checkpoint reach `awaiting_confirmation`, exact `confirm-next` causes exactly one `documents_updated` event and marks M1 complete while activating M2, a replayed confirmation is rejected without a second update, and all state/events stay under `.spec-driven/`.

- [ ] **Step 4: Run all tests**

Run:

```bash
python -m pytest tests/e2e/test_claude_code_workflow.py -q
python -m pytest -q
```

Expected: the complete Claude Code adapter gate passes offline using host-shaped fixtures.

- [ ] **Step 5: Commit the end-to-end proof**

```bash
git add tests/e2e/test_claude_code_workflow.py
git commit -m "test: prove Claude Code gated workflow"
```

> **Implementation notes (Task 4 complete):** `confirm_next` requires session+module match against live state, so the hook flow must echo the session id from core `start` output back through the UserPromptSubmit payload. Replaying a successful confirmation yields a new timestamped event id and is correctly rejected by the core as no-longer-current — the single `documents_updated` assertion is the guard against double writes.

## Claude Code acceptance checklist

- [ ] Capability report identifies each available/degraded hook guarantee.
- [ ] Bash success and failure hooks record real exit status and controlled output summaries.
- [ ] Natural-language confirmation cannot create an event.
- [ ] Exact confirmation is rejected by the core when either test gate is absent or failed, and the hook fails closed.
- [ ] Hook installation preserves unrelated settings/registrations, is idempotent, and rolls back byte-exactly.
- [ ] A successful confirmation updates both spec and plan exactly once.
- [ ] Hook failures leave documents unchanged and provide actionable `stopReason` diagnostics.
