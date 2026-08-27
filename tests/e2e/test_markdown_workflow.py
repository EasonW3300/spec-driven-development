from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import spec_driven.models as _models
from spec_driven.adapters.generic import GenericAdapter
from spec_driven.engine import CoreEngine
from spec_driven.errors import GateBlockedError, InvalidEventError
from spec_driven.models import Checkpoint, Event


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def _event(event_id: str, event_type: str, actor: str = "agent", module_id: str = "M1") -> Event:
    return Event(
        event_id,
        1,
        "session-1",
        event_type,
        "2026-08-26T00:00:00Z",
        "generic",
        actor,
        module_id,
        {"confirmation": "explicit_command"} if event_type == "next_module_confirmed" else {},
    )


def _evidence(kind: str, code: int) -> "_models.TestEvidence":
    return _models.TestEvidence(kind, "M1", kind, ".", "t0", "t1", code, None, "summary", 1)


@pytest.mark.parametrize(
    ("unit_code", "regression_code", "can_checkpoint"),
    [(0, 0, True), (1, 0, False), (0, 1, False)],
)
def test_two_test_gate(
    unit_code: int,
    regression_code: int,
    can_checkpoint: bool,
    tmp_path: Path,
) -> None:
    engine = CoreEngine.from_project(_root(tmp_path), session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_event("start-1", "module_started"))
    engine.record_test("unit-1", _evidence("unit", unit_code))
    engine.record_test("reg-1", _evidence("regression", regression_code))
    checkpoint = Checkpoint("cp1", "M1", ("MVP works",), ("reuse API",))
    if can_checkpoint:
        assert engine.record_checkpoint("cp-event", checkpoint).module_states["M1"] == "awaiting_confirmation"
    else:
        with pytest.raises(GateBlockedError):
            engine.record_checkpoint("cp-event", checkpoint)


def test_exact_confirmation_updates_both_documents_once(tmp_path: Path) -> None:
    root = _root(tmp_path)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_event("start-1", "module_started"))
    engine.record_test("unit-1", _evidence("unit", 0))
    engine.record_test("reg-1", _evidence("regression", 0))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("MVP works",), ("reuse API",)))
    confirmation = _event("confirm-1", "next_module_confirmed", "user")
    first = engine.confirm_next(confirmation)
    second = engine.confirm_next(confirmation)
    assert first == second
    assert first.current_module_id == "M2"
    for relative in ("docs/specs/product.md", "docs/plans/product-plan.md"):
        content = (root / relative).read_text(encoding="utf-8")
        assert content.count("Status: completed") == 1
        assert "- MVP works" in content
        assert "- reuse API" in content


def test_final_module_completion_ends_session_without_fabricated_module(tmp_path: Path) -> None:
    root = _root(tmp_path)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    for index in (1, 2):
        module_id = f"M{index}"
        engine.start_module(_event(f"start-{index}", "module_started", module_id=module_id))
        engine.record_test(f"unit-{index}", _models.TestEvidence("unit", module_id, "unit", ".", "t0", "t1", 0, None, "", 1))
        engine.record_test(f"reg-{index}", _models.TestEvidence("regression", module_id, "regression", ".", "t0", "t1", 0, None, "", 1))
        engine.record_checkpoint(f"cp-{index}", Checkpoint(f"cp-{index}", module_id, (f"{module_id} works",), ()))
        if index == 1:
            engine.confirm_next(_event(f"confirm-{index}", "next_module_confirmed", "user", module_id=module_id))
    final = engine.confirm_next(_event("confirm-2", "next_module_confirmed", "user", module_id="M2"))
    assert final.session_state == "completed"
    assert final.current_module_id is None


def test_natural_language_cannot_normalize_as_confirmation() -> None:
    adapter = GenericAdapter()
    with pytest.raises(InvalidEventError):
        adapter.normalize({
            "event_id": "e1",
            "schema_version": 1,
            "session_id": "session-1",
            "type": "next_module_confirmed",
            "occurred_at": "t",
            "actor": "user",
            "module_id": "M1",
            "payload": {"confirmation": "继续"},
        })
