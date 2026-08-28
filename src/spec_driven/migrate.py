from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Migration:
    kind: Literal["config", "state"]
    from_version: int
    to_version: int
    transform: Callable[[dict[str, object]], dict[str, object]]


class MigrationRegistry:
    def __init__(self) -> None:
        self._migrations: dict[tuple[str, int], Migration] = {}

    def register(self, migration: Migration) -> None:
        if migration.to_version != migration.from_version + 1:
            raise ValueError("migrations must advance exactly one version")
        key = (migration.kind, migration.from_version)
        if key in self._migrations:
            raise ValueError(f"duplicate migration: {key}")
        self._migrations[key] = migration

    def migrate(self, kind: str, document: dict[str, object], target_version: int) -> dict[str, object]:
        current = int(document.get("schema_version", 0))
        result = dict(document)
        while current < target_version:
            migration = self._migrations.get((kind, current))
            if migration is None:
                raise ValueError(f"no migration for {kind} schema {current}")
            result = migration.transform(dict(result))
            current = int(result.get("schema_version", 0))
            if current != migration.to_version:
                raise ValueError("migration returned the wrong schema version")
        if current != target_version:
            raise ValueError("downgrade migrations are not supported")
        return result


def migrate_file(
    path: Path,
    kind: str,
    target_version: int,
    backup_dir: Path,
    registry: MigrationRegistry,
) -> None:
    original = json.loads(path.read_text(encoding="utf-8"))
    migrated = registry.migrate(kind, original, target_version)
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)
    temporary = path.with_suffix(path.suffix + ".migrating")
    temporary.write_text(json.dumps(migrated, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
