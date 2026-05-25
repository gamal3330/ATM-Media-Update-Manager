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


def normalized_cash_layout(layout: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(item) for item in (layout or DEFAULT_YER_1000_LAYOUT)]
