from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import spec_driven.models as _models
from spec_driven.adapters.claude_code_hook import dispatch
from spec_driven.engine import CoreEngine
from spec_driven.errors import GateBlockedError
from spec_driven.models import Checkpoint

def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def _prepared(tmp_path: Path) -> tuple[CoreEngine, Path]:
    root = _project(tmp_path)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_models.Event("start-1", 1, "session-1", "module_started", "t0", "claude-code", "agent", "M1", {}))
    engine.record_test("unit-1", _models.TestEvidence("unit", "M1", "unit", ".", "t0", "t1", 0, None, "", 1))
    engine.record_test("reg-1", _models.TestEvidence("regression", "M1", "regression", ".", "t0", "t1", 0, None, "", 1))
    return engine, root


def test_failed_bash_evidence_keeps_module_in_testing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(_models.Event("start-1", 1, "session-1", "module_started", "t0", "claude-code", "agent", "M1", {}))
    engine.record_test("unit-1", _models.TestEvidence("unit", "M1", "unit", ".", "t0", "t1", 0, None, "", 1))
    engine.record_test("reg-1", _models.TestEvidence("regression", "M1", "regression", ".", "t0", "t1", 1, None, "", 1))
    with pytest.raises(GateBlockedError):
        engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("MVP works",), ()))
    assert engine.status().module_states["M1"] == "testing"


def test_natural_language_hook_leaves_documents_unchanged(tmp_path: Path) -> None:
    engine, root = _prepared(tmp_path)
    before_spec = (root / "docs/specs/product.md").read_bytes()
    before_plan = (root / "docs/plans/product-plan.md").read_bytes()
    result = dispatch(
        {"hook_event_name": "UserPromptSubmit", "prompt": "可以，继续", "session_id": "session-1", "timestamp": "t", "module_id": "M1"},
        root,
        {},
    )
    assert result.emitted == ()
    assert (root / "docs/specs/product.md").read_bytes() == before_spec
    assert (root / "docs/plans/product-plan.md").read_bytes() == before_plan
    assert engine.status().current_module_id == "M1"


def test_confirmation_updates_documents_exactly_once_and_activates_next(tmp_path: Path) -> None:
    engine, root = _prepared(tmp_path)
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("MVP works",), ("reuse API",)))
    before_spec = (root / "docs/specs/product.md").read_bytes()

    hook_payload = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "confirm-next",
        "session_id": "session-1",
        "timestamp": "2026-08-26T00:02:00Z",
        "module_id": "M1",
    }
    normalized = dispatch(hook_payload, root, {}).emitted[0]
    first = engine.confirm_next(normalized)  # type: ignore[arg-type]
    after_first = (root / "docs/specs/product.md").read_bytes()
    assert after_first != before_spec

    # Replaying the identical hook input must deduplicate by event id.
    replay = dispatch(hook_payload, root, {}).emitted[0]
    second = engine.confirm_next(replay)  # type: ignore[arg-type]
    assert second == first
    assert (root / "docs/specs/product.md").read_bytes() == after_first
    plan_text = (root / "docs/plans/product-plan.md").read_text(encoding="utf-8")
    spec_text = (root / "docs/specs/product.md").read_text(encoding="utf-8")
    assert plan_text.count('id="M1" order="1" status="completed"') == 1
    assert spec_text.count('status="completed"') == 1
    assert engine.status().current_module_id == "M2"
    assert "- MVP works" in plan_text
