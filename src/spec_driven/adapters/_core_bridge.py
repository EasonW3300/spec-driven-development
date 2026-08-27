from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping

import spec_driven.models as _models
from ..errors import SpecDrivenError
from ..models import Event
from .claude_code import normalize_bash_result, normalize_confirmation, normalize_session_start


def _core_command(root: Path, *arguments: str) -> list[str]:
    return [sys.executable, "-m", "spec_driven.cli", "--project", str(root), *arguments]


def emit_to_core(emitted: tuple[Event | "_models.TestEvidence", ...], env: Mapping[str, str]) -> list[int]:
    """Forward normalized items to the installed core CLI; returns child exit codes."""
    del env
    codes: list[int] = []
    for item in emitted:
        if isinstance(item, Event):
            if item.type == "next_module_confirmed":
                stdin_payload = json.dumps({
                    "event_id": item.event_id.replace(":", "-").replace("_", "-")[:120],
                    "schema_version": item.schema_version,
                    "session_id": item.session_id,
                    "type": item.type,
                    "occurred_at": item.occurred_at,
                    "source": "generic",
                    "actor": item.actor,
                    "module_id": item.module_id,
                    "payload": dict(item.payload),
                })
                arguments = ("confirm-next", "--input", "-")
            else:
                continue  # lifecycle-only events carry no core state transition today
        else:
            stdin_payload = json.dumps({
                "event_id": f"{item.module_id}-{item.kind}-{item.finished_at}".replace(":", "-"),
                "evidence": {
                    "kind": item.kind,
                    "module_id": item.module_id,
                    "command": item.command,
                    "working_directory": item.working_directory,
                    "started_at": item.started_at,
                    "finished_at": item.finished_at,
                    "exit_code": item.exit_code,
                    "output_path": item.output_path,
                    "output_summary": item.output_summary,
                    "attempt": item.attempt,
                },
            })
            arguments = ("record-test", "--input", "-")
        code = subprocess.run(
            _core_command(Path.cwd(), *arguments),
            input=stdin_payload,
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        codes.append(code)
    return codes
