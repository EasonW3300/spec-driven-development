from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from ..errors import StateConflictError
from ..models import DocumentUpdate, Module
from ..patches import DocumentPatch, apply_atomic, sha256
from .structured import apply_structured_update, parse_structured_modules


class YamlAdapter:
    name = "yaml"
    suffixes = frozenset({".yaml", ".yml"})

    def __init__(self) -> None:
        self.yaml = YAML(typ="rt")
        self.yaml.preserve_quotes = True

    def _load(self, path: Path):
        root = self.yaml.load(path.read_text(encoding="utf-8"))
        if not isinstance(root, dict):
            raise StateConflictError(f"YAML root must be a mapping: {path}")
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
        output = StringIO()
        self.yaml.dump(root, output)
        return DocumentPatch(path, expected_sha256, output.getvalue(), f"update {update.module_id}")

    def apply(self, patch: DocumentPatch) -> None:
        apply_atomic(patch)
