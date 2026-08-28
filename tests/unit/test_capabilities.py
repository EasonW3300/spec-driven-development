from pathlib import Path

import pytest

from spec_driven.capabilities import Capability, CapabilityReport, load_host_manifest
from spec_driven.errors import ConfigError


def test_capability_report_serializes_stable_fields() -> None:
    report = CapabilityReport(1, "generic", "0.1.0", (Capability("confirmation", "available", "CLI", "exact command", None),))
    assert report.to_dict()["capabilities"][0]["status"] == "available"


def test_empty_settings_fragment_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "host.json"
    path.write_text(
        '{"schema_version":1,"host":"h","adapter_module":"m",'
        '"skill_source":"s","settings_target":"settings.json",'
        '"settings_fragment":{}}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="missing required fields"):
        load_host_manifest(path)
