from __future__ import annotations

from collections.abc import Mapping

from ..errors import InvalidEventError
from ..models import Event


class GenericAdapter:
    def normalize(self, raw: Mapping[str, object]) -> Event:
        payload = raw.get("payload")
        if not isinstance(payload, Mapping):
            raise InvalidEventError("event payload must be a mapping")
        event = Event(
            event_id=str(raw.get("event_id", "")),
            schema_version=int(raw.get("schema_version", 0)),  # type: ignore[arg-type]
            session_id=str(raw.get("session_id", "")),
            type=str(raw.get("type", "")),
            occurred_at=str(raw.get("occurred_at", "")),
            source="generic",
            actor=str(raw.get("actor", "")),
            module_id=str(raw["module_id"]) if raw.get("module_id") is not None else None,
            payload=dict(payload),
        )
        if event.type == "next_module_confirmed" and event.payload.get("confirmation") != "explicit_command":
            raise InvalidEventError("generic confirmation requires explicit_command")
        return event
