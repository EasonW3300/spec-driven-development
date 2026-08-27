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


def test_bash_success_maps_to_test_evidence(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "PostToolUse",
        "session_id": "s1",
        "tool_name": "Bash",
        "command": "pytest",
        "module_id": "M1",
        "test_kind": "unit",
        "exit_code": 0,
        "started_at": "t0",
        "finished_at": "t1",
    }
    result = dispatch(payload, tmp_path, {})
    assert result.exit_code == 0
    assert isinstance(result.emitted[0], object)
    assert getattr(result.emitted[0], "kind", "") == "unit"


def test_session_start_emits_session_event(tmp_path: Path) -> None:
    payload = {"hook_event_name": "SessionStart", "session_id": "s1", "timestamp": "t", "cwd": "/p"}
    result = dispatch(payload, tmp_path, {})
    assert result.emitted[0].type == "session_started"


def test_malformed_confirmation_missing_module_fails_closed(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s1",
        "prompt": "confirm-next",
        # missing module_id and timestamp
    }
    result = dispatch(payload, tmp_path, {})
    assert result.exit_code != 0
    assert result.response["continue"] is False
