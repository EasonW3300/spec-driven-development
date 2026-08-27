from __future__ import annotations

import re
from pathlib import Path

from .errors import DiscoveryAmbiguousError
from .models import Module

_START = re.compile(r'<!--\s*spec-driven:module\s+id="([^"]+)"\s+order="(\d+)"\s+status="[^"]+"\s*-->')
_END = "<!-- /spec-driven:module -->"


def _single(lines: list[str], prefix: str) -> str:
    matches = [line[len(prefix):].strip() for line in lines if line.startswith(prefix)]
    if len(matches) != 1:
        raise DiscoveryAmbiguousError(f"module requires exactly one {prefix.rstrip(':')} field")
    return matches[0]


def parse_plan_modules(path: Path, allow_inference: bool) -> tuple[Module, ...]:
    del allow_inference
    lines = path.read_text(encoding="utf-8").splitlines()
    modules: list[Module] = []
    index = 0
    while index < len(lines):
        match = _START.fullmatch(lines[index].strip())
        if match is None:
            index += 1
            continue
        body: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip() != _END:
            body.append(lines[index])
            index += 1
        if index == len(lines):
            raise DiscoveryAmbiguousError(f"unterminated module marker: {match.group(1)}")
        title_line = next((line for line in body if line.startswith("## ")), "")
        acceptance_start = body.index("Acceptance:") if "Acceptance:" in body else -1
        tests_index = next((position for position, line in enumerate(body) if line.startswith("Tests:")), len(body))
        acceptance = tuple(
            line[2:].strip() for line in body[acceptance_start + 1:tests_index]
            if line.startswith("- ")
        ) if acceptance_start >= 0 else ()
        modules.append(Module(
            module_id=match.group(1),
            title=title_line.split(": ", 1)[-1],
            order=int(match.group(2)),
            goal=_single(body, "Goal:"),
            prerequisites=(),
            acceptance=acceptance,
            test_requirements=tuple(item.strip() for item in _single(body, "Tests:").split(",")),
        ))
        index += 1
    ordered = tuple(sorted(modules, key=lambda module: module.order))
    if not ordered or [module.order for module in ordered] != list(range(1, len(ordered) + 1)):
        raise DiscoveryAmbiguousError("plan requires explicit modules ordered contiguously from 1")
    if len({module.module_id for module in ordered}) != len(ordered):
        raise DiscoveryAmbiguousError("module ids must be unique")
    return ordered
