from __future__ import annotations

from pathlib import PureWindowsPath


def validate_managed_path(path_text: str, label: str) -> None:
    normalized = path_text.replace("/", "\\")
    parts = PureWindowsPath(normalized).parts
    if len(parts) < 3 or parts[0].upper() != "C:\\" or parts[1].upper() != "ATM":
        raise ValueError(f"{label} must be under C:\\ATM\\")
    if ".." in parts:
        raise ValueError(f"{label} must not contain '..'")


def validate_backup_path(media_path: str, backup_path: str) -> None:
    media = PureWindowsPath(media_path.replace("/", "\\"))
    backup = PureWindowsPath(backup_path.replace("/", "\\"))
    if len(backup.parts) > len(media.parts) and backup.parts[: len(media.parts)] == media.parts:
        raise ValueError("backup_path must not be inside media_path")
