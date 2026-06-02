from typing import Any

DEFAULT_YER_1000_LAYOUT = [
    {"cassette_no": 1, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100},
    {"cassette_no": 2, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100},
    {"cassette_no": 3, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100},
    {"cassette_no": 4, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100},
]

MIXED_YER_USD_SAR_LAYOUT = [
    {"cassette_no": 1, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100},
    {"cassette_no": 2, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100},
    {"cassette_no": 3, "currency": "USD", "denomination": 100, "max_capacity": 2000, "low_threshold": 100, "critical_threshold": 30},
    {"cassette_no": 4, "currency": "SAR", "denomination": 100, "max_capacity": 2000, "low_threshold": 100, "critical_threshold": 30},
]


def default_cash_layout() -> list[dict[str, Any]]:
    return [dict(item) for item in DEFAULT_YER_1000_LAYOUT]


def _default_item_for(cassette_no: int, currency: str | None = None) -> dict[str, Any]:
    for item in DEFAULT_YER_1000_LAYOUT:
        if item["cassette_no"] == cassette_no:
            base = dict(item)
            break
    else:
        base = {
            "cassette_no": cassette_no,
            "currency": "YER",
            "denomination": 1000,
            "max_capacity": 2000,
            "low_threshold": 300,
            "critical_threshold": 100,
        }
    if currency in {"USD", "SAR"}:
        base["denomination"] = 100
        base["low_threshold"] = 100
        base["critical_threshold"] = 30
    return base


def normalized_cash_layout(layout: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in layout or DEFAULT_YER_1000_LAYOUT:
        cassette_no = int(item.get("cassette_no", len(normalized) + 1))
        base = _default_item_for(cassette_no, item.get("currency"))
        base.update(item)
        normalized.append(base)
    return normalized
