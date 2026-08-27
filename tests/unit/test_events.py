from pathlib import Path

import pytest

from spec_driven.errors import InvalidEventError
from spec_driven.events import EventStore, validate_event
from spec_driven.models import Event


def event(event_id: str = "e1", **overrides: object) -> Event:
    defaults: dict[str, object] = {
        "event_id": event_id,
        "schema_version": 1,
        "session_id": "s1",
        "type": "module_started",
        "occurred_at": "t0",
        "source": "test",
        "actor": "agent",
        "module_id": "M1",
        "payload": {},
    }
    return Event(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_validate_accepts_well_formed_event() -> None:
    validate_event(event())


def test_validate_rejects_wrong_schema_version() -> None:
    with pytest.raises(InvalidEventError):
        validate_event(event(schema_version=2))


def test_validate_rejects_unsafe_event_id() -> None:
    with pytest.raises(InvalidEventError):
        validate_event(event(event_id="../escape"))


def test_confirmation_requires_user_actor_and_explicit_command() -> None:
    with pytest.raises(InvalidEventError):
        validate_event(event(type="next_module_confirmed", actor="agent", payload={"confirmation": "explicit_command"}))
    with pytest.raises(InvalidEventError):
        validate_event(event(type="next_module_confirmed", actor="user", payload={}))


def test_duplicate_event_id_is_not_rewritten(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events")
    assert store.append(event()) is True
    assert store.append(event()) is False


def test_read_and_all_round_trip_events(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events")
    first = event("e1")
    second = event("e2")
    third = event("e3")
    for item in (third, first, second):
        store.append(item)
    assert store.read("e2") == second
    assert store.all() == (first, second, third)
