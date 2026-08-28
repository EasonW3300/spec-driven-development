from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .config import load_config
from .discovery import discover_documents
from .documents import builtin_registry
from .errors import InvalidEventError, RecoveryRequiredError
from .events import EventStore, validate_event
from .models import Checkpoint, DocumentUpdate, Event, StateSnapshot, TestEvidence
from .patches import sha256
from .state import StateRepository, complete_current_module, record_checkpoint, record_test_result, start_module
from .transactions import apply_transaction


class CoreEngine:
    def __init__(self, project_root: Path, session_id_factory: Callable[[], str] | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = load_config(self.project_root)
        self.runtime = (self.project_root / self.config.state_dir).resolve()
        if self.project_root not in self.runtime.parents:
            raise InvalidEventError("runtime directory must be inside project")
        self.state_repository = StateRepository(self.runtime / "state.json")
        self.event_store = EventStore(self.runtime / "events")
        self.registry = builtin_registry()
        self.session_id_factory = session_id_factory or (lambda: uuid4().hex)

    @classmethod
    def from_project(cls, project_root: Path, session_id_factory: Callable[[], str] | None = None) -> "CoreEngine":
        return cls(project_root, session_id_factory)

    def status(self) -> StateSnapshot:
        snapshot = self.state_repository.load()
        if snapshot is None:
            raise InvalidEventError("session has not started", remediation="run spec-driven start")
        return snapshot

    def start(self) -> StateSnapshot:
        existing = self.state_repository.load()
        if existing is not None:
            return existing
        spec, plan = discover_documents(self.project_root, self.config)
        plan_path = self.project_root / plan.path
        adapter = self.registry.for_path(plan_path, self.config.document_adapters)
        modules = adapter.parse_modules(plan_path)
        snapshot = StateSnapshot(
            1,
            self.session_id_factory(),
            "active",
            modules[0].module_id,
            tuple(module.module_id for module in modules),
            {module.module_id: "pending" for module in modules},
            (spec, plan),
            (),
            None,
            frozenset(),
        )
        self.state_repository.save(snapshot)
        return snapshot

    def start_module(self, event: Event) -> StateSnapshot:
        snapshot = self.status()
        validate_event(event)
        updated = start_module(snapshot, event.module_id or "", event.event_id)
        if updated is not snapshot:
            self.event_store.append(event)
        self.state_repository.save(updated)
        return updated

    def record_test(self, event_id: str, item: TestEvidence) -> StateSnapshot:
        snapshot = self.status()
        updated = record_test_result(snapshot, item, event_id)
        if updated is not snapshot:
            self.event_store.append(Event(event_id, 1, snapshot.session_id, "test_finished", item.finished_at, "core", "host", item.module_id, {"kind": item.kind, "exit_code": item.exit_code}))
        self.state_repository.save(updated)
        return updated

    def record_checkpoint(self, event_id: str, checkpoint: Checkpoint) -> StateSnapshot:
        snapshot = self.status()
        updated = record_checkpoint(snapshot, checkpoint, event_id)
        if updated is not snapshot:
            self.event_store.append(Event(event_id, 1, snapshot.session_id, "checkpoint_recorded", "local", "core", "agent", checkpoint.module_id, {"checkpoint_id": checkpoint.checkpoint_id}))
        self.state_repository.save(updated)
        return updated

    def confirm_next(self, event: Event) -> StateSnapshot:
        snapshot = self.status()
        validate_event(event)
        if event.event_id in snapshot.processed_event_ids:
            return snapshot
        if event.session_id != snapshot.session_id or event.module_id != snapshot.current_module_id:
            raise InvalidEventError("confirmation session/module does not match current state")
        if snapshot.module_states.get(event.module_id or "") == "completed":
            return snapshot
        checkpoint = snapshot.checkpoint
        if checkpoint is None:
            raise InvalidEventError("confirmation requires checkpoint")
        previewed = complete_current_module(snapshot, event.event_id)
        latest = {item.kind: item for item in snapshot.evidence if item.module_id == event.module_id}
        update = DocumentUpdate(
            event.module_id or "",
            "completed",
            previewed.current_module_id,
            checkpoint.completed_points,
            checkpoint.notes,
            (
                f"unit: exit {latest['unit'].exit_code}",
                f"regression: exit {latest['regression'].exit_code}",
            ),
        )
        patches = tuple(
            self.registry.for_path(self.project_root / ref.path, self.config.document_adapters)
            .plan_update(self.project_root / ref.path, update, sha256(self.project_root / ref.path))
            for ref in snapshot.documents
        )
        self.event_store.append(event)
        apply_transaction(patches, self.runtime, event.event_id, lambda: self.state_repository.save(previewed))
        self.event_store.append(Event(f"{event.event_id}-documents-updated", 1, snapshot.session_id, "documents_updated", event.occurred_at, "core", "core", event.module_id, {"paths": [ref.path for ref in snapshot.documents]}))
        return previewed

    def recover(self) -> StateSnapshot:
        snapshot = self.status()
        incomplete = [
            path
            for path in sorted((self.runtime / "transactions").glob("*/journal.json"))
            if json.loads(path.read_text(encoding="utf-8"))["status"] == "documents_applied"
        ]
        if incomplete:
            raise RecoveryRequiredError("transaction requires explicit recovery", remediation=f"inspect {incomplete[0].parent}")
        return snapshot
