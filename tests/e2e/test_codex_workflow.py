from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import spec_driven.models as _models
from spec_driven.adapters._core_bridge import emit_to_core
from spec_driven.adapters.codex_hook import dispatch
from spec_driven.engine import CoreEngine

ENV = {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"}

_UNIT = f'{sys.executable} -c "import sys; sys.exit(0)"'
_REG_PASS = f'{sys.executable} -c "import sys; sys.exit(0)"'
_REG_FAIL = f'{sys.executable} -c "import sys; sys.exit(1)"'


def _project(tmp_path: Path, *, regression_passes: bool) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    regression = _REG_PASS if regression_passes else _REG_FAIL
    (root / "spec-driven.config.yaml").write_text(
        "schema_version: 1\n"
        "spec:\n"
        "  paths: [docs/specs/product.md]\n"
        "plan:\n"
        "  paths: [docs/plans/product-plan.md]\n"
        "tests:\n"
        f"  unit:\n    command: {json.dumps(_UNIT)}\n"
        f"  regression:\n    command: {json.dumps(regression)}\n",
        encoding="utf-8",
    )
    return root


def _run_configured_command(root: Path, command: str) -> int:
    """Codex has no Bash exit-status capability: real exit codes come only from
    executing the configured command itself, never from adapter-supplied flags."""
    return subprocess.run(shlex.split(command), cwd=root, check=False).returncode


def _cli(root: Path, *arguments: str, stdin: dict[str, object] | None = None) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "spec_driven.cli", "--project", str(root), *arguments],
        input=json.dumps(stdin) if stdin is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def _record_test(root: Path, event_id: str, kind: str, command: str, exit_code: int, attempt: int) -> int:
    payload = {
        "event_id": event_id,
        "evidence": {
            "kind": kind,
            "module_id": "M1",
            "command": command,
            "working_directory": str(root),
            "started_at": "t0",
            "finished_at": "t1",
            "exit_code": exit_code,
            "output_path": None,
            "output_summary": "",
            "attempt": attempt,
        },
    }
    return _cli(root, "record-test", "--input", "-", stdin=payload)


def _record_checkpoint(root: Path) -> int:
    payload = {
        "event_id": "cp-event",
        "checkpoint": {
            "checkpoint_id": "cp1",
            "module_id": "M1",
            "completed_points": ["login API"],
            "notes": ["reuse session token logic in M2"],
        },
    }
    return _cli(root, "checkpoint", "--input", "-", stdin=payload)


def _confirm_payload(session_id: str, timestamp: str) -> dict[str, object]:
    return {
        "type": "user-prompt",
        "session_id": session_id,
        "timestamp": timestamp,
        "module_id": "M1",
        "prompt": "confirm-next",
    }


def _prepared(tmp_path: Path) -> tuple[CoreEngine, Path]:
    """Real gate: run the unit command first so its true exit code is recorded."""
    root = _project(tmp_path, regression_passes=True)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(
        _models.Event("start-1", 1, "session-1", "module_started", "t0", "codex", "agent", "M1", {})
    )
    unit_exit = _run_configured_command(root, _UNIT)
    assert unit_exit == 0
    assert _record_test(root, "unit-1", "unit", _UNIT, unit_exit, attempt=1) == 0
    return engine, root


def _docs(root: Path) -> tuple[bytes, bytes]:
    return (
        (root / "docs/specs/product.md").read_bytes(),
        (root / "docs/plans/product-plan.md").read_bytes(),
    )


def test_failed_regression_via_real_execution_keeps_testing_and_documents_untouched(tmp_path: Path) -> None:
    root = _project(tmp_path, regression_passes=False)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(
        _models.Event("start-1", 1, "session-1", "module_started", "t0", "codex", "agent", "M1", {})
    )
    before = _docs(root)

    unit_exit = _run_configured_command(root, _UNIT)
    reg_exit = _run_configured_command(root, _REG_FAIL)
    assert (unit_exit, reg_exit) == (0, 1)
    assert _record_test(root, "unit-1", "unit", _UNIT, unit_exit, attempt=1) == 0
    assert _record_test(root, "reg-1", "regression", _REG_FAIL, reg_exit, attempt=1) == 0
    checkpoint_exit = _record_checkpoint(root)
    # gates still open (regression failed) -> checkpoint must be refused
    assert checkpoint_exit != 0

    status = engine.status()
    assert status.module_states["M1"] == "testing"
    assert [e.exit_code for e in status.evidence] == [0, 1]
    assert _docs(root) == before


def test_confirmation_updates_documents_once_and_replay_deduplicates(tmp_path: Path) -> None:
    engine, root = _prepared(tmp_path)

    reg_exit = _run_configured_command(root, _REG_PASS)
    assert reg_exit == 0
    assert _record_test(root, "reg-1", "regression", _REG_PASS, reg_exit, attempt=1) == 0
    assert _record_checkpoint(root) == 0
    assert engine.status().module_states["M1"] == "awaiting_confirmation"
    assert engine.status().session_state == "active"

    natural_before = _docs(root)
    natural = dispatch(
        {
            "type": "user-prompt",
            "prompt": "可以，继续",
            "session_id": "session-1",
            "module_id": "M1",
            "timestamp": "2026-08-27T00:00:00Z",
        },
        root,
        ENV,
    )
    assert natural.emitted == ()
    assert _docs(root) == natural_before

    hook_payload = _confirm_payload("session-1", "2026-08-27T00:01:00Z")
    normalized = dispatch(hook_payload, root, ENV).emitted[0]
    original_cwd = Path.cwd()
    try:
        import os

        os.chdir(root)
        first_codes = emit_to_core((normalized,), env={})
        after_first = _docs(root)
        # replaying the identical host payload must deduplicate by canonical event id
        replay = dispatch(hook_payload, root, ENV).emitted[0]
        second_codes = emit_to_core((replay,), env={})
    finally:
        os.chdir(original_cwd)

    assert first_codes == [0] and second_codes == [0]
    assert after_first != natural_before
    assert _docs(root) == after_first
    spec_text = after_first[0].decode("utf-8")
    plan_text = after_first[1].decode("utf-8")
    assert plan_text.count('id="M1" order="1" status="completed"') == 1
    assert spec_text.count('status="completed"') == 1
    status = engine.status()
    assert status.current_module_id == "M2"
    assert "- login API" in plan_text
