from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Callable

from .adapters.generic import GenericAdapter
from .config import load_config
from .discovery import discover_documents, infer_test_commands
from .documents.markdown import MarkdownAdapter
from .engine import CoreEngine
from .errors import SpecDrivenError
from .models import Checkpoint, Event, TestEvidence


class CliInputError(SpecDrivenError):
    code = "CLI_INPUT_INVALID"


def _read_payload(name: str, *, allow_empty: bool = False) -> dict[str, object]:
    text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
    if allow_empty and not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except ValueError as error:
        raise CliInputError(f"structured input is not valid JSON: {error}") from error
    if not isinstance(loaded, dict):
        raise CliInputError("structured input root must be a JSON object")
    return loaded


def doctor(project: str) -> dict[str, object]:
    root = Path(project)
    config = load_config(root)
    spec, plan = discover_documents(root, config)
    modules = MarkdownAdapter().parse_modules(root / plan.path)
    unit, regression = infer_test_commands(root, config)
    return {
        "status": "ok",
        "documents": {"spec": spec.path, "plan": plan.path},
        "modules": [module.module_id for module in modules],
        "tests": {"unit": unit, "regression": regression},
    }


def _jsonable(value: object) -> object:
    if isinstance(value, frozenset | set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _emit(value: object) -> None:
    if is_dataclass(value):
        value = asdict(value)  # type: ignore[arg-type]
    json.dump(_jsonable(value), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _error(error: SpecDrivenError) -> int:
    json.dump(
        {"code": error.code, "message": str(error), "retryable": error.retryable, "remediation": error.remediation},
        sys.stdout,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 1


def _handlers(engine: CoreEngine, payload: dict[str, object]) -> dict[str, Callable[[], object]]:
    return {
        "start": engine.start,
        "status": engine.status,
        "start-module": lambda: engine.start_module(Event(**payload)),  # type: ignore[arg-type]
        "record-test": lambda: engine.record_test(str(payload["event_id"]), TestEvidence(**payload["evidence"])),  # type: ignore[arg-type]
        "checkpoint": lambda: engine.record_checkpoint(str(payload["event_id"]), Checkpoint(**payload["checkpoint"])),  # type: ignore[arg-type]
        "confirm-next": lambda: engine.confirm_next(GenericAdapter().normalize(payload)),
        "recover": engine.recover,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spec-driven", description="Host-neutral spec-driven development core")
    parser.add_argument("--project", default=".", help="project root directory")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS, help="project root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    structured = ("start", "status", "start-module", "record-test", "checkpoint", "confirm-next", "recover")
    for name in structured:
        subparser = subparsers.add_parser(name, parents=[common])
        if name in {"start-module", "record-test", "checkpoint", "confirm-next"}:
            subparser.add_argument("--input", default="-", help="JSON input path or '-' for stdin")
        elif name in {"start"}:
            subparser.add_argument("--input", default="-", help='optional session JSON ({"session_id": ...}) or "-" for stdin')
    subparsers.add_parser("doctor", parents=[common])
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "doctor":
            _emit(doctor(arguments.project))
            return 0
        engine = CoreEngine.from_project(Path(arguments.project))
        needs_input = arguments.command not in {"status", "recover"}
        payload = (
            _read_payload(arguments.input, allow_empty=arguments.command == "start")
            if needs_input and hasattr(arguments, "input")
            else {}
        )
        handler = _handlers(engine, payload)[arguments.command]
        result = handler()
        _emit(result)
        return 0
    except SpecDrivenError as error:
        if error.code == "CLI_INPUT_INVALID":
            _error(error)
            return 2
        return _error(error)


if __name__ == "__main__":
    raise SystemExit(main())
