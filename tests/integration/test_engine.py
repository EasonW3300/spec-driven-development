import shutil
from pathlib import Path

import pytest

from spec_driven.engine import CoreEngine
from spec_driven.errors import GateBlockedError
from spec_driven.models import Checkpoint, Event
import spec_driven.models as _models


def event(event_id: str, event_type: str, actor: str = "agent") -> Event:
    return Event(event_id, 1, "session-1", event_type, "2026-08-26T00:00:00Z", "generic", actor, "M1", {"confirmation": "explicit_command"} if event_type == "next_module_confirmed" else {})


def evidence(kind: str, code: int = 0) -> "_models.TestEvidence":
    return _models.TestEvidence(kind, "M1", kind, ".", "t0", "t1", code, None, "summary", 1)


def prepared_engine(root: Path) -> CoreEngine:
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(event("start-1", "module_started"))
    engine.record_test("unit-1", evidence("unit"))
    engine.record_test("reg-1", evidence("regression"))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("state works",), ("reuse API",)))
    return engine


def gated_engine(tmp_path: Path) -> tuple[CoreEngine, Path]:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(event("start-1", "module_started"))
    engine.record_test("unit-1", evidence("unit"))
    return engine, root


def test_engine_updates_both_documents_only_after_gate(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    engine = prepared_engine(root)
    engine.confirm_next(event("confirm-1", "next_module_confirmed", "user"))
    assert 'status="completed"' in (root / "docs/specs/product.md").read_text(encoding="utf-8")
    assert 'status="completed"' in (root / "docs/plans/product-plan.md").read_text(encoding="utf-8")
    assert engine.status().current_module_id == "M2"


def test_checkpoint_blocked_until_regression_passes(tmp_path: Path) -> None:
    engine, _root = gated_engine(tmp_path)
    with pytest.raises(GateBlockedError):
        engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("state works",), ()))


def test_repeated_confirmation_event_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    engine = prepared_engine(root)
    confirmation = event("confirm-1", "next_module_confirmed", "user")
    first = engine.confirm_next(confirmation)
    spec_after_first = (root / "docs/specs/product.md").read_bytes()
    again = engine.confirm_next(confirmation)
    assert again.processed_event_ids == first.processed_event_ids
    assert (root / "docs/specs/product.md").read_bytes() == spec_after_first


def test_status_before_start_requires_start(tmp_path: Path) -> None:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    engine = CoreEngine.from_project(root)
    from spec_driven.errors import InvalidEventError

    with pytest.raises(InvalidEventError):
        engine.status()
