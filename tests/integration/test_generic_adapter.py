import pytest

from spec_driven.adapters.generic import GenericAdapter
from spec_driven.errors import InvalidEventError


def raw(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "event_id": "e1",
        "schema_version": 1,
        "session_id": "s1",
        "type": "module_started",
        "occurred_at": "t0",
        "actor": "agent",
        "module_id": "M1",
        "payload": {},
    }
    base.update(overrides)
    return base


def test_normalize_builds_versioned_event() -> None:
    event = GenericAdapter().normalize(raw())
    assert event.source == "generic"
    assert event.schema_version == 1
    assert event.module_id == "M1"


def test_confirmation_requires_explicit_command_payload() -> None:
    with pytest.raises(InvalidEventError):
        GenericAdapter().normalize(raw(type="next_module_confirmed", actor="user", payload={"confirmation": "sounds right"}))


def test_confirmation_with_explicit_command_passes() -> None:
    event = GenericAdapter().normalize(raw(type="next_module_confirmed", actor="user", payload={"confirmation": "explicit_command"}))
    assert event.type == "next_module_confirmed"


def test_payload_must_be_mapping() -> None:
    with pytest.raises(InvalidEventError):
        GenericAdapter().normalize(raw(payload="natural language"))
