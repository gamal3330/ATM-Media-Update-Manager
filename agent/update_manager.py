from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backup_manager import clean_directory, copy_directory_contents, create_backup, restore_backup
from api_client import ApiClient
from checksum import sha256_file
from config_manager import LocalConfig, RemoteConfig
from path_policy import validate_backup_path, validate_managed_path
from safe_zip import content_root, extract_safe_zip


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UpdateManager:
    def __init__(self, api: ApiClient, local_config: LocalConfig) -> None:
        self.api = api
        self.local_config = local_config
        self.current_package_version: str | None = None

    def apply_remote_config(self, config: RemoteConfig) -> None:
        validate_managed_path(config.media_path, "media_path")
        validate_managed_path(config.backup_path, "backup_path")
        validate_managed_path(config.temp_path, "temp_path")
        validate_backup_path(config.media_path, config.backup_path)
        for path_text in [config.media_path, config.backup_path, config.temp_path]:
            path = Path(path_text)
            if str(path.resolve()) == path.resolve().anchor:
                raise ValueError(f"Refusing unsafe root path: {path}")
            path.mkdir(parents=True, exist_ok=True)

    def apply_update(self, update: dict, config: RemoteConfig) -> None:
        package_id = int(update["package_id"])
        version = str(update["version"])
        started_at = utc_now_iso()
        backup_dir: Path | None = None
        rollback_done = False

        try:
            temp_root = Path(config.temp_path)
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="atm_media_update_", dir=temp_root) as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                zip_path = temp_dir / f"package_{package_id}.zip"
                with zip_path.open("wb") as output:
                    downloaded, total = self.api.download_package(update["download_url"], output)
                self.api.progress(package_id, "downloading", 65, "Download completed", downloaded, total)

                expected_hash = str(update["sha256"]).lower()
                actual_hash = sha256_file(zip_path).lower()
                if actual_hash != expected_hash:
                    raise ValueError(f"Checksum mismatch: expected {expected_hash} got {actual_hash}")
                self.api.progress(package_id, "applying", 70, "Checksum verified")

                staging_dir = temp_dir / "staging"
                extract_safe_zip(zip_path, staging_dir, config.allowed_extensions)
                root = content_root(staging_dir)
                self.api.progress(package_id, "applying", 80, "Package extracted")

                media_path = Path(config.media_path)
                backup_dir = create_backup(media_path, Path(config.backup_path), self.local_config.atm_id)
                self.api.progress(package_id, "applying", 90, "Backup created")

                clean_directory(media_path)
                copy_directory_contents(root, media_path)
                self.api.progress(package_id, "applying", 95, "Media files copied")

            self.current_package_version = version
            message = "Images updated successfully"
            self.api.progress(package_id, "applied", 100, message)
            self.api.report_result(package_id, version, "success", message, started_at, utc_now_iso(), rollback_done=False)
        except Exception as exc:
            message = str(exc)
            if backup_dir is not None:
                try:
                    restore_backup(Path(config.media_path), backup_dir)
                    rollback_done = True
                    message = f"{message}. Rollback completed."
                except Exception as rollback_exc:
                    message = f"{message}. Rollback failed: {rollback_exc}"
            self.api.progress(package_id, "failed", 100, message)
            self.api.report_result(package_id, version, "failed", message, started_at, utc_now_iso(), rollback_done=rollback_done)
            raise
