from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from .errors import GateBlockedError, StateConflictError
from .models import Checkpoint, DocumentRef, StateSnapshot, TestEvidence


def _decode(raw: dict[str, object]) -> StateSnapshot:
    documents = tuple(DocumentRef(**item) for item in raw["documents"])  # type: ignore[arg-type]
    evidence = tuple(TestEvidence(**item) for item in raw["evidence"])  # type: ignore[arg-type]
    checkpoint_raw = raw.get("checkpoint")
    checkpoint = (
        Checkpoint(
            checkpoint_id=str(checkpoint_raw["checkpoint_id"]),
            module_id=str(checkpoint_raw["module_id"]),
            completed_points=tuple(checkpoint_raw["completed_points"]),  # type: ignore[index]
            notes=tuple(checkpoint_raw["notes"]),  # type: ignore[index]
        )
        if checkpoint_raw
        else None
    )
    return StateSnapshot(
        schema_version=int(raw["schema_version"]),  # type: ignore[arg-type]
        session_id=str(raw["session_id"]),
        session_state=raw["session_state"],  # type: ignore[arg-type]
        current_module_id=raw.get("current_module_id"),  # type: ignore[arg-type]
        module_order=tuple(raw["module_order"]),  # type: ignore[arg-type]
        module_states=dict(raw["module_states"]),  # type: ignore[call-arg]
        documents=documents,
        evidence=evidence,
        checkpoint=checkpoint,
        processed_event_ids=frozenset(raw["processed_event_ids"]),  # type: ignore[arg-type]
    )


class StateRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> StateSnapshot | None:
        if not self.path.is_file():
            return None
        return _decode(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, snapshot: StateSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(snapshot)
        payload["processed_event_ids"] = sorted(snapshot.processed_event_ids)
        fd, temporary = tempfile.mkstemp(prefix="state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _ensure_current(snapshot: StateSnapshot, module_id: str) -> None:
    if snapshot.current_module_id != module_id or snapshot.session_state != "active":
        raise StateConflictError(f"module is not current: {module_id}")


def _gate_passes(snapshot: StateSnapshot, module_id: str) -> bool:
    latest = {item.kind: item for item in snapshot.evidence if item.module_id == module_id}
    return all(kind in latest and latest[kind].exit_code == 0 for kind in ("unit", "regression"))


def start_module(snapshot: StateSnapshot, module_id: str, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    _ensure_current(snapshot, module_id)
    if snapshot.module_states[module_id] != "pending":
        raise StateConflictError("module can start only from pending")
    states = dict(snapshot.module_states)
    states[module_id] = "implementing"
    return replace(snapshot, module_states=states, processed_event_ids=snapshot.processed_event_ids | {event_id})


def record_test_result(snapshot: StateSnapshot, item: TestEvidence, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    _ensure_current(snapshot, item.module_id)
    if snapshot.module_states[item.module_id] not in {"implementing", "testing"}:
        raise StateConflictError("test result requires implementing or testing state")
    kept = tuple(value for value in snapshot.evidence if not (value.module_id == item.module_id and value.kind == item.kind))
    states = dict(snapshot.module_states)
    states[item.module_id] = "testing"
    return replace(snapshot, module_states=states, evidence=kept + (item,), processed_event_ids=snapshot.processed_event_ids | {event_id})


def record_checkpoint(snapshot: StateSnapshot, checkpoint: Checkpoint, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    _ensure_current(snapshot, checkpoint.module_id)
    if snapshot.module_states[checkpoint.module_id] != "testing" or not _gate_passes(snapshot, checkpoint.module_id):
        raise GateBlockedError("checkpoint requires passing unit and regression evidence")
    if not checkpoint.completed_points:
        raise StateConflictError("checkpoint requires at least one completed point")
    states = dict(snapshot.module_states)
    states[checkpoint.module_id] = "awaiting_confirmation"
    return replace(snapshot, module_states=states, checkpoint=checkpoint, processed_event_ids=snapshot.processed_event_ids | {event_id})


def complete_current_module(snapshot: StateSnapshot, event_id: str) -> StateSnapshot:
    if event_id in snapshot.processed_event_ids:
        return snapshot
    current = snapshot.current_module_id
    if current is None or snapshot.module_states[current] != "awaiting_confirmation" or snapshot.checkpoint is None:
        raise StateConflictError("current module is not awaiting confirmation")
    if not _gate_passes(snapshot, current):
        raise GateBlockedError("confirmation requires passing unit and regression evidence")
    states = dict(snapshot.module_states)
    states[current] = "completed"
    index = snapshot.module_order.index(current)
    next_id = snapshot.module_order[index + 1] if index + 1 < len(snapshot.module_order) else None
    return replace(
        snapshot,
        session_state="active" if next_id else "completed",
        current_module_id=next_id,
        module_states=states,
        checkpoint=None,
        processed_event_ids=snapshot.processed_event_ids | {event_id},
    )
