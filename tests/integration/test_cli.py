import json
import shutil
from pathlib import Path

import pytest

from spec_driven.cli import main


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def _input(tmp_path: Path, name: str, payload: object) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def evidence_payload(kind: str, module_id: str = "M1") -> dict[str, object]:
    return {
        "event_id": f"{kind}-1",
        "evidence": {
            "kind": kind,
            "module_id": module_id,
            "command": f"pytest {kind}",
            "working_directory": ".",
            "started_at": "t0",
            "finished_at": "t1",
            "exit_code": 0,
            "output_path": None,
            "output_summary": "ok",
            "attempt": 1,
        },
    }


def _status(root: Path) -> dict[str, object]:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert main(["--project", str(root), "status"]) == 0
    payload = json.loads(buffer.getvalue())
    assert isinstance(payload, dict)
    return payload


def test_doctor_reports_checks_in_human_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path)
    assert main(["--project", str(root), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "configuration: pass" in out
    assert "document_discovery: pass" in out
    assert "test_commands: pass" in out
    assert "host_adapter: pass" in out


def test_cli_workflow_drives_gate_to_confirmation(tmp_path: Path) -> None:
    root = _project(tmp_path)
    start_input = _input(tmp_path, "start.json", {"session_id": "s1"})
    assert main(["--project", str(root), "start", "--input", start_input]) == 0
    session_id = str(_status(root)["session_id"])
    start_module = _input(tmp_path, "start-module.json", {"event_id": "start-1", "schema_version": 1, "session_id": session_id, "type": "module_started", "occurred_at": "t0", "source": "generic", "actor": "agent", "module_id": "M1", "payload": {}})
    unit = _input(tmp_path, "unit.json", evidence_payload("unit"))
    regression = _input(tmp_path, "regression.json", evidence_payload("regression"))
    checkpoint = _input(tmp_path, "checkpoint.json", {"event_id": "cp-1", "checkpoint": {"checkpoint_id": "cp-M1", "module_id": "M1", "completed_points": ["gate works"], "notes": ["reuse API"]}})
    confirmation = _input(tmp_path, "confirm.json", {"event_id": "confirm-1", "schema_version": 1, "session_id": session_id, "type": "next_module_confirmed", "occurred_at": "t1", "source": "generic", "actor": "user", "module_id": "M1", "payload": {"confirmation": "explicit_command"}})

    assert main(["--project", str(root), "start-module", "--input", start_module]) == 0
    assert main(["--project", str(root), "record-test", "--input", unit]) == 0
    assert main(["--project", str(root), "record-test", "--input", regression]) == 0
    assert main(["--project", str(root), "checkpoint", "--input", checkpoint]) == 0
    assert main(["--project", str(root), "confirm-next", "--input", confirmation]) == 0
    status_json = _status(root)
    assert status_json["current_module_id"] == "M2"
    assert 'status="completed"' in (root / "docs/specs/product.md").read_text(encoding="utf-8")
    assert 'status="completed"' in (root / "docs/plans/product-plan.md").read_text(encoding="utf-8")


def _last_error(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    return payload


def test_malformed_input_maps_to_exit_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    exit_code = main(["--project", str(root), "start-module", "--input", str(bad)])
    assert exit_code == 2
    assert _last_error(capsys)["code"] == "CLI_INPUT_INVALID"


def test_gate_error_prints_stable_shape_and_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path)
    start_input = _input(tmp_path, "s.json", {"session_id": "s1"})
    assert main(["--project", str(root), "start", "--input", start_input]) == 0
    session_id = str(_status(root)["session_id"])
    start_module = _input(tmp_path, "m.json", {"event_id": "start-1", "schema_version": 1, "session_id": session_id, "type": "module_started", "occurred_at": "t0", "source": "generic", "actor": "agent", "module_id": "M1", "payload": {}})
    checkpoint = _input(tmp_path, "c.json", {"event_id": "cp-1", "checkpoint": {"checkpoint_id": "cp-M1", "module_id": "M1", "completed_points": ["gate works"], "notes": []}})

    assert main(["--project", str(root), "start-module", "--input", start_module]) == 0
    capsys.readouterr()  # drain successful-call output so only the error document remains
    exit_code = main(["--project", str(root), "checkpoint", "--input", checkpoint])
    assert exit_code == 1
    error = _last_error(capsys)
    assert error["code"] == "TEST_GATE_BLOCKED"
    assert error["retryable"] is False
