from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .adapters.generic import GenericAdapter
from .config import load_config
from .discovery import discover_documents, infer_test_commands
from .documents import builtin_registry
from .engine import CoreEngine
from .errors import SpecDrivenError
from .models import Checkpoint, Event, TestEvidence

def _fixture_root() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / "fixtures" / "markdown-project",  # source checkout
        here.parent / "fixtures" / "markdown-project",  # packaged inside the module (wheel)
        here.parents[1] / "fixtures" / "markdown-project",  # wheel data at site-packages
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


_FIXTURE_ROOT = _fixture_root()
_NEXT_MODULE_CONFIRMED = {
    "event_id": "confirm-1",
    "schema_version": 1,
    "session_id": "session-1",
    "type": "next_module_confirmed",
    "occurred_at": "t2",
    "source": "generic",
    "actor": "user",
    "module_id": "M1",
    "payload": {"confirmation": "explicit_command"},
}


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    remediation: str | None


def run_doctor(project_root: Path, host: str) -> tuple[DoctorCheck, ...]:
    checks: list[DoctorCheck] = []
    try:
        config = load_config(project_root)
        checks.append(DoctorCheck("configuration", "pass", "schema version 1 loaded", None))
    except SpecDrivenError as error:
        checks.append(
            DoctorCheck(
                "configuration",
                "fail",
                f"{error.code}: {error}",
                "check spec-driven.config.yaml",
            )
        )
        return tuple(checks)
    except Exception as error:
        checks.append(
            DoctorCheck("configuration", "fail", str(error), "check spec-driven.config.yaml")
        )
        return tuple(checks)
    try:
        discover_documents(project_root, config, builtin_registry())
        checks.append(DoctorCheck("document_discovery", "pass", "one spec and one plan selected", None))
    except SpecDrivenError as error:
        checks.append(
            DoctorCheck(
                "document_discovery",
                "fail",
                f"{error.code}: {error}",
                "set spec.paths and plan.paths in spec-driven.config.yaml",
            )
        )
    except Exception as error:
        checks.append(
            DoctorCheck(
                "document_discovery",
                "fail",
                str(error),
                "set spec.paths and plan.paths in spec-driven.config.yaml",
            )
        )
    try:
        infer_test_commands(project_root, config)
        checks.append(DoctorCheck("test_commands", "pass", "unit and regression commands configured", None))
    except SpecDrivenError as error:
        checks.append(
            DoctorCheck("test_commands", "fail", str(error), "configure tests.unit.command and tests.regression.command")
        )
    except Exception as error:
        checks.append(
            DoctorCheck("test_commands", "fail", str(error), "configure tests.unit.command and tests.regression.command")
        )
    checks.append(DoctorCheck("host_adapter", "pass" if host in {"generic", "claude-code", "codex"} else "warn", host, None))
    return tuple(checks)


def run_self_test(work_root: Path) -> dict[str, object]:
    root = work_root / "self-test"
    try:
        shutil.copytree(_FIXTURE_ROOT, root)
        engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
        engine.start()
        engine.start_module(Event("start-1", 1, "session-1", "module_started", "t0", "core", "agent", "M1", {}))
        engine.record_test("unit-1", TestEvidence("unit", "M1", "unit", ".", "t0", "t1", 0, None, "", 1))
        engine.record_test("reg-1", TestEvidence("regression", "M1", "regression", ".", "t0", "t1", 0, None, "", 1))
        engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("done",), ("note",)))
        engine.confirm_next(GenericAdapter().normalize(_NEXT_MODULE_CONFIRMED))
        snapshot = engine.status()
        spec_text = (root / "docs" / "specs" / "product.md").read_text(encoding="utf-8")
        plan_text = (root / "docs" / "plans" / "product-plan.md").read_text(encoding="utf-8")
        return {
            "schema_version": 1,
            "status": "pass",
            "checks": {
                "gate": snapshot.current_module_id == "M2",
                "spec_updated": 'status="completed"' in spec_text,
                "plan_updated": 'status="completed"' in plan_text,
                "audit_event": (root / ".spec-driven" / "events" / "confirm-1-documents-updated.json").is_file(),
                "next_module": snapshot.current_module_id,
            },
        }
    except SpecDrivenError as error:
        return {
            "schema_version": 1,
            "status": "fail",
            "error_code": error.code,
            "error": str(error),
        }
    except OSError as error:
        return {
            "schema_version": 1,
            "status": "fail",
            "error_code": "SELF_TEST_SETUP_FAILED",
            "error": str(error),
        }
