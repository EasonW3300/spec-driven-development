from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from .errors import InvalidEventError
from .models import Event


def validate_event(event: Event) -> None:
    required = (event.event_id, event.session_id, event.type, event.occurred_at, event.source, event.actor)
    if event.schema_version != 1 or any(not value for value in required):
        raise InvalidEventError("event requires schema_version 1 and all identity fields")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", event.event_id) is None:
        raise InvalidEventError("event_id contains unsafe characters")
    if event.type == "next_module_confirmed":
        if event.actor != "user" or event.payload.get("confirmation") != "explicit_command":
            raise InvalidEventError("confirmation requires user actor and explicit_command payload")


class EventStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> bool:
        validate_event(event)
        path = self.directory / f"{event.event_id}.json"
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(asdict(event), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
            return True
        except FileExistsError:
            return False

    def read(self, event_id: str) -> Event:
        return Event(**json.loads((self.directory / f"{event_id}.json").read_text(encoding="utf-8")))

    def all(self) -> tuple[Event, ...]:
        return tuple(self.read(path.stem) for path in sorted(self.directory.glob("*.json")))
