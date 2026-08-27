from pathlib import Path

import pytest

from spec_driven.config import load_config
from spec_driven.models import Module


def test_module_is_immutable() -> None:
    module = Module("M1", "Core", 1, "Build core", (), (), ("unit", "regression"))
    with pytest.raises(AttributeError):
        module.order = 2  # type: ignore[misc]


def test_project_and_session_override_global_config(tmp_path: Path) -> None:
    global_path = tmp_path / "global.yaml"
    global_path.write_text("tests:\n  unit:\n    command: global-unit\n", encoding="utf-8")
    (tmp_path / "spec-driven.config.yaml").write_text(
        "tests:\n  unit:\n    command: project-unit\n", encoding="utf-8"
    )
    project = load_config(tmp_path, global_path)
    session = load_config(
        tmp_path,
        global_path,
        {"tests": {"unit": {"command": "session-unit"}}},
    )
    assert project.unit_test_command == "project-unit"
    assert session.unit_test_command == "session-unit"


def test_defaults_are_applied_without_any_config_files(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.schema_version == 1
    assert config.confirmation_command == "confirm-next"
    assert config.state_dir == ".spec-driven"
    assert config.document_adapters == ("markdown",)
    assert config.unit_test_command is None


def test_invalid_schema_version_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "spec-driven.config.yaml").write_text("schema_version: 99\n", encoding="utf-8")
    try:
        load_config(tmp_path)
        raised = False
    except Exception as error:
        raised = True
        assert error.code == "CONFIG_INVALID"
    assert raised
