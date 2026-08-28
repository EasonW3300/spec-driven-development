from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Callable

from .adapters.generic import GenericAdapter
from .capabilities import load_host_manifest
from .config import load_config
from .discovery import discover_documents, infer_test_commands
from .documents import builtin_registry
from .engine import CoreEngine
from .errors import SpecDrivenError
from .install import (
    InstallReceipt,
    TomlInstallReceipt,
    apply_install,
    copy_assets,
    merge_toml_fragment,
    plan_install,
    rollback_install,
    rollback_toml,
    verify_receipt,
)
from .migrate import MigrationRegistry, migrate_file
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
    registry = builtin_registry()
    modules = registry.for_path(root / plan.path, config.document_adapters).parse_modules(root / plan.path)
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


def _install(args: argparse.Namespace) -> int:
    root = Path.home() if args.scope == "user" else Path.cwd()
    manifest_path = Path(__file__).resolve().parents[2] / "install" / "manifests" / f"{args.host}.json"
    manifest = load_host_manifest(manifest_path)
    source_root = manifest_path.parents[2]
    plan = plan_install(manifest, root, source_root)
    if args.dry_run:
        _emit({"host": args.host, "scope": args.scope, "settings_target": str(plan.settings_target), "dry_run": True})
        return 0
    if args.host == "codex":
        receipt = merge_toml_fragment(plan.settings_target, manifest.settings_fragment)
        copy_assets(source_root, root / ".codex")
        payload = {
            "kind": "toml",
            "backup_path": str(receipt.backup_path) if receipt.backup_path is not None else None,
            "target": str(receipt.target),
            "applied_keys": list(receipt.applied_keys),
        }
    else:
        backup_dir = root / ".spec-driven" / "install-receipts" / ".backups"
        receipt = apply_install(plan, backup_dir)
        payload = {
            "kind": "json",
            "backup_dir": str(receipt.backup_dir),
            "target": str(receipt.target),
            "backup_file": str(receipt.backup_file) if receipt.backup_file is not None else None,
        }
    receipt_dir = root / ".spec-driven" / "install-receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / f"{args.host}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _emit({"host": args.host, "scope": args.scope, "settings_target": str(plan.settings_target), "installed": True})
    return 0


def _uninstall(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    receipt_path = Path(args.receipt)
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        kind = payload.get("kind")
        if kind == "json":
            receipt = InstallReceipt(
                backup_dir=Path(payload["backup_dir"]),
                target=Path(payload["target"]),
                backup_file=Path(payload["backup_file"]) if payload.get("backup_file") else None,
            )
            verify_receipt(receipt, root)
            rollback_install(receipt)
        elif kind == "toml":
            receipt = TomlInstallReceipt(
                backup_path=Path(payload["backup_path"]) if payload.get("backup_path") else None,
                target=Path(payload["target"]),
                applied_keys=tuple(payload.get("applied_keys") or ()),
            )
            for candidate in (receipt.target, receipt.backup_path):
                if candidate is None:
                    continue
                resolved = candidate.resolve()
                if resolved != root and root not in resolved.parents:
                    raise ValueError(f"path escapes target root: {candidate}")
            rollback_toml(receipt)
        else:
            raise CliInputError(f"unknown receipt kind: {kind!r}")
    except ValueError as error:
        raise CliInputError(str(error)) from error
    receipt_path.unlink(missing_ok=True)
    return 0


def _migrate(args: argparse.Namespace) -> int:
    project = Path(args.project)
    backup_dir = project / ".spec-driven" / "migration-backups"
    registry = MigrationRegistry()
    target_version = args.target_version
    dry_run = args.dry_run

    found: list[tuple[Path, str]] = []
    state_path = project / ".spec-driven" / "state.json"
    if state_path.is_file():
        found.append((state_path, "state"))
    config_path = project / "spec-driven.config.json"
    if config_path.is_file():
        found.append((config_path, "config"))

    for candidate in (project / "spec-driven.config.yaml", project / "spec-driven.config.toml"):
        if candidate.is_file() and not config_path.is_file():
            _emit(
                {
                    "path": str(candidate),
                    "kind": "config",
                    "skipped": "non-json-config",
                    "message": "migrations apply to JSON machine documents only",
                }
            )

    if not found:
        _emit({"project": str(project), "target_version": target_version, "migrated": [], "dry_run": dry_run})
        return 0

    try:
        if dry_run:
            for path, kind in found:
                document = json.loads(path.read_text(encoding="utf-8"))
                _emit(
                    {
                        "path": str(path),
                        "kind": kind,
                        "current_version": int(document.get("schema_version", 0)),
                        "target_version": target_version,
                        "dry_run": True,
                    }
                )
            return 0
        for path, kind in found:
            migrate_file(path, kind, target_version, backup_dir, registry)
            _emit({"path": str(path), "kind": kind, "migrated": True})
        return 0
    except ValueError as error:
        raise CliInputError(str(error)) from error


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
    parser_install = subparsers.add_parser("install", parents=[common])
    parser_install.add_argument("--host", choices=("claude-code", "codex"), default="claude-code")
    parser_install.add_argument("--scope", choices=("user", "project"), default="user")
    parser_install.add_argument("--dry-run", action="store_true")
    parser_uninstall = subparsers.add_parser("uninstall", parents=[common])
    parser_uninstall.add_argument("--receipt", required=True)
    parser_uninstall.add_argument("--root", default=".")
    parser_migrate = subparsers.add_parser("migrate", parents=[common])
    parser_migrate.add_argument("--target-version", type=int, required=True)
    parser_migrate.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "doctor":
            _emit(doctor(arguments.project))
            return 0
        if arguments.command == "install":
            return _install(arguments)
        if arguments.command == "uninstall":
            return _uninstall(arguments)
        if arguments.command == "migrate":
            return _migrate(arguments)
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
