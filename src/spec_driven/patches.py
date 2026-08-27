from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class DocumentPatch:
    path: Path
    expected_sha256: str
    replacement: str
    description: str
