from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..errors import SpecDrivenError
from ..models import Event
from ._core_bridge import emit_to_core
from .claude_code import normalize_bash_result, normalize_confirmation, normalize_session_start


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    response: Mapping[str, object]
    emitted: tuple[Event | object, ...]


def dispatch(payload: Mapping[str, object], project_root: Path, env: Mapping[str, str]) -> HookResult:
    del project_root
    hook_name = str(payload.get("hook_event_name", ""))
    command = env.get("SPECDRIVEN_CONFIRMATION_COMMAND", "confirm-next")
    try:
        if hook_name == "SessionStart":
            emitted = (normalize_session_start(payload),)
            return HookResult(0, {"continue": True}, emitted)
        if hook_name in {"PostToolUse", "PostToolUseFailure"} and payload.get("tool_name") == "Bash":
            evidence = normalize_bash_result(payload, hook_name == "PostToolUse")
            return HookResult(0, {"continue": True}, (evidence,) if evidence else ())
        if hook_name == "UserPromptSubmit":
            confirmation = normalize_confirmation(payload, command)
            if confirmation is None:
                return HookResult(0, {
                    "continue": True,
                    "systemMessage": f"Spec-driven workflow requires explicit `{command}` after both test gates pass.",
                }, ())
            return HookResult(0, {"continue": True}, (confirmation,))
        return HookResult(0, {"continue": True}, ())
    except SpecDrivenError as error:
        return HookResult(2, {"continue": False, "stopReason": f"{error.code}: {error}"}, ())


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        json.dump({"continue": False, "stopReason": "EVENT_INVALID: stdin was not one JSON object"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    if not isinstance(payload, dict):
        json.dump({"continue": False, "stopReason": "EVENT_INVALID: hook payload must be an object"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    result = dispatch(payload, Path.cwd(), os.environ)
    codes = emit_to_core(result.emitted, os.environ)  # type: ignore[arg-type]
    failed = [code for code in codes if code != 0]
    response = dict(result.response)
    if failed:
        # Fail closed when the core rejects any forwarded item.
        response = {
            "continue": False,
            "stopReason": f"CORE_REJECTED: spec-driven core returned nonzero {failed}; "
            "run spec-driven status to inspect the gate",
        }
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")
    return result.exit_code if not failed else 1
