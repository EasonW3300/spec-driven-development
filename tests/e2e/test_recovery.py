from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import spec_driven.models as _models
from spec_driven.engine import CoreEngine
from spec_driven.errors import DocumentConflictError
from spec_driven.models import Checkpoint, Event


def _prepared(tmp_path: Path) -> tuple[CoreEngine, Path]:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_event("start-1", "module_started"))
    engine.record_test("unit-1", _models.TestEvidence("unit", "M1", "unit", ".", "t0", "t1", 0, None, "", 1))
    engine.record_test("reg-1", _models.TestEvidence("regression", "M1", "regression", ".", "t0", "t1", 0, None, "", 1))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("MVP works",), ("reuse API",)))
    return engine, root


def _event(event_id: str, event_type: str, actor: str = "agent") -> Event:
    return Event(
        event_id,
        1,
        "session-1",
        event_type,
        "2026-08-26T00:00:00Z",
        "generic",
        actor,
        "M1",
        {"confirmation": "explicit_command"} if event_type == "next_module_confirmed" else {},
    )


def test_save_state_failure_rolls_back_documents_and_retry_commits_once(tmp_path: Path) -> None:
    engine, root = _prepared(tmp_path)
    confirmation = _event("confirm-1", "next_module_confirmed", "user")
    original_spec = (root / "docs/specs/product.md").read_bytes()
    original_plan = (root / "docs/plans/product-plan.md").read_bytes()

    repository_save = engine.state_repository.save
    attempts: list[int] = []

    def failing_save(snapshot: object) -> None:
        if not attempts:
            attempts.append(1)
            raise RuntimeError("state failed")
        repository_save(snapshot)  # type: ignore[arg-type]

    engine.state_repository.save = failing_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        engine.confirm_next(confirmation)
    journal_path = root / ".spec-driven/transactions/confirm-1/journal.json"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["status"] == "rolled_back"
    assert (root / "docs/specs/product.md").read_bytes() == original_spec
    assert (root / "docs/plans/product-plan.md").read_bytes() == original_plan

    engine.state_repository.save = repository_save  # type: ignore[method-assign]
    engine.recover()
    engine.confirm_next(confirmation)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "committed"
    assert 'status="completed"' in (root / "docs/specs/product.md").read_text(encoding="utf-8")


def test_external_edit_after_patch_planning_conflicts_without_overwrite(tmp_path: Path) -> None:
    engine, root = _prepared(tmp_path)
    plan_path = root / "docs/plans/product-plan.md"
    plan_path.write_text("externally edited\n", encoding="utf-8")
    plan_before = plan_path.read_bytes()
    spec_before = (root / "docs/specs/product.md").read_bytes()
    with pytest.raises(DocumentConflictError):
        engine.confirm_next(_event("confirm-ext", "next_module_confirmed", "user"))
    assert plan_path.read_bytes() == plan_before
    assert (root / "docs/specs/product.md").read_bytes() == spec_before


def test_recovery_flags_incomplete_transaction_and_clears_when_resolved(tmp_path: Path) -> None:
    from spec_driven.errors import RecoveryRequiredError

    engine, root = _prepared(tmp_path)
    journal_path = root / ".spec-driven/transactions/confirm-1/journal.json"

    # A crash between "documents applied" and state save leaves an ambiguous state.
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text(json.dumps({"schema_version": 1, "status": "documents_applied", "paths": ["docs/specs/product.md"]}), encoding="utf-8")
    with pytest.raises(RecoveryRequiredError):
        engine.recover()

    # Once resolved (rolled back), recovery returns the live snapshot.
    _rewrite_journal(journal_path, {"schema_version": 1, "status": "rolled_back"})
    assert engine.recover() == engine.status()


def _rewrite_journal(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

