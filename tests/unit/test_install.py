from pathlib import Path

import pytest

from spec_driven.capabilities import HostManifest
from spec_driven.install import InstallReceipt, plan_install, resolve_package_root, verify_receipt


def _manifest(settings_target: str, host: str = "claude-code") -> HostManifest:
    return HostManifest(1, host, "spec_driven.adapters.claude_code", "skills/spec-driven-development", ".claude/skills/spec-driven-development", settings_target, {"hooks": {"SessionStart": []}})


def test_plan_install_rejects_settings_target_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes target root"):
        plan_install(_manifest("../outside.json"), tmp_path, tmp_path)


def test_receipt_with_escaping_target_is_rejected(tmp_path: Path) -> None:
    receipt = InstallReceipt(str(tmp_path / "backups"), str(tmp_path / "root" / ".." / "outside.json"), None)
    with pytest.raises(ValueError, match="escapes target root"):
        verify_receipt(receipt, tmp_path / "root")


def test_receipt_with_escaping_backup_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "settings.json").write_text("{}", encoding="utf-8")
    receipt = InstallReceipt(str(tmp_path / "backups"), str(tmp_path / "root" / "settings.json"), str(tmp_path / "outside" / "0-settings.json"))
    with pytest.raises(ValueError, match="escapes target root"):
        verify_receipt(receipt, tmp_path / "root")


def test_receipt_with_contained_paths_passes(tmp_path: Path) -> None:
    (tmp_path / "root" / "backups").mkdir(parents=True)
    (tmp_path / "root" / "settings.json").write_text("{}", encoding="utf-8")
    receipt = InstallReceipt(str(tmp_path / "root" / "backups"), str(tmp_path / "root" / "settings.json"), str(tmp_path / "root" / "backups" / "0-settings.json"))
    verify_receipt(receipt, tmp_path / "root")


def test_resolve_package_root_source_layout(tmp_path: Path) -> None:
    module_file = tmp_path / "src" / "spec_driven" / "cli.py"
    module_file.parent.mkdir(parents=True)
    (tmp_path / "install" / "manifests").mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")
    assert resolve_package_root(module_file) == tmp_path


def test_resolve_package_root_wheel_layout(tmp_path: Path) -> None:
    site_packages = tmp_path / "lib" / "python3.12" / "site-packages"
    module_file = site_packages / "spec_driven" / "cli.py"
    module_file.parent.mkdir(parents=True)
    (site_packages / "install" / "manifests").mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")
    assert resolve_package_root(module_file) == site_packages


def test_resolve_package_root_raises_when_missing(tmp_path: Path) -> None:
    module_file = tmp_path / "nested" / "module" / "cli.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="package data not found"):
        resolve_package_root(module_file)
