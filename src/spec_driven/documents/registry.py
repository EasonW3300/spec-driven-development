from __future__ import annotations

from pathlib import Path

from ..errors import ConfigError
from .base import DocumentAdapter


class DocumentRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, DocumentAdapter] = {}

    def register(self, adapter: DocumentAdapter) -> None:
        if adapter.name in self._adapters:
            raise ConfigError(f"document adapter already registered: {adapter.name}")
        self._adapters[adapter.name] = adapter

    def for_path(self, path: Path, enabled: tuple[str, ...]) -> DocumentAdapter:
        matches = [
            adapter
            for name, adapter in self._adapters.items()
            if name in enabled and path.suffix.lower() in adapter.suffixes
        ]
        if len(matches) != 1:
            raise ConfigError(
                f"no enabled document adapter for {path}",
                remediation="check documents.adapters in spec-driven.config.yaml",
            )
        return matches[0]

    def enabled_suffixes(self, enabled: tuple[str, ...]) -> frozenset[str]:
        missing = set(enabled) - set(self._adapters)
        if missing:
            raise ConfigError(f"unknown document adapters: {sorted(missing)}")
        return frozenset(
            suffix
            for name in enabled
            for suffix in self._adapters[name].suffixes
        )
