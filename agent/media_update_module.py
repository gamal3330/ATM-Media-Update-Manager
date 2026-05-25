from __future__ import annotations

import logging

from api_client import ApiClient
from config_manager import LocalConfig, RemoteConfig
from update_manager import UpdateManager


class MediaUpdateModule:
    name = "media_update"

    def __init__(self, api: ApiClient, local_config: LocalConfig, logger: logging.Logger) -> None:
        self.api = api
        self.local_config = local_config
        self.logger = logger
        self.manager = UpdateManager(api, local_config)
        self.remote_config: RemoteConfig | None = None
        self.status = "disabled"
        self.last_check = 0.0

    @property
    def current_package_version(self) -> str | None:
        return self.manager.current_package_version

    def configure(self, config: RemoteConfig) -> None:
        self.manager.apply_remote_config(config)
        self.remote_config = config
        self.status = "running"

    def tick(self, now: float) -> None:
        if self.remote_config is None or not self.remote_config.media_update.enabled:
            self.status = "disabled"
            return
        interval = self.remote_config.media_update.check_interval_seconds
        if now - self.last_check < interval:
            return

        update = self.api.check_update()
        if update:
            self.status = "applying"
            self.manager.apply_update(update, self.remote_config)
        self.last_check = now
        self.status = "running"
