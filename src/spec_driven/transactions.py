from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from .errors import DocumentConflictError
from .patches import DocumentPatch, sha256


def _write_journal(path: Path, status: str, patches: tuple[DocumentPatch, ...]) -> None:
    payload = {
        "schema_version": 1,
        "status": status,
        "paths": [str(patch.path) for patch in patches],
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def apply_transaction(
    patches: tuple[DocumentPatch, ...],
    runtime_root: Path,
    event_id: str,
    save_state: Callable[[], None],
) -> None:
    transaction = runtime_root / "transactions" / event_id
    backups = transaction / "backups"
    staged = transaction / "staged"
    journal = transaction / "journal.json"
    backups.mkdir(parents=True, exist_ok=True)
    staged.mkdir(parents=True, exist_ok=True)
    if journal.is_file() and json.loads(journal.read_text(encoding="utf-8"))["status"] == "committed":
        return
    for patch in patches:
        if sha256(patch.path) != patch.expected_sha256:
            raise DocumentConflictError(f"stale document hash: {patch.path}")
    for index, patch in enumerate(patches):
        shutil.copy2(patch.path, backups / f"{index}.bak")
        (staged / f"{index}.new").write_text(patch.replacement, encoding="utf-8")
    _write_journal(journal, "prepared", patches)
    replaced: list[int] = []
    try:
        for index, patch in enumerate(patches):
            (staged / f"{index}.new").replace(patch.path)
            replaced.append(index)
        _write_journal(journal, "documents_applied", patches)
        save_state()
        _write_journal(journal, "committed", patches)
    except BaseException:
        for index in replaced:
            shutil.copy2(backups / f"{index}.bak", patches[index].path)
        _write_journal(journal, "rolled_back", patches)
        raise
