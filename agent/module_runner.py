from __future__ import annotations

import logging
import time
from typing import Protocol

from config_manager import RemoteConfig


class IAgentModule(Protocol):
    name: str
    status: str

    def configure(self, config: RemoteConfig) -> None:
        ...

    def tick(self, now: float) -> None:
        ...


class ModuleRunner:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self.modules: dict[str, IAgentModule] = {}
        self.enabled: set[str] = set()
        self.statuses: dict[str, str] = {}

    def register(self, module: IAgentModule) -> None:
        self.modules[module.name] = module
        self.statuses[module.name] = "disabled"

    def configure(self, config: RemoteConfig) -> None:
        enabled = set()
        if config.media_update.enabled:
            enabled.add("media_update")
        if config.cash_monitoring.enabled:
            enabled.add("cash_monitoring")
        if config.journal_reader.enabled:
            enabled.add("journal_reader")

        self.enabled = enabled
        for name, module in self.modules.items():
            if name not in enabled:
                self.statuses[name] = "disabled"
                continue
            try:
                module.configure(config)
                self.statuses[name] = "running"
            except Exception as exc:
                self.statuses[name] = "error"
                self.logger.exception("Module configure failed: %s: %s", name, exc)

    def tick(self, now: float | None = None) -> None:
        current = now if now is not None else time.monotonic()
        for name in list(self.enabled):
            module = self.modules.get(name)
            if module is None:
                continue
            try:
                module.tick(current)
                self.statuses[name] = getattr(module, "status", "running")
            except Exception as exc:
                self.statuses[name] = "error"
                self.logger.exception("Module tick failed: %s: %s", name, exc)

    def enabled_modules(self) -> list[str]:
        return sorted(self.enabled)

    def module_statuses(self) -> dict[str, str]:
        return dict(self.statuses)
