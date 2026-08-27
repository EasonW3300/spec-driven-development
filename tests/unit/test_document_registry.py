from pathlib import Path

import pytest

from spec_driven.documents.registry import DocumentRegistry
from spec_driven.errors import ConfigError


class StubAdapter:
    name = "stub"
    suffixes = frozenset({".stub"})

    def parse_modules(self, path: Path):
        return ()

    def plan_update(self, path, update, expected_sha256):
        raise AssertionError("registry test does not plan updates")

    def apply(self, patch):
        raise AssertionError("registry test does not apply patches")


def test_registry_selects_enabled_suffix() -> None:
    registry = DocumentRegistry()
    registry.register(StubAdapter())
    assert registry.for_path(Path("plan.stub"), ("stub",)).name == "stub"
    assert registry.enabled_suffixes(("stub",)) == frozenset({".stub"})


def test_registry_rejects_disabled_and_duplicate_adapters() -> None:
    registry = DocumentRegistry()
    registry.register(StubAdapter())
    with pytest.raises(ConfigError, match="already registered"):
        registry.register(StubAdapter())
    with pytest.raises(ConfigError, match="no enabled document adapter"):
        registry.for_path(Path("plan.stub"), ("markdown",))


def test_registry_flags_unknown_enabled_names() -> None:
    registry = DocumentRegistry()
    registry.register(StubAdapter())
    with pytest.raises(ConfigError, match="unknown document adapters"):
        registry.enabled_suffixes(("yaml",))
