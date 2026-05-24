ALL_PAGE_IDS = [
    "dashboard",
    "atms",
    "upload",
    "packages",
    "agent-downloads",
    "logs",
    "settings",
    "users",
]

DEFAULT_OPERATOR_PAGES = ["dashboard"]


def normalize_allowed_pages(role: str, pages: list[str] | None) -> list[str]:
    if role == "admin":
        return list(ALL_PAGE_IDS)

    cleaned = []
    for page in pages or DEFAULT_OPERATOR_PAGES:
        if page in ALL_PAGE_IDS and page not in cleaned and page != "users":
            cleaned.append(page)

    return cleaned or list(DEFAULT_OPERATOR_PAGES)
