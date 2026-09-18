"""Customer-only projection for the public TV files; never copy source rows."""

PUBLIC_TOP_FIELDS = frozenset({
    "schema_version", "generated_at", "menu", "screen", "rotation_seconds", "brands",
})
PUBLIC_ROW_FIELDS = frozenset({
    "product_name", "display_name", "brand", "strain", "thc", "thc_display",
    "gram", "eighth", "quarter", "half", "ounce", "feeling", "looking_for",
    "closeout", "aged_inventory", "no_recent_sales", "size", "format", "process",
    "price", "short_price", "detail_display",
})


def public_menu_payload(menu):
    return {
        **{key: value for key, value in menu.items() if key in PUBLIC_TOP_FIELDS},
        "rows": [
            {key: value for key, value in row.items() if key in PUBLIC_ROW_FIELDS}
            for row in menu["rows"]
        ],
    }


def validate_public_payload(menu):
    if set(menu) - (PUBLIC_TOP_FIELDS | {"rows"}):
        raise ValueError("public menu contains non-customer metadata")
    if not isinstance(menu.get("rows"), list):
        raise ValueError("public menu rows must be a list")
    for row in menu["rows"]:
        if not isinstance(row, dict) or set(row) - PUBLIC_ROW_FIELDS:
            raise ValueError("public row contains non-customer fields")
        if any(isinstance(value, (dict, list)) for value in row.values()):
            raise ValueError("public row values must be scalar customer fields")
