from __future__ import annotations

import glob
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config_manager import JournalReaderConfig, LocalConfig, RemoteConfig
from journal_reader import GrgJournalParser, NcrJournalParser, read_new_text

if TYPE_CHECKING:
    from api_client import ApiClient


DEFAULT_BATCH_SIZE = 200
NCR_PARSER_STATE_VERSION = 3


class JournalReaderModule:
    name = "journal_reader"

    def __init__(self, api: ApiClient, local_config: LocalConfig, logger: logging.Logger) -> None:
        self.api = api
        self.local_config = local_config
        self.logger = logger
        self.config: JournalReaderConfig | None = None
        self.last_read = 0.0
        self.status = "disabled"
        self.last_event_count = 0
        self.last_error: str | None = None
        self.state_file = Path(local_config.local_log_path) / "journal-reader-state.json"
        self.parsers: dict[str, GrgJournalParser | NcrJournalParser] = {}

    def configure(self, config: RemoteConfig) -> None:
        self.config = config.journal_reader
        self.status = "running" if self.config.enabled else "disabled"

    def tick(self, now: float) -> None:
        if self.config is None or not self.config.enabled:
            self.status = "disabled"
            return
        if now - self.last_read < self.config.read_interval_seconds:
            return

        self.last_read = now
        try:
            count = self.read_and_send()
            self.last_event_count = count
            self.last_error = None
            self.status = "running"
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            self.logger.exception("Journal reader failed: %s", exc)
            self.api.log("error", "Journal reader failed", {"event_type": "JOURNAL_READER_FAILED", "error": str(exc)})
            raise

    def read_and_send(self) -> int:
        config = self.config
        if config is None:
            return 0

        provider = (config.provider or "grg_ej").strip().lower()
        state = self._load_state()
        files_state = state.setdefault("files", {})
        paths = sorted(Path(path) for path in glob.glob(config.log_glob))
        total_sent = 0
        batch: list[dict[str, Any]] = []

        for path in paths:
            file_key = os.path.normcase(str(path.resolve()))
            current_size = path.stat().st_size
            file_state = dict(files_state.get(file_key) or {})
            offset = int(file_state.get("offset") or 0)
            line_number = int(file_state.get("line_number") or 1)
            parser_state_version = int(file_state.get("parser_state_version") or 0)
            if provider == "ncr_ej" and parser_state_version < NCR_PARSER_STATE_VERSION:
                offset = 0
                line_number = 1
            if current_size < offset:
                offset = 0
                line_number = 1

            text, new_offset = read_new_text(path, offset)
            if not text:
                files_state[file_key] = {
                    "path": str(path),
                    "provider": provider,
                    "parser_state_version": NCR_PARSER_STATE_VERSION if provider == "ncr_ej" else 1,
                    "offset": new_offset,
                    "line_number": line_number,
                    "size": current_size,
                }
                continue

            lines = text.splitlines()
            parser_key = f"{provider}:{file_key}"
            parser = self.parsers.setdefault(parser_key, self._new_parser(provider, str(path)))
            if offset == 0:
                parser = self._new_parser(provider, str(path))
                self.parsers[parser_key] = parser
            events = parser.parse_lines(lines, start_line=line_number)
            for event in events:
                batch.append(event.to_payload())
                if len(batch) >= DEFAULT_BATCH_SIZE:
                    self.api.journal_events(batch)
                    total_sent += len(batch)
                    batch = []

            files_state[file_key] = {
                "path": str(path),
                "provider": provider,
                "parser_state_version": NCR_PARSER_STATE_VERSION if provider == "ncr_ej" else 1,
                "offset": new_offset,
                "line_number": line_number + len(lines),
                "size": current_size,
            }

        if batch:
            self.api.journal_events(batch)
            total_sent += len(batch)

        self._save_state(state)
        if total_sent:
            self.logger.info("Journal events sent: %s", total_sent)
        return total_sent

    def _new_parser(self, provider: str, file_path: str) -> GrgJournalParser | NcrJournalParser:
        if provider == "ncr_ej":
            return NcrJournalParser(file_path)
        return GrgJournalParser(file_path)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"files": {}}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"files": {}}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
