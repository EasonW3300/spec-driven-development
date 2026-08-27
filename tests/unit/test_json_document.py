import json
from pathlib import Path

from spec_driven.documents.json import JsonAdapter
from spec_driven.models import DocumentUpdate
from spec_driven.patches import sha256


def test_json_update_preserves_unknown_fields_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({
        "title": "用户计划",
        "unknown": {"keep": True},
        "spec_driven": {
            "active_module_id": "M1",
            "modules": [{
                "id": "M1", "order": 1, "title": "Core", "goal": "Build",
                "status": "pending", "prerequisites": [], "acceptance": [],
                "tests": ["unit", "regression"], "completed_points": [],
                "notes": [], "evidence": []
            }]
        }
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    adapter = JsonAdapter()
    update = DocumentUpdate("M1", "completed", None, ("done",), (), ("unit: pass",))
    adapter.apply(adapter.plan_update(path, update, sha256(path)))
    first = path.read_text(encoding="utf-8")
    assert json.loads(first)["unknown"] == {"keep": True}
    assert "用户计划" in first
    adapter.apply(adapter.plan_update(path, update, sha256(path)))
    assert path.read_text(encoding="utf-8") == first


def test_json_declares_identity() -> None:
    adapter = JsonAdapter()
    assert adapter.name == "json"
    assert adapter.suffixes == frozenset({".json"})


def test_json_stale_hash_prevents_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"spec_driven": {"active_module_id": "M1"}}), encoding="utf-8")
    original = path.read_bytes()
    try:
        JsonAdapter().plan_update(
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


def test_json_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    try:
        JsonAdapter().parse_modules(path)
        raised = False
    except Exception as error:
        raised = True
        assert "object" in str(error) or "mapping" in str(error)
    assert raised


def test_json_parses_two_modules_with_unicode(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({
        "title": "路线图",
        "spec_driven": {
            "active_module_id": "M1",
            "modules": [
                {"id": "M1", "order": 1, "title": "核心", "goal": "构建", "status": "pending",
                 "prerequisites": [], "acceptance": [], "tests": ["unit", "regression"]},
                {"id": "M2", "order": 2, "title": "适配器", "goal": "接线", "status": "pending",
                 "prerequisites": ["M1"], "acceptance": [], "tests": ["unit", "regression"]},
            ],
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    modules = JsonAdapter().parse_modules(path)
    assert [module.module_id for module in modules] == ["M1", "M2"]
