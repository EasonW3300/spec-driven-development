import json
from pathlib import Path

from spec_driven.adapters.codex import (
    CodexCapabilities,
    normalize_confirmation,
    normalize_notify_event,
    parse_explicit_confirmation,
)


FIXTURES = Path("fixtures/codex")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_notify_turn_complete_normalizes_to_versioned_event() -> None:
    event = normalize_notify_event(_load("notify-turn-complete.json"))
    assert event is not None
    assert event.type == "session_turn_completed"
    assert event.schema_version == 1
    assert event.session_id


def test_unknown_notify_event_returns_none() -> None:
    assert normalize_notify_event(_load("notify-unknown-event.json")) is None


def test_only_exact_confirmation_command_is_accepted() -> None:
    assert parse_explicit_confirmation("confirm-next", "confirm-next") is True
    assert parse_explicit_confirmation("confirm-next --extra", "confirm-next") is False
    assert parse_explicit_confirmation("继续下一个模块", "confirm-next") is False
    assert parse_explicit_confirmation("please confirm-next now", "confirm-next") is False
    assert parse_explicit_confirmation("confirm-next", "advance") is False


def test_natural_language_prompt_does_not_create_event() -> None:
    assert normalize_confirmation(_load("prompt-natural-language.json"), "confirm-next") is None


def test_capability_report_marks_bash_exit_status_unavailable(tmp_path: Path) -> None:
    report = CodexCapabilities.detect({}, tmp_path / "config.toml")
    statuses = {capability.name: capability.status for capability in report.capabilities}
    assert statuses["bash_exit_status"] == "unavailable"
    assert statuses["session_events"] == "degraded"
    assert report.host == "codex"


def test_capability_report_detects_installed_config(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('notify = ["python", "-m", "spec_driven.adapters.codex_hook"]\n', encoding="utf-8")
    report = CodexCapabilities.detect({}, config)
    statuses = {capability.name: capability.status for capability in report.capabilities}
    assert statuses["session_events"] == "available"


def test_malformed_user_toml_degrades_instead_of_crashing(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("notify = [broken\n", encoding="utf-8")
    report = CodexCapabilities.detect({}, config)
    statuses = {capability.name: capability.status for capability in report.capabilities}
    assert statuses["session_events"] == "degraded"
