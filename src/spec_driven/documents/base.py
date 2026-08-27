from pathlib import Path
from typing import Protocol

from ..models import DocumentUpdate, Module
from ..patches import DocumentPatch


class DocumentAdapter(Protocol):
    name: str
    suffixes: frozenset[str]

    def parse_modules(self, path: Path) -> tuple[Module, ...]: ...
    def plan_update(self, path: Path, update: DocumentUpdate, expected_sha256: str) -> DocumentPatch: ...
    def apply(self, patch: DocumentPatch) -> None: ...
