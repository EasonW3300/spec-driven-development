import json
from pathlib import Path

from spec_driven.capabilities import HostManifest
from spec_driven.install import apply_install, claude_code_settings_fragment, plan_install, rollback_install


MANIFEST = HostManifest(
    1,
    "claude-code",
    "spec_driven.adapters.claude_code",
    "skills/spec-driven-development",
    ".claude/settings.json",
    {},
)


def _fragment() -> dict[str, object]:
    fragment = claude_code_settings_fragment("python -m spec_driven.adapters.claude_code_hook")
    assert fragment["hooks"]["UserPromptSubmit"]
    return fragment


def test_claude_settings_merge_keeps_existing_hooks(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "hooks": {"Notification": [{"command": "keep"}]}}), encoding="utf-8")
    manifest = HostManifest(MANIFEST.schema_version, MANIFEST.host, MANIFEST.adapter_package, MANIFEST.skill_source, MANIFEST.settings_path, _fragment())
    plan = plan_install(manifest, tmp_path, tmp_path)
    receipt = apply_install(plan, tmp_path / ".backup")
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert merged["hooks"]["Notification"] == [{"command": "keep"}]
    assert merged["hooks"]["UserPromptSubmit"]
    rollback_install(receipt)
    restored = json.loads(settings.read_text(encoding="utf-8"))
    assert restored["theme"] == "dark"
    assert restored["hooks"]["Notification"] == [{"command": "keep"}]
    assert "UserPromptSubmit" not in restored.get("hooks", {})


def test_rerunning_install_does_not_duplicate_registrations(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({}), encoding="utf-8")
    manifest = HostManifest(MANIFEST.schema_version, MANIFEST.host, MANIFEST.adapter_package, MANIFEST.skill_source, MANIFEST.settings_path, _fragment())
    plan = plan_install(manifest, tmp_path, tmp_path)
    apply_install(plan, tmp_path / ".backup")
    once = json.loads(settings.read_text(encoding="utf-8"))
    apply_install(plan, tmp_path / ".backup")
    twice = json.loads(settings.read_text(encoding="utf-8"))
    assert once == twice


def test_generated_fragment_covers_lifecycle_and_bash(tmp_path: Path) -> None:
    hooks = claude_code_settings_fragment("python -m spec_driven.adapters.claude_code_hook")["hooks"]
    assert set(hooks) == {"SessionStart", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit"}
    assert all(entry["matcher"] == "Bash" or entry["matcher"] == "" for entry in [*hooks["PostToolUse"], *hooks["PostToolUseFailure"]])
    commands = [
        inner["command"]
        for event in hooks.values()
        for entry in event
        for inner in entry["hooks"]
    ]
    assert all("-m spec_driven.adapters.claude_code_hook" in command for command in commands)
