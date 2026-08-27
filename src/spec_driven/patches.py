from __future__ import annotations

import hashlib
import os
import tempfile
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


def apply_atomic(patch: DocumentPatch) -> None:
    """Shared atomic writer: temp file + fsync + rename inside the document's directory."""
    if sha256(patch.path) != patch.expected_sha256:
        raise ValueError(f"stale document hash: {patch.path}")
    fd, temporary = tempfile.mkstemp(prefix=f"{patch.path.name}.", dir=patch.path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(patch.replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, patch.path)
    finally:
        Path(temporary).unlink(missing_ok=True)
