from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModuleState = Literal["pending", "implementing", "testing", "awaiting_confirmation", "completed"]
SessionState = Literal["active", "paused", "completed"]


@dataclass(frozen=True)
class Module:
    module_id: str
    title: str
    order: int
    goal: str
    prerequisites: tuple[str, ...]
    acceptance: tuple[str, ...]
    test_requirements: tuple[str, ...]


@dataclass(frozen=True)
class DocumentRef:
    kind: Literal["spec", "plan"]
    path: str
    sha256: str


@dataclass(frozen=True)
class TestEvidence:
    kind: Literal["unit", "regression"]
    module_id: str
    command: str
    working_directory: str
    started_at: str
    finished_at: str
    exit_code: int
    output_path: str | None
    output_summary: str
    attempt: int


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    module_id: str
    completed_points: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class DocumentUpdate:
    module_id: str
    status: str
    next_module_id: str | None
    completed_points: tuple[str, ...]
    notes: tuple[str, ...]
    evidence_summary: tuple[str, ...]


@dataclass(frozen=True)
class Event:
    event_id: str
    schema_version: int
    session_id: str
    type: str
    occurred_at: str
    source: str
    actor: str
    module_id: str | None
    payload: dict[str, object]


@dataclass(frozen=True)
class ProjectConfig:
    schema_version: int
    spec_paths: tuple[str, ...]
    plan_paths: tuple[str, ...]
    unit_test_command: str | None
    regression_test_command: str | None
    document_adapters: tuple[str, ...]
    host_adapter: str
    confirmation_command: str
    state_dir: str
    allow_module_inference: bool


@dataclass(frozen=True)
class StateSnapshot:
    schema_version: int
    session_id: str
    session_state: SessionState
    current_module_id: str | None
    module_order: tuple[str, ...]
    module_states: dict[str, ModuleState]
    documents: tuple[DocumentRef, ...]
    evidence: tuple[TestEvidence, ...]
    checkpoint: Checkpoint | None
    processed_event_ids: frozenset[str]
