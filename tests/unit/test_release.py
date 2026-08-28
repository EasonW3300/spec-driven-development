from pathlib import Path

from spec_driven.release import validate_release


def test_repository_has_no_release_validation_errors() -> None:
    assert validate_release(Path.cwd()) == ()


def test_empty_host_settings_fragment_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "install" / "manifests"
    manifest.mkdir(parents=True)
    (manifest / "host.json").write_text(
        '{"schema_version":1,"host":"h","adapter_module":"m","skill_source":"s",'
        '"settings_target":"x","settings_fragment":{}}', encoding="utf-8"
    )
    assert "host manifest settings_fragment is empty: host.json" in validate_release(tmp_path)
