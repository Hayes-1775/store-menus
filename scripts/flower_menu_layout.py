"""Deterministic single-screen layout rules for the flower menu."""

from __future__ import annotations

from typing import Any, Dict


MENU_HEIGHT = 1920
CONTENT_TOP = 88
BOTTOM_MARGIN = 48
MAX_ROW_HEIGHT = 54
MIN_ROW_HEIGHT = 26


class FlowerMenuLayoutError(ValueError):
    """Raised when the complete flower menu cannot fit on one screen."""


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def section_metrics(row_height: int) -> Dict[str, int]:
    return {
        "section_height": clamp(int(row_height * 1.28), 46, 68),
        "gap_after_section": clamp(int(row_height * 0.32), 10, 24),
        "gap_between_groups": clamp(int(row_height * 0.40), 12, 30),
    }


def measure_flower_layout(
    row_count: int,
    group_count: int,
    row_height: int,
    *,
    menu_height: int = MENU_HEIGHT,
    content_top: int = CONTENT_TOP,
    bottom_margin: int = BOTTOM_MARGIN,
) -> Dict[str, Any]:
    metrics = section_metrics(row_height)
    available_height = menu_height - content_top - bottom_margin
    required_height = (
        row_count * row_height
        + group_count * metrics["section_height"]
        + group_count * metrics["gap_after_section"]
        + max(group_count - 1, 0) * metrics["gap_between_groups"]
    )
    return {
        "fits": required_height <= available_height,
        "row_count": row_count,
        "group_count": group_count,
        "row_height": row_height,
        "required_height": required_height,
        "available_height": available_height,
        **metrics,
    }


def select_flower_layout(row_count: int, group_count: int) -> Dict[str, Any]:
    if row_count < 0 or group_count < 0:
        raise FlowerMenuLayoutError("Flower menu counts cannot be negative.")
    for row_height in range(MAX_ROW_HEIGHT, MIN_ROW_HEIGHT - 1, -1):
        layout = measure_flower_layout(row_count, group_count, row_height)
        if layout["fits"]:
            return layout
    smallest = measure_flower_layout(row_count, group_count, MIN_ROW_HEIGHT)
    raise FlowerMenuLayoutError(
        "Complete flower menu does not fit one 1080x1920 screen: "
        f"requires {smallest['required_height']}px with "
        f"{smallest['available_height']}px available."
    )
