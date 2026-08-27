from __future__ import annotations

import json
from pathlib import Path

from ..errors import StateConflictError
from ..models import DocumentUpdate, Module
from ..patches import DocumentPatch, apply_atomic, sha256
from .structured import apply_structured_update, parse_structured_modules


class JsonAdapter:
    name = "json"
    suffixes = frozenset({".json"})

    def _load(self, path: Path) -> dict[str, object]:
        root = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(root, dict):
            raise StateConflictError(f"JSON root must be an object: {path}")
        return root

    def parse_modules(self, path: Path) -> tuple[Module, ...]:
        return parse_structured_modules(self._load(path))

    def plan_update(
        self,
        path: Path,
        update: DocumentUpdate,
        expected_sha256: str,
    ) -> DocumentPatch:
        if sha256(path) != expected_sha256:
            raise StateConflictError(f"document hash is stale: {path}")
        root = self._load(path)
        apply_structured_update(root, update)
        replacement = json.dumps(root, ensure_ascii=False, indent=2) + "\n"
        return DocumentPatch(path, expected_sha256, replacement, f"update {update.module_id}")

    def apply(self, patch: DocumentPatch) -> None:
        apply_atomic(patch)
