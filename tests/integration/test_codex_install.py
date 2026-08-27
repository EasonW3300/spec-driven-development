from pathlib import Path

from spec_driven.install import copy_assets, merge_toml_fragment, rollback_toml


def _read(path: Path) -> bytes:
    return path.read_bytes()


def test_merge_sets_notify_and_preserves_existing_content(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    original = b'# my prefs\nmodel = "o5"\napproval_policy = "never"\n'
    config.write_bytes(original)
    receipt = merge_toml_fragment(config, {"notify": ["python", "/opt/spec-driven/codex-hook"]})
    text = config.read_text(encoding="utf-8")
    assert 'model = "o5"' in text
    assert "# my prefs" in text
    assert 'notify = ["python", "/opt/spec-driven/codex-hook"]' in text
    rollback_toml(receipt)
    assert _read(config) == original


def test_merge_is_idempotent_for_identical_value(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    fragment = {"notify": ["python", "/opt/spec-driven/codex-hook"]}
    merge_toml_fragment(config, fragment)
    once = _read(config)
    receipt = merge_toml_fragment(config, fragment)
    assert receipt.applied_keys == ()  # nothing changed on second pass
    assert _read(config) == once


def test_merge_refuses_conflicting_value(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('notify = ["other"]\n', encoding="utf-8")
    raised = False
    try:
        merge_toml_fragment(config, {"notify": ["python", "/x"]})
    except Exception:
        raised = True
    assert raised
    assert 'notify = ["other"]' in config.read_text(encoding="utf-8")


def test_merge_rolls_back_created_file_entirely(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    assert not config.exists()
    receipt = merge_toml_fragment(config, {"notify": ["python", "/x"]})
    assert config.is_file()
    rollback_toml(receipt)
    assert not config.exists()


def test_copy_assets_is_idempotent(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    copy_assets(repo_root / "adapters/codex", tmp_path)
    first = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    copy_assets(repo_root / "adapters/codex", tmp_path)
    second = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second


def test_copy_assets_lands_prompts_and_skills(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    copy_assets(repo_root / "adapters/codex", tmp_path)
    prompt = tmp_path / "prompts" / "confirm-next.md"
    skill = tmp_path / "skills" / "spec-driven-development" / "SKILL.md"
    assert prompt.is_file()
    assert skill.is_file()
    # non-asset files (the config fragment) are never copied into codex home
    assert not (tmp_path / "config.fragment.toml").exists()


def test_copy_assets_replaces_stale_content(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    stale_home = tmp_path / "codex-home"
    (stale_home / "prompts").mkdir(parents=True)
    (stale_home / "prompts" / "confirm-next.md").write_text("outdated", encoding="utf-8")
    copy_assets(repo_root / "adapters/codex", stale_home)
    assert (stale_home / "prompts" / "confirm-next.md").read_text(encoding="utf-8") != "outdated"
