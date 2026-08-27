import shutil
from pathlib import Path

from spec_driven.adapters.claude_code_hook import dispatch

_ENV = {"SPECDRIVEN_CONFIRMATION_COMMAND": "confirm-next"}


def _project(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    before = {p: p.read_bytes() for p in sorted((root / "docs").rglob("*.md"))}
    return root, before


def test_dispatch_matrix_leaves_documents_byte_identical(tmp_path: Path) -> None:
    root, before = _project(tmp_path)
    payloads = [
        {"hook_event_name": "SessionStart", "session_id": "s", "timestamp": "t", "cwd": str(root)},
        {"hook_event_name": "PreToolUse", "session_id": "s"},
        {"hook_event_name": "UnknownEvent", "session_id": "s"},
        {"hook_event_name": "PostToolUse", "hook_name": "x", "tool_name": "Read"},  # non-Bash ignored
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "command": "pytest",
            "module_id": "M1",
            "test_kind": "unit",
            "exit_code": 0,
            "started_at": "t0",
            "finished_at": "t1",
            "session_id": "s",
        },
        {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "command": "pytest",
            "module_id": "M1",
            "test_kind": "regression",
            "exit_code": 1,
            "started_at": "t0",
            "finished_at": "t1",
            "session_id": "s",
        },
        {"hook_event_name": "UserPromptSubmit", "prompt": "可以，继续", "session_id": "s", "timestamp": "t", "module_id": "M1"},
    ]
    for payload in payloads:
        result = dispatch(payload, root, _ENV)
        assert result.exit_code == 0, payload
    after = {p: p.read_bytes() for p in before}
    assert after == before


def test_confirmation_via_hook_payload_shape(tmp_path: Path) -> None:
    root, _before = _project(tmp_path)
    result = dispatch(
        {"hook_event_name": "UserPromptSubmit", "prompt": "confirm-next", "session_id": "s", "timestamp": "t", "module_id": "M1"},
        root,
        _ENV,
    )
    assert result.emitted[0].type == "next_module_confirmed"
