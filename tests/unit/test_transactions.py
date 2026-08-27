import json
from pathlib import Path

import pytest

from spec_driven.errors import DocumentConflictError
from spec_driven.patches import DocumentPatch, sha256
from spec_driven.transactions import apply_transaction


def test_transaction_restores_first_document_when_state_save_fails(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("old spec\n", encoding="utf-8")
    plan.write_text("old plan\n", encoding="utf-8")
    patches = (
        DocumentPatch(spec, sha256(spec), "new spec\n", "spec"),
        DocumentPatch(plan, sha256(plan), "new plan\n", "plan"),
    )
    with pytest.raises(RuntimeError, match="state failed"):
        apply_transaction(patches, tmp_path / ".spec-driven", "e1", lambda: (_ for _ in ()).throw(RuntimeError("state failed")))
    assert spec.read_text(encoding="utf-8") == "old spec\n"
    assert plan.read_text(encoding="utf-8") == "old plan\n"


def test_committed_transaction_short_circuits_rerun(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("old\n", encoding="utf-8")
    calls: list[int] = []
    patches = (DocumentPatch(doc, sha256(doc), "new\n", "doc"),)
    runtime = tmp_path / ".spec-driven"
    apply_transaction(patches, runtime, "e1", lambda: calls.append(1))
    assert doc.read_text(encoding="utf-8") == "new\n"
    journal = json.loads((runtime / "transactions" / "e1" / "journal.json").read_text(encoding="utf-8"))
    assert journal["status"] == "committed"
    # Simulate a crash after commit but before downstream bookkeeping reruns.
    doc.write_text("externally changed\n", encoding="utf-8")
    apply_transaction(patches, runtime, "e1", lambda: calls.append(1))
    assert doc.read_text(encoding="utf-8") == "externally changed\n"
    assert len(calls) == 1


def test_stale_hash_aborts_before_any_write(tmp_path: Path) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("one\n", encoding="utf-8")
    second.write_text("two\n", encoding="utf-8")
    patches = (
        DocumentPatch(first, sha256(first), "ONE\n", "first"),
        DocumentPatch(second, "stale", "TWO\n", "second"),
    )
    with pytest.raises(DocumentConflictError):
        apply_transaction(patches, tmp_path / ".spec-driven", "e2", lambda: None)
    assert first.read_text(encoding="utf-8") == "one\n"
    assert second.read_text(encoding="utf-8") == "two\n"
