#!/usr/bin/env python3
"""Screen-capacity planning for the portrait cartridge menus."""

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence


MENU_HEIGHT = 1920
CONTENT_TOP = 88
BOTTOM_MARGIN = 34
MIN_ROW_HEIGHT = 34
MAX_ROW_HEIGHT = 44
PROCESS_ORDER = ["Distillate", "Cured Resin", "Live Resin", "DLR", "Live Rosin", "Rosin", "Rosin/CR", "Other"]
FORMAT_ORDER = ["510", "AIO", "Other"]


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _max_column_count(rows: Sequence[Dict[str, Any]], key) -> int:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(key(row) or "Other")] += 1
    return max(counts.values(), default=0)


def content_groups(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_process: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        process = str(row.get("process") or "Other")
        by_process[process].append(row)

    present_processes = set(by_process)
    ordered_processes = [process for process in PROCESS_ORDER if process in present_processes]
    ordered_processes.extend(sorted(present_processes - set(ordered_processes), key=str.casefold))
    return [{"process": process, "rows": by_process[process]} for process in ordered_processes]


def _species_panel_height(rows: Sequence[Dict[str, Any]], row_height: int) -> int:
    base_height = 10 + 28 + 12
    by_format: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_format[str(row.get("format") or "Other")].append(row)
    present_formats = set(by_format)
    ordered_formats = [format_name for format_name in FORMAT_ORDER if format_name in present_formats]
    ordered_formats.extend(sorted(present_formats - set(ordered_formats), key=str.casefold))
    return base_height + sum(22 + len(by_format[format_name]) * row_height for format_name in ordered_formats)


def brand_body_height(rows: Sequence[Dict[str, Any]], row_height: int) -> int:
    height = 0
    for group in content_groups(rows):
        by_strain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in group["rows"]:
            by_strain[str(row.get("strain") or "Other")].append(row)
        panel_height = max(
            (_species_panel_height(strain_rows, row_height) for strain_rows in by_strain.values()),
            default=0,
        )
        height += 30 + panel_height + 10
    return height


def measure_layout(rows: Sequence[Dict[str, Any]], row_height: int) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        brand = str(row.get("brand") or "Other")
        grouped.setdefault(brand, []).append(row)

    section_height = clamp(int(row_height * 1.28), 48, 60)
    gap_after_section = clamp(int(row_height * 0.25), 8, 12)
    gap_between_brands = clamp(int(row_height * 0.38), 12, 18)
    required_height = CONTENT_TOP
    brands = list(grouped)

    for index, brand in enumerate(brands):
        required_height += section_height + gap_after_section
        required_height += brand_body_height(grouped[brand], row_height)
        if index < len(brands) - 1:
            required_height += gap_between_brands

    available_bottom = MENU_HEIGHT - BOTTOM_MARGIN
    return {
        "fits": required_height <= available_bottom,
        "row_height": row_height,
        "required_height": required_height,
        "available_height": available_bottom,
        "remaining_pixels": available_bottom - required_height,
        "brand_count": len(brands),
        "row_count": len(rows),
    }


def best_layout(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    for row_height in range(MAX_ROW_HEIGHT, MIN_ROW_HEIGHT - 1, -1):
        metrics = measure_layout(rows, row_height)
        if metrics["fits"]:
            return metrics
    return measure_layout(rows, MIN_ROW_HEIGHT)


def ordered_inventory_brands(
    rows: Sequence[Dict[str, Any]], priority: Iterable[str]
) -> List[str]:
    available = {str(row.get("brand") or "Other") for row in rows}
    ordered: List[str] = []
    seen = set()
    for brand in priority:
        name = str(brand).strip()
        if name in available and name not in seen:
            ordered.append(name)
            seen.add(name)
    ordered.extend(sorted(available - seen, key=str.casefold))
    return ordered


def plan_screens(
    rows: Sequence[Dict[str, Any]],
    priority: Iterable[str],
    screen_count: int = 2,
) -> Dict[str, Any]:
    if screen_count < 1:
        raise ValueError("screen_count must be at least 1")

    by_brand: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_brand[str(row.get("brand") or "Other")].append(row)
    ordered_brands = ordered_inventory_brands(rows, priority)

    screens: List[Dict[str, Any]] = []
    current_brands: List[str] = []
    current_rows: List[Dict[str, Any]] = []
    oversized_brands: List[str] = []
    not_displayed: List[str] = []

    def finish_screen() -> None:
        nonlocal current_brands, current_rows
        screens.append(
            {
                "number": len(screens) + 1,
                "brands": current_brands,
                "rows": current_rows,
                "layout": best_layout(current_rows),
            }
        )
        current_brands = []
        current_rows = []

    for brand in ordered_brands:
        brand_rows = by_brand[brand]
        if not best_layout(brand_rows)["fits"]:
            oversized_brands.append(brand)
            not_displayed.append(brand)
            continue

        candidate_rows = current_rows + brand_rows
        if not current_rows or best_layout(candidate_rows)["fits"]:
            current_brands.append(brand)
            current_rows = candidate_rows
            continue

        finish_screen()
        if len(screens) >= screen_count:
            not_displayed.append(brand)
            continue
        current_brands = [brand]
        current_rows = list(brand_rows)

    if current_rows and len(screens) < screen_count:
        finish_screen()
    while len(screens) < screen_count:
        finish_screen()

    displayed = {brand for screen in screens for brand in screen["brands"]}
    not_displayed.extend(brand for brand in ordered_brands if brand not in displayed and brand not in not_displayed)
    cutoff_brand = screens[1]["brands"][0] if len(screens) > 1 and screens[1]["brands"] else None

    return {
        "priority": ordered_brands,
        "screens": screens,
        "screen_1_cutoff_brand": cutoff_brand,
        "not_displayed": not_displayed,
        "oversized_brands": oversized_brands,
    }
