from pathlib import Path

import pytest

from spec_driven.documents.markdown import MarkdownAdapter
from spec_driven.errors import DocumentConflictError
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256

_FIXTURE_PLAN = Path("fixtures/markdown-project/docs/plans/product-plan.md")


def test_adapter_declares_identity() -> None:
    adapter = MarkdownAdapter()
    assert adapter.name == "markdown"
    assert adapter.suffixes == frozenset({".md", ".markdown"})


def test_adapter_parses_fixture_modules() -> None:
    modules = MarkdownAdapter().parse_modules(_FIXTURE_PLAN)
    assert [module.module_id for module in modules] == ["M1", "M2"]


def test_plan_update_rejects_mismatched_document(tmp_path: Path) -> None:
    other = tmp_path / "other.md"
    other.write_text("# Not the fixture\n", encoding="utf-8")
    update = DocumentUpdate("M1", "completed", "M2", ("a",), (), ("unit: exit 0",))
    with pytest.raises(DocumentConflictError):
        MarkdownAdapter().plan_update(other, update, sha256(other))


def test_plan_update_then_apply_round_trip_is_idempotent(tmp_path: Path) -> None:
    content = _FIXTURE_PLAN.read_text(encoding="utf-8")
    target = tmp_path / "product-plan.md"
    target.write_text(content, encoding="utf-8")
    adapter = MarkdownAdapter()
    update = DocumentUpdate(
        "M1",
        "completed",
        "M2",
        ("State transitions are validated.", "Both test gates are recorded."),
        ("Reuse engine boundaries in M2",),
        ("unit: exit 0", "regression: exit 0"),
    )
    adapter.apply(adapter.plan_update(target, update, sha256(target)))
    once = target.read_bytes()
    assert once != content.encode("utf-8")  # block actually changed
    adapter.apply(adapter.plan_update(target, update, sha256(target)))
    assert target.read_bytes() == once
    # Prose outside managed blocks is untouched.
    assert "Prose here differs from the spec" in target.read_text(encoding="utf-8")


def test_baseline_markdown_adapter_dispatches_by_contract() -> None:
    from spec_driven.documents.registry import DocumentRegistry

    registry = DocumentRegistry()
    registry.register(MarkdownAdapter())
    adapter = registry.for_path(Path("plan.md"), ("markdown",))
    assert adapter.name == "markdown"
    assert callable(adapter.parse_modules)
    assert callable(adapter.plan_update)
    assert callable(adapter.apply)
