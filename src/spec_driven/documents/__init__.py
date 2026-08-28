from .json import JsonAdapter
from .markdown import MarkdownAdapter
from .registry import DocumentRegistry
from .yaml import YamlAdapter


def builtin_registry() -> DocumentRegistry:
    registry = DocumentRegistry()
    registry.register(MarkdownAdapter())
    registry.register(YamlAdapter())
    registry.register(JsonAdapter())
    return registry
