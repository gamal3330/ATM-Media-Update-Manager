ALL_PAGE_IDS = [
    "dashboard",
    "atms",
    "upload",
    "packages",
    "agent-updates",
    "cash",
    "notifications",
    "agent-downloads",
    "logs",
    "journal",
    "settings",
    "users",
]

DEFAULT_OPERATOR_PAGES = ["dashboard"]
SYSTEM_ADMIN_ROLES = {"admin", "system_admin"}
ROLE_DEFAULT_PAGES = {
    "operator": ["dashboard"],
    "media_admin": ["dashboard", "atms", "upload", "packages", "agent-updates", "logs", "journal"],
    "cash_monitoring_viewer": ["dashboard", "cash"],
    "cash_monitoring_admin": ["dashboard", "cash", "notifications", "atms", "logs", "journal"],
}


def normalize_allowed_pages(role: str, pages: list[str] | None) -> list[str]:
    if role in SYSTEM_ADMIN_ROLES:
        return list(ALL_PAGE_IDS)

    cleaned = []
    for page in pages or ROLE_DEFAULT_PAGES.get(role, DEFAULT_OPERATOR_PAGES):
        if page in ALL_PAGE_IDS and page not in cleaned and page != "users":
            cleaned.append(page)

    return cleaned or list(DEFAULT_OPERATOR_PAGES)
