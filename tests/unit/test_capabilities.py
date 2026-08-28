import importlib
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


ROOT = Path(__file__).resolve().parents[2]
HOSTS = {"claude-code", "codex"}


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_real_manifest_declares_importable_adapter_and_concrete_registration(host: str) -> None:
    manifest = load_host_manifest(ROOT / "install" / "manifests" / f"{host}.json")
    assert manifest.host == host
    importlib.import_module(manifest.adapter_module)
    assert manifest.settings_fragment
    assert manifest.skill_source
    assert manifest.settings_target


def test_capability_report_builds_per_host() -> None:
    for host in sorted(HOSTS):
        manifest = load_host_manifest(ROOT / "install" / "manifests" / f"{host}.json")
        report = CapabilityReport(1, manifest.host, "0.1.0", ())
        assert report.to_dict()["host"] == manifest.host
