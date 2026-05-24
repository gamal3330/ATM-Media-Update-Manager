import hashlib
import json
import zipfile

import pytest

from backup_manager import create_backup, restore_backup
from checksum import sha256_file
from config_manager import load_local_config
from path_policy import validate_managed_path
from safe_zip import extract_safe_zip


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_sha256_file(tmp_path):
    target = tmp_path / "image.png"
    target.write_bytes(b"sample-image")

    assert sha256_file(target) == hashlib.sha256(b"sample-image").hexdigest()


def test_rejects_script_file_in_zip(tmp_path):
    package = tmp_path / "bad.zip"
    make_zip(package, {"bad.ps1": "Write-Host bad"})

    with pytest.raises(ValueError, match="Executable or script file"):
        extract_safe_zip(package, tmp_path / "staging", {"jpg", "jpeg", "png", "bmp", "gif"})


def test_rejects_path_traversal_in_zip(tmp_path):
    package = tmp_path / "bad.zip"
    make_zip(package, {"../escape.png": b"bad"})

    with pytest.raises(ValueError, match="Unsafe path"):
        extract_safe_zip(package, tmp_path / "staging", {"jpg", "jpeg", "png", "bmp", "gif"})


def test_backup_and_rollback_restore_existing_media(tmp_path):
    media = tmp_path / "media"
    backup_root = tmp_path / "backups"
    media.mkdir()
    (media / "screen.png").write_text("old", encoding="utf-8")

    backup = create_backup(media, backup_root, "ATM001")
    (media / "screen.png").write_text("new", encoding="utf-8")

    restore_backup(media, backup)

    assert (media / "screen.png").read_text(encoding="utf-8") == "old"


def test_local_config_contains_connection_data_only(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "server_url": "https://server.local",
                "atm_id": "ATM001",
                "api_key": "secret",
            }
        ),
        encoding="utf-8",
    )

    config = load_local_config(config_path)

    assert config.server_url == "https://server.local"
    assert not hasattr(config, "media_path")


def test_remote_config_rejects_paths_outside_atm_root():
    with pytest.raises(ValueError, match="media_path must be under"):
        validate_managed_path("C:/Windows/System32", "media_path")
