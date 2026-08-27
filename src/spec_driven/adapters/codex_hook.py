from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import spec_driven.models as _models

from ..errors import SpecDrivenError
from ..models import Event, TestEvidence  # noqa: F401  (re-exported via HookResult typing)
from ._core_bridge import emit_to_core
from .codex import normalize_confirmation, normalize_notify_event


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    response: Mapping[str, object]
    emitted: tuple[Event | "_models.TestEvidence", ...]


def dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult:
    del project_root  # forwarding runs from the bridge process cwd; the core CLI takes --project itself
    kind = str(payload.get("type", ""))
    command = env.get("SPECDRIVEN_CONFIRMATION_COMMAND", "confirm-next")
    try:
        if kind == "user-prompt":
            confirmation = normalize_confirmation(payload, command)
            if confirmation is None:
                return HookResult(0, {
                    "status": "context",
                    "message": f"Spec-driven workflow requires explicit `{command}` after both test gates pass.",
                }, ())
            return HookResult(0, {"status": "ok"}, (confirmation,))
        event = normalize_notify_event(payload)
        if event is None:
            return HookResult(0, {"status": "ignored"}, ())
        return HookResult(0, {"status": "ok"}, (event,))
    except SpecDrivenError as error:
        return HookResult(2, {"status": "error", "reason": f"{error.code}: {error}"}, ())


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    try:
        payload = json.loads(raw_argv[0])
    except (IndexError, ValueError):
        json.dump({"status": "error", "reason": "missing or invalid JSON payload argument"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    result = dispatch(payload, Path.cwd(), os.environ)
    response = dict(result.response)
    if result.emitted:
        codes = emit_to_core(result.emitted, env=os.environ)
        rejected = [code for code in codes if code != 0]
        if rejected:
            # notify output controls nothing at runtime: report the refusal instead of
            # blocking the host, but never pretend the forward succeeded.
            response["status"] = "error"
            response["reason"] = f"CORE_REJECTED: forwarded item(s) exited {rejected}"
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")
    return result.exit_code
