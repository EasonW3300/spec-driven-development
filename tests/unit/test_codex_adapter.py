from pathlib import Path

from spec_driven.adapters.codex_hook import dispatch


def test_natural_language_is_non_mutating_context(tmp_path: Path) -> None:
    payload = {
        "type": "user-prompt",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:00Z",
        "module_id": "M1",
        "prompt": "可以，继续",
    }
    result = dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.exit_code == 0
    assert result.emitted == ()
    assert "confirm-next" in str(result.response)


def test_exact_confirmation_emits_core_event(tmp_path: Path) -> None:
    payload = {
        "type": "user-prompt",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:00Z",
        "module_id": "M1",
        "prompt": "confirm-next",
    }
    result = dispatch(payload, tmp_path, {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"})
    assert result.emitted[0].type == "next_module_confirmed"


def test_turn_complete_event_is_forwarded(tmp_path: Path) -> None:
    payload = {"type": "agent-turn-complete", "session_id": "s1", "timestamp": "2026-08-27T00:00:00Z"}
    result = dispatch(payload, tmp_path, {})
    assert result.emitted[0].type == "session_turn_completed"


def test_unknown_event_type_is_ignored_silently(tmp_path: Path) -> None:
    result = dispatch({"type": "session-configured", "session_id": "s1"}, tmp_path, {})
    assert result.exit_code == 0
    assert result.response == {"status": "ignored"}
    assert result.emitted == ()
