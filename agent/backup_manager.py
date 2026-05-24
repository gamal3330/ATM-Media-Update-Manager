from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def assert_safe_managed_directory(path: Path) -> None:
    resolved = path.resolve()
    if str(resolved) == resolved.anchor:
        raise ValueError(f"Refusing to manage filesystem root: {resolved}")


def clean_directory(path: Path) -> None:
    assert_safe_managed_directory(path)
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_directory_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def create_backup(media_path: Path, backup_root: Path, atm_id: str) -> Path:
    assert_safe_managed_directory(media_path)
    backup_root.mkdir(parents=True, exist_ok=True)
    if backup_root.resolve().is_relative_to(media_path.resolve()):
        raise ValueError("backup_path must not be inside media_path")

    backup_dir = backup_root / f"{atm_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=False, exist_ok=False)
    copy_directory_contents(media_path, backup_dir)
    return backup_dir


def restore_backup(media_path: Path, backup_dir: Path) -> None:
    clean_directory(media_path)
    copy_directory_contents(backup_dir, media_path)
