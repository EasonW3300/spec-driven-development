import shutil
from pathlib import Path

import pytest

from spec_driven.adapters.generic import GenericAdapter
from spec_driven.engine import CoreEngine
from spec_driven.models import Checkpoint, Event, TestEvidence

_PARAMS = [
    ("yaml-project", ".yaml"),
    ("json-project", ".json"),
]


@pytest.mark.parametrize("fixture,suffix", _PARAMS)
def test_structured_fixture_can_start_and_parse_modules(tmp_path: Path, fixture: str, suffix: str) -> None:
    root = tmp_path / "project"
    shutil.copytree(Path("fixtures") / fixture, root)
    snapshot = CoreEngine.from_project(root).start()
    assert snapshot.current_module_id == "M1"
    assert snapshot.module_states == {"M1": "pending", "M2": "pending"}
    assert snapshot.documents[0].path.endswith(suffix)
    assert snapshot.documents[1].path.endswith(suffix)


@pytest.mark.parametrize("fixture", ["yaml-project", "json-project"])
def test_structured_fixture_runs_full_gated_transaction(tmp_path: Path, fixture: str) -> None:
    root = tmp_path / "project"
    shutil.copytree(Path("fixtures") / fixture, root)
    engine = CoreEngine.from_project(root, session_id_factory=lambda: "session-1")
    engine.start()
    engine.start_module(Event("start-1", 1, "session-1", "module_started", "t0", "core", "agent", "M1", {}))
    engine.record_test("unit-1", TestEvidence("unit", "M1", "unit", ".", "t0", "t1", 0, None, "", 1))
    engine.record_test("reg-1", TestEvidence("regression", "M1", "regression", ".", "t0", "t1", 0, None, "", 1))
    engine.record_checkpoint("cp-event", Checkpoint("cp1", "M1", ("done",), ("note",)))
    before = (root / "docs/plan.yaml" if "yaml" in fixture else root / "docs/plan.json").read_bytes()
    engine.confirm_next(
        GenericAdapter().normalize(
            {
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
        )
    )
    assert engine.status().current_module_id == "M2"
    assert engine.status().module_states["M1"] == "completed"
    after = (root / "docs/plan.yaml" if "yaml" in fixture else root / "docs/plan.json").read_bytes()
    assert after != before
