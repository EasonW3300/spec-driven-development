from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ..capabilities import Capability, CapabilityReport
from ..errors import InvalidEventError
from ..models import Event


class CodexCapabilities:
    @staticmethod
    def detect(environment: Mapping[str, str], config_path: Path) -> CapabilityReport:
        del environment  # detection is driven by the Codex config file, not process env
        configured = False
        if config_path.is_file():
            try:
                import tomllib

                with config_path.open("rb") as handle:
                    config = tomllib.load(handle)
                configured = bool(config.get("notify"))
            except Exception:  # malformed user TOML is a degradation, not a crash
                configured = False
        status = "available" if configured else "degraded"
        return CapabilityReport(
            schema_version=1,
            host="codex",
            adapter_version="0.1.0",
            capabilities=(
                Capability("session_events", status, "notify external program", "turn lifecycle is observable", "install notify bridge"),
                Capability("bash_exit_status", "unavailable", "no per-tool hook in Codex", "core CLI must execute tests itself", "run tests via spec-driven gate"),
                Capability("explicit_confirmation", status, "custom prompt exact command", "only confirm-next can authorize", "use the generic CLI command"),
                Capability("document_update", status, "local core CLI", "core gate controls writes", "run spec-driven doctor"),
            ),
        )


def _required(payload: Mapping[str, object], *keys: str) -> list[object]:
    values = [payload.get(key) for key in keys]
    if any(value in (None, "") for value in values):
        raise InvalidEventError(f"Codex notify payload is missing: {keys}")
    return values


def _safe_event_id(raw: str) -> str:
    """Event ids double as event file names under .spec-driven/events/, so keep them inside the core's whitelist."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw)
    return cleaned[:128].strip("-") or "evt"


def normalize_notify_event(payload: Mapping[str, object]) -> Event | None:
    kind = str(payload.get("type", ""))
    if kind != "agent-turn-complete":
        return None
    session_id, occurred_at = _required(payload, "session_id", "timestamp")
    return Event(
        event_id=_safe_event_id(f"{session_id}-turn-completed-{occurred_at}"),
        schema_version=1,
        session_id=str(session_id),
        type="session_turn_completed",
        occurred_at=str(occurred_at),
        source="codex",
        actor="host",
        module_id=None,
        payload={"cwd": str(payload.get("cwd", ""))},
    )


def parse_explicit_confirmation(prompt: str, command: str) -> bool:
    return bool(re.fullmatch(re.escape(command), prompt.strip()))


def normalize_confirmation(payload: Mapping[str, object], command: str) -> Event | None:
    prompt = str(payload.get("prompt", ""))
    if not parse_explicit_confirmation(prompt, command):
        return None
    session_id, module_id, occurred_at = _required(payload, "session_id", "module_id", "timestamp")
    return Event(
        event_id=_safe_event_id(f"{session_id}-confirm-{module_id}-{occurred_at}"),
        schema_version=1,
        session_id=str(session_id),
        type="next_module_confirmed",
        occurred_at=str(occurred_at),
        source="codex",
        actor="user",
        module_id=str(module_id),
        payload={"confirmation": "explicit_command"},
    )
