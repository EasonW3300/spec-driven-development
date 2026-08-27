import pytest

from spec_driven.documents.structured import apply_structured_update, parse_structured_modules
from spec_driven.errors import ConfigError
from spec_driven.models import DocumentUpdate


def _root() -> dict[str, object]:
    return {
        "title": "Keep me",
        "spec_driven": {
            "active_module_id": "M1",
            "modules": [
                {
                    "id": "M1",
                    "order": 1,
                    "title": "Core",
                    "goal": "Build core",
                    "status": "pending",
                    "prerequisites": [],
                    "acceptance": ["gate works"],
                    "tests": ["unit", "regression"],
                    "completed_points": [],
                    "notes": [],
                    "evidence": [],
                },
                {
                    "id": "M2",
                    "order": 2,
                    "title": "Adapter",
                    "goal": "Build adapter",
                    "status": "pending",
                    "prerequisites": ["M1"],
                    "acceptance": [],
                    "tests": ["unit", "regression"],
                    "completed_points": [],
                    "notes": [],
                    "evidence": [],
                },
            ],
        },
    }


def test_structured_modules_are_ordered() -> None:
    assert [module.module_id for module in parse_structured_modules(_root())] == ["M1", "M2"]


def test_update_changes_only_managed_values() -> None:
    root = _root()
    apply_structured_update(
        root,
        DocumentUpdate("M1", "completed", "M2", ("gate works",), ("reuse API",), ("unit: pass",)),
    )
    assert root["title"] == "Keep me"
    managed = root["spec_driven"]
    assert managed["active_module_id"] == "M2"
    assert managed["modules"][0]["status"] == "completed"
    assert managed["modules"][0]["notes"] == ["reuse API"]
    assert managed["modules"][1]["status"] == "pending"


def test_duplicate_module_ids_are_rejected() -> None:
    root = _root()
    root["spec_driven"]["modules"][1]["id"] = "M1"
    with pytest.raises(ConfigError, match="duplicate module id"):
        parse_structured_modules(root)


def test_missing_spec_driven_mapping_is_rejected() -> None:
    with pytest.raises(ConfigError, match="spec_driven"):
        parse_structured_modules({"title": "no managed section"})


def test_non_contiguous_order_is_rejected() -> None:
    root = _root()
    root["spec_driven"]["modules"][1]["order"] = 3
    with pytest.raises(ConfigError, match="contiguous"):
        parse_structured_modules(root)


def test_empty_modules_list_is_rejected() -> None:
    root = _root()
    root["spec_driven"]["modules"] = []
    with pytest.raises(ConfigError, match="non-empty list"):
        parse_structured_modules(root)
