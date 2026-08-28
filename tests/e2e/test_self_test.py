import json
from pathlib import Path

import pytest

from spec_driven.cli import main
from spec_driven.diagnostics import run_self_test


def test_self_test_proves_full_gated_workflow(tmp_path: Path) -> None:
    result = run_self_test(tmp_path)
    assert result["schema_version"] == 1
    assert result["status"] == "pass"
    checks = result["checks"]
    assert checks["gate"] is True
    assert checks["spec_updated"] is True
    assert checks["plan_updated"] is True
    assert checks["audit_event"] is True
    assert checks["next_module"] == "M2"


def test_self_test_cli_json_exits_zero_on_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["self-test", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["status"] == "pass"
    assert payload["checks"]["gate"] is True
    assert payload["checks"]["next_module"] == "M2"
