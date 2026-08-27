from pathlib import Path

import pytest

from spec_driven.errors import DiscoveryAmbiguousError
from spec_driven.modules import parse_plan_modules


def _write_plan(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "plan.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_non_contiguous_order_is_rejected(tmp_path: Path) -> None:
    body = (
        '<!-- spec-driven:module id="M1" order="1" status="pending" -->\n'
        "## M1: Core workflow\n"
        "\n"
        "Goal: Create the core workflow.\n"
        "\n"
        "Acceptance:\n"
        "- State transitions are validated.\n"
        "\n"
        "Tests: unit, regression\n"
        "<!-- /spec-driven:module -->\n"
        '<!-- spec-driven:module id="M3" order="3" status="pending" -->\n'
        "## M3: Skipped order\n"
        "\n"
        "Goal: Break contiguity.\n"
        "\n"
        "Tests: unit\n"
        "<!-- /spec-driven:module -->\n"
    )
    with pytest.raises(DiscoveryAmbiguousError):
        parse_plan_modules(_write_plan(tmp_path, body), True)


def test_duplicate_module_ids_are_rejected(tmp_path: Path) -> None:
    block = (
        '<!-- spec-driven:module id="M1" order="{order}" status="pending" -->\n'
        "## M1: Core workflow\n"
        "\n"
        "Goal: Create the core workflow.\n"
        "\n"
        "Tests: unit\n"
        "<!-- /spec-driven:module -->\n"
    )
    body = block.format(order=1) + block.format(order=2)
    with pytest.raises(DiscoveryAmbiguousError):
        parse_plan_modules(_write_plan(tmp_path, body), True)


def test_unterminated_marker_is_rejected(tmp_path: Path) -> None:
    body = (
        '<!-- spec-driven:module id="M1" order="1" status="pending" -->\n'
        "## M1: Core workflow\n"
        "\n"
        "Goal: No end marker.\n"
        "\n"
        "Tests: unit\n"
    )
    with pytest.raises(DiscoveryAmbiguousError):
        parse_plan_modules(_write_plan(tmp_path, body), True)


def test_missing_goal_is_rejected(tmp_path: Path) -> None:
    body = (
        '<!-- spec-driven:module id="M1" order="1" status="pending" -->\n'
        "## M1: Core workflow\n"
        "\n"
        "Acceptance:\n"
        "- Something verifiable.\n"
        "\n"
        "Tests: unit\n"
        "<!-- /spec-driven:module -->\n"
    )
    with pytest.raises(DiscoveryAmbiguousError):
        parse_plan_modules(_write_plan(tmp_path, body), True)
