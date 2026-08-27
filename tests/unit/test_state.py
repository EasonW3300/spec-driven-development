from pathlib import Path

import pytest

import spec_driven.models as models
from spec_driven.errors import GateBlockedError, StateConflictError
from spec_driven.models import Checkpoint, DocumentRef, StateSnapshot
from spec_driven.state import (
    StateRepository,
    complete_current_module,
    record_checkpoint,
    record_test_result,
    start_module,
)


def snapshot() -> StateSnapshot:
    return StateSnapshot(1, "s1", "active", "M1", ("M1", "M2"), {"M1": "implementing", "M2": "pending"}, (DocumentRef("spec", "spec.md", "h"),), (), None, frozenset())


def evidence(kind: str, code: int = 0) -> "models.TestEvidence":
    return models.TestEvidence(kind, "M1", kind, ".", "t0", "t1", code, None, "summary", 1)


def test_snapshot_round_trip_preserves_nested_values(tmp_path: Path) -> None:
    repository = StateRepository(tmp_path / "state.json")
    repository.save(snapshot())
    assert repository.load() == snapshot()


def test_load_returns_none_for_missing_state_file(tmp_path: Path) -> None:
    assert StateRepository(tmp_path / "missing.json").load() is None


def test_duplicate_event_id_is_not_rewritten(tmp_path: Path) -> None:
    from spec_driven.events import EventStore
    from spec_driven.models import Event

    event = Event("e1", 1, "s1", "module_started", "t", "test", "agent", "M1", {})
    store = EventStore(tmp_path / "events")
    assert store.append(event) is True
    assert store.append(event) is False


def test_start_module_moves_pending_to_implementing() -> None:
    pending = snapshot()
    started = start_module(replace_states(pending, {"M1": "pending", "M2": "pending"}), "M1", "evt-start")
    assert started.module_states["M1"] == "implementing"


def replace_states(value: StateSnapshot, states: dict[str, str]) -> StateSnapshot:
    from dataclasses import replace as dataclass_replace

    return dataclass_replace(value, module_states=states)


def test_processed_event_ids_are_idempotent() -> None:
    once = record_test_result(snapshot(), evidence("unit"), "unit-1")
    twice = record_test_result(once, evidence("unit"), "unit-1")
    assert twice is once


def test_record_test_result_on_foreign_module_is_conflict() -> None:
    with pytest.raises(StateConflictError):
        record_test_result(snapshot(), models.TestEvidence("unit", "M2", "cmd", ".", "t0", "t1", 0, None, "", 1), "unit-9")


def test_failed_evidence_keeps_gate_closed() -> None:
    current = record_test_result(snapshot(), evidence("regression", code=1), "reg-1")
    current = record_test_result(current, evidence("unit"), "unit-1")
    with pytest.raises(GateBlockedError):
        record_checkpoint(current, Checkpoint("cp1", "M1", ("done",), ()), "cp-event")


def test_empty_checkpoint_is_rejected_after_passing_gates() -> None:
    current = record_test_result(snapshot(), evidence("unit"), "unit-1")
    current = record_test_result(current, evidence("regression"), "reg-1")
    with pytest.raises(StateConflictError):
        record_checkpoint(current, Checkpoint("cp1", "M1", (), ()), "cp-event")


def test_checkpoint_requires_both_passing_tests() -> None:
    current = record_test_result(snapshot(), evidence("unit"), "unit-1")
    with pytest.raises(GateBlockedError):
        record_checkpoint(current, Checkpoint("cp1", "M1", ("done",), ()), "cp-event")


def test_last_module_completion_finishes_session() -> None:
    current = snapshot()
    current = record_test_result(current, evidence("unit"), "unit-1")
    current = record_test_result(current, evidence("regression"), "reg-1")
    current = record_checkpoint(current, Checkpoint("cp1", "M1", ("done",), ()), "cp-event")
    completed = complete_current_module(current, "confirm-1")
    assert completed.module_states["M1"] == "completed"
    assert completed.current_module_id == "M2"
