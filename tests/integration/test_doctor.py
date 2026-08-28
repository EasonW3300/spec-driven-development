import json
import shutil
from pathlib import Path

import pytest

from spec_driven.cli import main
from spec_driven.diagnostics import run_doctor


def test_doctor_reports_ambiguous_documents_as_failure(tmp_path: Path) -> None:
    (tmp_path / "one-spec.md").write_text("# One", encoding="utf-8")
    (tmp_path / "two-spec.md").write_text("# Two", encoding="utf-8")
    checks = run_doctor(tmp_path, "generic")
    discovery = next(check for check in checks if check.name == "document_discovery")
    assert discovery.status == "fail"
    assert discovery.remediation == "set spec.paths and plan.paths in spec-driven.config.yaml"


def _configured_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree("fixtures/markdown-project", root)
    return root


def test_doctor_passes_for_configured_markdown_project(tmp_path: Path) -> None:
    root = _configured_project(tmp_path)
    checks = run_doctor(root, "generic")
    statuses = {check.name: check.status for check in checks}
    assert statuses == {
        "configuration": "pass",
        "document_discovery": "pass",
        "test_commands": "pass",
        "host_adapter": "pass",
    }


def test_doctor_warns_for_unknown_host(tmp_path: Path) -> None:
    root = _configured_project(tmp_path)
    checks = run_doctor(root, "sublime-text")
    host = next(check for check in checks if check.name == "host_adapter")
    assert host.status == "warn"
    assert host.message == "sublime-text"


def test_doctor_cli_json_exits_zero_when_all_checks_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _configured_project(tmp_path)
    assert main(["--project", str(root), "doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert {item["name"] for item in payload} == {"configuration", "document_discovery", "test_commands", "host_adapter"}
    assert all(item["status"] != "fail" for item in payload)


def test_doctor_cli_json_exits_one_when_discovery_is_ambiguous(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "one-spec.md").write_text("# One", encoding="utf-8")
    (tmp_path / "two-spec.md").write_text("# Two", encoding="utf-8")
    assert main(["--project", str(tmp_path), "doctor", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    discovery = next(item for item in payload if item["name"] == "document_discovery")
    assert discovery["status"] == "fail"
    assert discovery["remediation"] == "set spec.paths and plan.paths in spec-driven.config.yaml"
