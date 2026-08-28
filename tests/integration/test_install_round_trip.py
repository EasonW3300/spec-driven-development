import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spec_driven.capabilities import load_host_manifest
from spec_driven.cli import _install, _uninstall
from spec_driven.install import (
    apply_install,
    merge_toml_fragment,
    plan_install,
    rollback_install,
    rollback_toml,
    verify_receipt,
)

ROOT = Path(__file__).resolve().parents[2]


def test_claude_code_real_manifest_merges_and_rolls_back_byte_equivalent(tmp_path: Path) -> None:
    manifest = load_host_manifest(ROOT / "install" / "manifests" / "claude-code.json")
    target = tmp_path / "home"
    settings = target / manifest.settings_target
    settings.parent.mkdir(parents=True)
    seed = '{"theme": "dark"}\n'
    settings.write_text(seed, encoding="utf-8")
    backup_dir = target / ".spec-driven-install-backups"
    receipt = apply_install(plan_install(manifest, target, ROOT), backup_dir)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"                      # unknown key survived
    assert "SessionStart" in merged["hooks"]
    verify_receipt(receipt, target)
    rollback_install(receipt)
    assert settings.read_text(encoding="utf-8") == seed    # byte-equivalent restoration


def test_codex_real_manifest_toml_merges_and_rolls_back_byte_equivalent(tmp_path: Path) -> None:
    manifest = load_host_manifest(ROOT / "install" / "manifests" / "codex.json")
    target = tmp_path / "home"
    config = target / manifest.settings_target
    config.parent.mkdir(parents=True)
    seed = 'model = "keep"\n'
    config.write_text(seed, encoding="utf-8")
    receipt = merge_toml_fragment(config, manifest.settings_fragment)
    merged = config.read_text(encoding="utf-8")
    assert 'model = "keep"' in merged                      # unknown key survived
    assert "background = true" in merged
    rollback_toml(receipt)
    assert config.read_text(encoding="utf-8") == seed      # byte-equivalent restoration


def test_cli_project_install_and_uninstall_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _install(SimpleNamespace(host="claude-code", scope="project", dry_run=False)) == 0
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.is_file()
    assert "python -m spec_driven.adapters.claude_code_hook" in settings.read_text(encoding="utf-8")
    receipt_path = tmp_path / ".spec-driven" / "install-receipts" / "claude-code.json"
    assert receipt_path.is_file()
    assert _uninstall(SimpleNamespace(receipt=str(receipt_path), root=tmp_path)) == 0
    assert not settings.exists()
    assert not receipt_path.exists()


def test_cli_install_dry_run_does_not_mutate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _install(SimpleNamespace(host="claude-code", scope="project", dry_run=True)) == 0
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / ".spec-driven").exists()
