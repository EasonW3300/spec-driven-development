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
