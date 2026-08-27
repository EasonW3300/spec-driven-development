from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ..capabilities import Capability, CapabilityReport
from ..errors import InvalidEventError
from ..models import Event, TestEvidence


class ClaudeCodeCapabilities:
    @staticmethod
    def detect(environment: Mapping[str, str], settings_path: Path | None = None) -> CapabilityReport:
        del environment  # hook availability is resolved from the installed settings file
        configured = bool(settings_path and settings_path.is_file() and "spec-driven" in settings_path.read_text(encoding="utf-8"))
        status = "available" if configured else "degraded"
        return CapabilityReport(
            schema_version=1,
            host="claude-code",
            adapter_version="0.1.0",
            capabilities=(
                Capability("session_events", status, "SessionStart hook", "session lifecycle is observable", "install SessionStart hook"),
                Capability("bash_exit_status", status, "PostToolUse/PostToolUseFailure Bash matcher", "real Bash exit code can be recorded", "install Bash matchers"),
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
    del session_id
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
