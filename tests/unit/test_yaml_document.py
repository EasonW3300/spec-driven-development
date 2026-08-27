from pathlib import Path

from spec_driven.documents.yaml import YamlAdapter
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256


def test_yaml_update_preserves_comments_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(
        "title: 'Keep quotes' # keep comment\n"
        "owner: platform\n"
        "spec_driven:\n"
        "  active_module_id: M1\n"
        "  modules:\n"
        "    - id: M1\n"
        "      order: 1\n"
        "      title: Core\n"
        "      goal: Build\n"
        "      status: pending\n"
        "      prerequisites: []\n"
        "      acceptance: []\n"
        "      tests: [unit, regression]\n"
        "      completed_points: []\n"
        "      notes: []\n"
        "      evidence: []\n",
        encoding="utf-8",
    )
    adapter = YamlAdapter()
    patch = adapter.plan_update(
        path,
        DocumentUpdate("M1", "completed", None, ("done",), ("note",), ("unit: pass",)),
        sha256(path),
    )
    adapter.apply(patch)
    content = path.read_text(encoding="utf-8")
    assert "# keep comment" in content
    assert "title: 'Keep quotes'" in content
    assert "owner: platform" in content
    assert "status: completed" in content


def test_yaml_declares_identity() -> None:
    adapter = YamlAdapter()
    assert adapter.name == "yaml"
    assert adapter.suffixes == frozenset({".yaml", ".yml"})


def test_yaml_stale_hash_prevents_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text("spec_driven:\n  active_module_id: M1\n", encoding="utf-8")
    adapter = YamlAdapter()
    original = path.read_bytes()
    try:
        adapter.plan_update(
            path,
            DocumentUpdate("M1", "completed", None, (), (), ("unit: pass",)),
            "not-the-real-hash",
        )
        raised = False
    except Exception as error:
        raised = True
        assert "stale" in str(error) or "hash" in str(error)
    assert raised
    assert path.read_bytes() == original


def test_yaml_parses_two_module_managed_section(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        "purpose: component spec\n"
        "spec_driven:\n"
        "  active_module_id: M1\n"
        "  modules:\n"
        "    - id: M1\n"
        "      order: 1\n"
        "      title: Core\n"
        "      goal: Build core\n"
        "      status: pending\n"
        "      prerequisites: []\n"
        "      acceptance: ['gate works']\n"
        "      tests: [unit, regression]\n"
        "    - id: M2\n"
        "      order: 2\n"
        "      title: Adapter\n"
        "      goal: Build adapter\n"
        "      status: pending\n"
        "      prerequisites: [M1]\n"
        "      acceptance: []\n"
        "      tests: [unit, regression]\n",
        encoding="utf-8",
    )
    modules = YamlAdapter().parse_modules(path)
    assert [module.module_id for module in modules] == ["M1", "M2"]
