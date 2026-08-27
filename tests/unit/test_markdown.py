import pytest

from spec_driven.documents.markdown import MarkdownAdapter
from spec_driven.errors import DocumentConflictError
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256


def managed(module_id: str) -> str:
    return (
        f'<!-- spec-driven:module id="{module_id}" order="1" status="pending" -->\n'
        f"## {module_id}: Core\n\nGoal: Build.\n\nTests: unit, regression\n\n"
        "<!-- spec-driven:completion -->\nStatus: pending\nNext module: M2\n"
        "Completed points:\nNotes:\nEvidence:\n<!-- /spec-driven:completion -->\n"
        "<!-- /spec-driven:module -->\n"
    )


def update() -> DocumentUpdate:
    return DocumentUpdate("M1", "completed", "M2", ("gate works",), ("reuse API",), ("unit: exit 0", "regression: exit 0"))


def test_markdown_update_is_idempotent_and_preserves_prose(tmp_path) -> None:
    path = tmp_path / "plan.md"
    path.write_text("# Plan\n\n" + managed("M1") + "\nKeep this.\n", encoding="utf-8")
    adapter = MarkdownAdapter()
    adapter.apply(adapter.plan_update(path, update(), sha256(path)))
    first = path.read_text(encoding="utf-8")
    adapter.apply(adapter.plan_update(path, update(), sha256(path)))
    assert path.read_text(encoding="utf-8") == first
    assert "Keep this." in first
    assert "- gate works" in first


def test_stale_hash_is_rejected(tmp_path) -> None:
    path = tmp_path / "plan.md"
    path.write_text(managed("M1"), encoding="utf-8")
    with pytest.raises(DocumentConflictError):
        MarkdownAdapter().plan_update(path, update(), "deadbeef")


def test_missing_managed_module_is_rejected(tmp_path) -> None:
    path = tmp_path / "plan.md"
    path.write_text(managed("M9"), encoding="utf-8")
    with pytest.raises(DocumentConflictError):
        MarkdownAdapter().plan_update(path, update(), sha256(path))


def test_apply_rejects_stale_hash(tmp_path) -> None:
    path = tmp_path / "plan.md"
    path.write_text(managed("M1"), encoding="utf-8")
    from spec_driven.patches import DocumentPatch

    patch = DocumentPatch(path, "deadbeef", managed("M1"), "rewrite")
    with pytest.raises(DocumentConflictError):
        MarkdownAdapter().apply(patch)


def test_completion_lists_evidence_and_notes(tmp_path) -> None:
    path = tmp_path / "plan.md"
    path.write_text(managed("M1"), encoding="utf-8")
    adapter = MarkdownAdapter()
    adapter.apply(adapter.plan_update(path, update(), sha256(path)))
    text = path.read_text(encoding="utf-8")
    assert "Status: completed" in text
    assert "Next module: M2" in text
    assert "- reuse API" in text
    assert "- unit: exit 0" in text
