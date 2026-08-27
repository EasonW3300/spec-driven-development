from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from ..errors import DocumentConflictError
from ..models import DocumentUpdate, Module
from ..modules import parse_plan_modules
from ..patches import DocumentPatch, sha256

_START = re.compile(r'(<!--\s*spec-driven:module\s+id="(?P<id>[^"]+)"\s+order="(?P<order>\d+)"\s+status=")(?P<status>[^"]+)("\s*-->)')
_COMPLETION = re.compile(r'<!-- spec-driven:completion -->.*?<!-- /spec-driven:completion -->', re.DOTALL)


class MarkdownAdapter:
    name = "markdown"
    suffixes = frozenset({".md", ".markdown"})

    def parse_modules(self, path: Path) -> tuple[Module, ...]:
        return parse_plan_modules(path, allow_inference=True)

    def plan_update(self, path: Path, update: DocumentUpdate, expected_sha256: str) -> DocumentPatch:
        if sha256(path) != expected_sha256:
            raise DocumentConflictError(f"stale document hash: {path}")
        content = path.read_text(encoding="utf-8")
        starts = list(_START.finditer(content))
        target = next((item for item in starts if item.group("id") == update.module_id), None)
        if target is None:
            raise DocumentConflictError(f"managed module not found: {update.module_id}")
        end_token = "<!-- /spec-driven:module -->"
        end = content.find(end_token, target.end())
        if end < 0:
            raise DocumentConflictError(f"unterminated managed module: {update.module_id}")
        block = content[target.start():end]
        block = _START.sub(lambda match: f'{match.group(1)}{update.status}{match.group(5)}', block, count=1)
        completion = "\n".join((
            "<!-- spec-driven:completion -->",
            f"Status: {update.status}",
            f"Next module: {update.next_module_id or ''}",
            "Completed points:",
            *(f"- {item}" for item in update.completed_points),
            "Notes:",
            *(f"- {item}" for item in update.notes),
            "Evidence:",
            *(f"- {item}" for item in update.evidence_summary),
            "<!-- /spec-driven:completion -->",
        ))
        if _COMPLETION.search(block):
            block = _COMPLETION.sub(completion, block, count=1)
        else:
            block = block.rstrip() + "\n\n" + completion + "\n"
        replacement = content[:target.start()] + block + content[end:]
        return DocumentPatch(path, expected_sha256, replacement, f"complete {update.module_id}")

    def apply(self, patch: DocumentPatch) -> None:
        if sha256(patch.path) != patch.expected_sha256:
            raise DocumentConflictError(f"stale document hash: {patch.path}")
        fd, temporary = tempfile.mkstemp(prefix=f"{patch.path.name}.", dir=patch.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(patch.replacement)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, patch.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
