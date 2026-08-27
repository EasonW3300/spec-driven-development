import dataclasses

import pytest

from spec_driven import models


def _sample(value_type: type) -> object:
    kwargs = {
        "kind": "spec",
        "path": "docs/specs/product.md",
        "sha256": "abc",
        "module_id": "M1",
        "command": "pytest",
        "working_directory": ".",
        "started_at": "t0",
        "finished_at": "t1",
        "exit_code": 0,
        "output_path": None,
        "output_summary": "",
        "attempt": 1,
        "checkpoint_id": "cp-1",
        "completed_points": (),
        "notes": (),
        "event_id": "evt-1",
        "schema_version": 1,
        "session_id": "s",
        "type": "test_finished",
        "occurred_at": "t0",
        "source": "test",
        "actor": "host",
        "payload": {},
    }
    fields = dataclasses.fields(value_type)
    return value_type(**{f.name: kwargs[f.name] for f in fields})


def test_all_domain_values_are_frozen() -> None:
    for value_type in (
        models.DocumentRef,
        models.TestEvidence,
        models.Checkpoint,
        models.Event,
    ):
        instance = _sample(value_type)
        with pytest.raises(AttributeError):
            setattr(instance, dataclasses.fields(value_type)[0].name, None)


def test_event_requires_explicit_confirmation_payload_shape() -> None:
    event = models.Event(
        event_id="evt-2",
        schema_version=1,
        session_id="s",
        type="next_module_confirmed",
        occurred_at="t0",
        source="generic",
        actor="user",
        module_id="M1",
        payload={"confirmation": "explicit_command"},
    )
    assert event.payload["confirmation"] == "explicit_command"
