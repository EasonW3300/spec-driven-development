from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_driven.cli import main
from spec_driven.migrate import Migration, MigrationRegistry, migrate_file


def _parse_all(text: str) -> list[object]:
    decoder = json.JSONDecoder()
    result: list[object] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        result.append(value)
    return result


def test_registry_applies_each_version_once() -> None:
    registry = MigrationRegistry()
    registry.register(Migration("state", 1, 2, lambda value: {**value, "schema_version": 2, "v2": True}))
    registry.register(Migration("state", 2, 3, lambda value: {**value, "schema_version": 3, "v3": True}))
    migrated = registry.migrate("state", {"schema_version": 1}, 3)
    assert migrated == {"schema_version": 3, "v2": True, "v3": True}
    assert registry.migrate("state", migrated, 3) == migrated


def test_missing_migration_path_is_rejected() -> None:
    registry = MigrationRegistry()
    with pytest.raises(ValueError, match="no migration"):
        registry.migrate("state", {"schema_version": 1}, 2)


def test_register_rejects_skipping_versions() -> None:
    registry = MigrationRegistry()
    with pytest.raises(ValueError, match="exactly one version"):
        registry.register(Migration("state", 1, 3, lambda value: value))


def test_register_rejects_duplicate_kind_and_from_version() -> None:
    registry = MigrationRegistry()
    registry.register(Migration("state", 1, 2, lambda value: value))
    with pytest.raises(ValueError, match="duplicate migration"):
        registry.register(Migration("state", 1, 2, lambda value: value))


def test_migrate_file_rejects_downgrade(tmp_path: Path) -> None:
    path = tmp_path / ".spec-driven" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 3}), encoding="utf-8")
    registry = MigrationRegistry()
    with pytest.raises(ValueError, match="downgrade migrations are not supported"):
        migrate_file(path, "state", 2, tmp_path / "backups", registry)
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 3


def test_migrate_file_backs_up_and_atomically_replaces(tmp_path: Path) -> None:
    path = tmp_path / ".spec-driven" / "state.json"
    path.parent.mkdir(parents=True)
    original = {"schema_version": 1, "session_id": "s1"}
    original_text = json.dumps(original, sort_keys=True, indent=2) + "\n"
    path.write_text(original_text, encoding="utf-8")
    backup_dir = tmp_path / ".spec-driven" / "migration-backups"
    registry = MigrationRegistry()
    registry.register(Migration("state", 1, 2, lambda value: {**value, "schema_version": 2, "v2": True}))

    migrate_file(path, "state", 2, backup_dir, registry)

    # The backup is byte-identical to the original document.
    assert (backup_dir / path.name).read_bytes() == original_text.encode("utf-8")
    # The document was rewritten atomically: transform applied, no .migrating leftover.
    assert json.loads(path.read_text(encoding="utf-8")) == {"schema_version": 2, "session_id": "s1", "v2": True}
    assert not path.with_suffix(path.suffix + ".migrating").exists()

    # Re-migrating to the same target is a no-op that restores stable content.
    migrated_text = path.read_text(encoding="utf-8")
    migrate_file(path, "state", 2, backup_dir, registry)
    assert path.read_text(encoding="utf-8") == migrated_text


def test_cli_migrate_dry_run_reports_documents_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / ".spec-driven" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"schema_version": 1, "session_id": "s1"}), encoding="utf-8")

    assert main(["--project", str(tmp_path), "migrate", "--target-version", "1", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["path"] == str(state)
    assert report["kind"] == "state"
    assert report["current_version"] == 1
    assert report["target_version"] == 1
    assert report["dry_run"] is True
    assert json.loads(state.read_text(encoding="utf-8"))["schema_version"] == 1


def test_cli_migrate_no_documents_reports_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--project", str(tmp_path), "migrate", "--target-version", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["migrated"] == []
    assert report["target_version"] == 2
    assert report["dry_run"] is False


def test_cli_migrate_missing_migration_is_input_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / ".spec-driven" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    assert main(["--project", str(tmp_path), "migrate", "--target-version", "2"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "CLI_INPUT_INVALID"
    assert "no migration for state schema 1" in payload["message"]
    assert json.loads(state.read_text(encoding="utf-8"))["schema_version"] == 1


def test_cli_migrate_notes_non_json_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "spec-driven.config.yaml").write_text("schema_version: 1\n", encoding="utf-8")

    assert main(["--project", str(tmp_path), "migrate", "--target-version", "1"]) == 0
    notes = [value for value in _parse_all(capsys.readouterr().out) if isinstance(value, dict) and value.get("skipped") == "non-json-config"]
    assert notes == [{"path": str(tmp_path / "spec-driven.config.yaml"), "kind": "config", "skipped": "non-json-config", "message": "migrations apply to JSON machine documents only"}]
