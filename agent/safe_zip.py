from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath

IGNORED_ZIP_FILENAMES = {".ds_store", "thumbs.db", "desktop.ini"}
DISALLOWED_EXTENSIONS = {".exe", ".ps1", ".bat", ".cmd", ".vbs", ".js", ".jse", ".msi", ".dll", ".scr", ".com", ".reg"}


def is_ignored_member(path: PurePosixPath) -> bool:
    parts = [part.lower() for part in path.parts]
    filename = parts[-1] if parts else ""
    return "__macosx" in parts or any(part.startswith("._") for part in parts) or filename in IGNORED_ZIP_FILENAMES


def safe_member_path(name: str, allowed_extensions: set[str]) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or any(part.endswith(":") for part in path.parts):
        raise ValueError(f"Unsafe path in ZIP member: {name}")
    if is_ignored_member(path):
        return path
    extension = path.suffix.lower()
    if extension in DISALLOWED_EXTENSIONS:
        raise ValueError(f"Executable or script file is not allowed in ZIP: {name}")
    allowed = {item.lower().lstrip(".") for item in allowed_extensions}
    if extension.lstrip(".") not in allowed:
        raise ValueError(f"Unsupported file extension in ZIP: {name}")
    return path


def extract_safe_zip(zip_path: Path, destination: Path, allowed_extensions: set[str]) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    file_count = 0

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_path = safe_member_path(member.filename, allowed_extensions)
            if is_ignored_member(member_path):
                continue
            target = (destination / Path(*member_path.parts)).resolve()
            if not target.is_relative_to(destination_resolved):
                raise ValueError(f"ZIP member escapes destination: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            file_count += 1

    if file_count == 0:
        raise ValueError("ZIP package contains no image files")
    return file_count


def content_root(staging_dir: Path) -> Path:
    children = list(staging_dir.iterdir())
    files = [child for child in children if child.is_file()]
    directories = [child for child in children if child.is_dir()]
    if not files and len(directories) == 1:
        return directories[0]
    return staging_dir
