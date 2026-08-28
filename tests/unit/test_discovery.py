from pathlib import Path

import pytest

from spec_driven.config import load_config
from spec_driven.discovery import discover_documents
from spec_driven.errors import DiscoveryAmbiguousError
from spec_driven.modules import parse_plan_modules


def test_fixture_has_one_spec_and_one_plan() -> None:
    root = Path("fixtures/markdown-project")
    refs = discover_documents(root, load_config(root))
    assert [(ref.kind, ref.path) for ref in refs] == [
        ("spec", "docs/specs/product.md"),
        ("plan", "docs/plans/product-plan.md"),
    ]


def test_equal_candidates_stop_discovery(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a-spec.md").write_text("# A", encoding="utf-8")
    (tmp_path / "docs/b-spec.md").write_text("# B", encoding="utf-8")
    (tmp_path / "docs/plan.md").write_text("# Plan", encoding="utf-8")
    with pytest.raises(DiscoveryAmbiguousError):
        discover_documents(tmp_path, load_config(tmp_path))


def test_explicit_markers_produce_contiguous_modules() -> None:
    modules = parse_plan_modules(Path("fixtures/markdown-project/docs/plans/product-plan.md"), True)
    assert [(module.module_id, module.order) for module in modules] == [("M1", 1), ("M2", 2)]


def test_document_ref_sha_matches_fixture_bytes() -> None:
    import hashlib

    root = Path("fixtures/markdown-project")
    refs = discover_documents(root, load_config(root))
    spec = refs[0]
    expected = hashlib.sha256((root / spec.path).read_bytes()).hexdigest()
    assert spec.sha256 == expected


def test_configured_paths_outside_project_are_rejected(tmp_path: Path) -> None:
    config = load_config(
        tmp_path,
        session_override={"spec": {"paths": ["../outside.md"]}, "plan": {"paths": ["docs/plan.md"]}},
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/plan.md").write_text("# Plan", encoding="utf-8")
    (tmp_path.parent / "outside.md").write_text("# Outside", encoding="utf-8")
    try:
        discover_documents(tmp_path, config)
        raised = False
    except DiscoveryAmbiguousError:
        raised = True
    assert raised


def test_auto_discovery_ignores_project_config_file(tmp_path: Path) -> None:
    (tmp_path / "spec-driven.config.yaml").write_text(
        "documents:\n  adapters:\n    - markdown\n    - yaml\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.yaml").write_text("spec: []\n", encoding="utf-8")
    (tmp_path / "docs" / "plan.yaml").write_text("plan: []\n", encoding="utf-8")
    spec, plan = discover_documents(tmp_path, load_config(tmp_path))
    assert spec.path == "docs/spec.yaml"
    assert plan.path == "docs/plan.yaml"
