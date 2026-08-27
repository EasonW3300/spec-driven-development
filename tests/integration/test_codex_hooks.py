import json
import shutil
from pathlib import Path

from spec_driven.adapters.codex_hook import dispatch, main

_ENV = {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"}


def _project(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    before = {p: p.read_bytes() for p in sorted((root / "docs").rglob("*.md"))}
    return root, before


def test_missing_payload_argument_exits_two_and_touches_nothing(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    root, before = _project(tmp_path)
    monkeypatch.chdir(root)
    assert main([]) == 2
    captured = capsys.readouterr()
    assert "missing or invalid JSON payload" in captured.out
    assert {(p, p.read_bytes()) for p in sorted((root / "docs").rglob("*.md"))} == set(before.items())


def test_unparseable_json_exits_two_with_diagnostic(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    root, before = _project(tmp_path)
    monkeypatch.chdir(root)
    assert main(["{not json"]) == 2
    captured = capsys.readouterr()
    assert "missing or invalid JSON payload" in captured.out
    assert {(p, p.read_bytes()) for p in sorted((root / "docs").rglob("*.md"))} == set(before.items())


def test_confirmation_without_module_id_fails_closed(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    root, before = _project(tmp_path)
    monkeypatch.chdir(root)
    payload = {
        "type": "user-prompt",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:00Z",
        "prompt": "confirm-next",
    }
    result = dispatch(payload, root, _ENV)
    assert result.exit_code == 2
    assert "M" in str(result.response.get("reason", "")) or "missing" in str(result.response).lower()
    capsys.readouterr()
    assert {(p, p.read_bytes()) for p in sorted((root / "docs").rglob("*.md"))} == set(before.items())


def test_core_rejection_is_reported_not_blocked(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Gates never opened for session s1, so the core refuses the confirmation;
    notify output controls nothing, so the bridge reports instead of exiting hard."""
    root, before = _project(tmp_path)
    monkeypatch.chdir(root)
    payload = {
        "type": "user-prompt",
        "session_id": "s1",
        "timestamp": "2026-08-27T00:00:00Z",
        "module_id": "M1",
        "prompt": "confirm-next",
    }
    raw = json.dumps(payload)
    assert main([raw]) == 0
    captured = capsys.readouterr()
    response = json.loads(captured.out.strip().splitlines()[-1])
    assert response["status"] == "error"
    assert "CORE_REJECTED" in response["reason"]
    assert {(p, p.read_bytes()) for p in sorted((root / "docs").rglob("*.md"))} == set(before.items())


def test_turn_complete_notification_reports_ok(tmp_path: Path, capsys, monkeypatch) -> None:
    root, before = _project(tmp_path)
    monkeypatch.chdir(root)
    payload = json.dumps(
        {"type": "agent-turn-complete", "session_id": "s1", "timestamp": "2026-08-27T00:00:00Z"}
    )
    assert main([payload]) == 0
    captured = capsys.readouterr()
    response = json.loads(captured.out.strip().splitlines()[-1])
    # lifecycle events carry no core state transition today -> nothing rejected
    assert response["status"] == "ok"
    assert {(p, p.read_bytes()) for p in sorted((root / "docs").rglob("*.md"))} == set(before.items())
