from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


TIMESTAMP_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s*(?P<message>.*)$")
SERIAL_RE = re.compile(r"TRANSACTION SERIAL NUMBER\s*:\s*(?P<value>\S+)", re.IGNORECASE)
RECEIPT_FIELD_RE = re.compile(r"^(?P<key>[A-Z ]+?)\s*:\s*(?P<value>.*)$", re.IGNORECASE)
CASSETTE_OUT_RE = re.compile(
    r"\[CAS\s+(?P<cassette>\d+)\]\s+OUT:\s*(?P<out>\d+),\s*REJECT:\s*(?P<reject>\d+),\s*DENO:\s*(?P<denomination>\d+)",
    re.IGNORECASE,
)


EVENT_MESSAGES: tuple[tuple[str, str], ...] = (
    ("LINE DOWN", "LINE_DOWN"),
    ("LINE UP", "LINE_UP"),
    ("ENTER OFFLINE MODE", "ENTER_OFFLINE_MODE"),
    ("EXIT OFFLINE MODE", "EXIT_OFFLINE_MODE"),
    ("ENTER OUTOFSERVICE MODE", "ENTER_OUTOFSERVICE_MODE"),
    ("ENTER INSERVICE MODE", "ENTER_INSERVICE_MODE"),
    ("ATM POWER UP", "ATM_POWER_UP"),
    ("DISPENSE SUCCESS", "DISPENSE_SUCCESS"),
    ("PRESENT SUCCESS", "PRESENT_SUCCESS"),
    ("CARD TAKEN", "CARD_TAKEN"),
    ("TAKE CASH TIMEOUT", "TAKE_CASH_TIMEOUT"),
    ("MONEY TAKEN", "MONEY_TAKEN"),
)


PRINTER_KEYWORDS = (
    "PRINTER",
    "RECEIPT PRINTER",
    "JOURNAL PRINTER",
    "PRINT",
)


@dataclass
class JournalEvent:
    event_uid: str
    source: str
    event_type: str
    occurred_at: str
    severity: str
    message: str
    file_path: str
    line_number: int
    transaction_serial: str | None = None
    transaction_type: str | None = None
    amount: int | None = None
    currency: str | None = None
    rrn: str | None = None
    stan: str | None = None
    auth_code: str | None = None
    card_masked: str | None = None
    receipt_date: str | None = None
    cassette_outputs: list[dict[str, int]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value not in (None, [], {})}


@dataclass
class TransactionContext:
    started_at: str
    started_line: int
    file_path: str
    serial_number: str | None = None
    transaction_type: str | None = None
    amount: int | None = None
    currency: str | None = None
    rrn: str | None = None
    stan: str | None = None
    auth_code: str | None = None
    card_masked: str | None = None
    receipt_date: str | None = None
    response: str | None = None
    wording: str | None = None
    cassette_outputs: list[dict[str, int]] = field(default_factory=list)
    dispense_success: bool = False
    present_success: bool = False
    card_taken: bool = False
    take_cash_timeout: bool = False
    money_taken: bool = False


def parse_timestamp(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").isoformat(timespec="milliseconds")


def mask_card(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 10:
        return None
    return f"{digits[:6]}{'*' * max(0, len(digits) - 10)}{digits[-4:]}"


def normalize_receipt_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def event_uid(file_path: str, line_number: int, occurred_at: str, event_type: str, message: str) -> str:
    raw = f"{file_path}|{line_number}|{occurred_at}|{event_type}|{message}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def make_event(
    *,
    file_path: str,
    line_number: int,
    occurred_at: str,
    event_type: str,
    message: str,
    severity: str = "info",
    tx: TransactionContext | None = None,
    details: dict[str, Any] | None = None,
) -> JournalEvent:
    return JournalEvent(
        event_uid=event_uid(file_path, line_number, occurred_at, event_type, message),
        source="grg_ej",
        event_type=event_type,
        occurred_at=occurred_at,
        severity=severity,
        message=message,
        file_path=file_path,
        line_number=line_number,
        transaction_serial=tx.serial_number if tx else None,
        transaction_type=tx.transaction_type if tx else None,
        amount=tx.amount if tx else None,
        currency=tx.currency if tx else None,
        rrn=tx.rrn if tx else None,
        stan=tx.stan if tx else None,
        auth_code=tx.auth_code if tx else None,
        card_masked=tx.card_masked if tx else None,
        receipt_date=tx.receipt_date if tx else None,
        cassette_outputs=list(tx.cassette_outputs) if tx else [],
        details=details or {},
    )


class GrgJournalParser:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.current_tx: TransactionContext | None = None
        self.in_receipt = False

    def parse_lines(self, lines: Iterable[str], start_line: int = 1) -> list[JournalEvent]:
        events: list[JournalEvent] = []
        for offset, raw_line in enumerate(lines):
            line_number = start_line + offset
            line = raw_line.rstrip("\r\n")
            events.extend(self.parse_line(line, line_number))
        return events

    def parse_line(self, line: str, line_number: int) -> list[JournalEvent]:
        matched = TIMESTAMP_RE.match(line)
        if matched:
            occurred_at = parse_timestamp(matched.group("ts"))
            message = matched.group("message").strip()
            return self._parse_timestamped_line(occurred_at, message, line_number)

        if self.in_receipt and self.current_tx:
            self._parse_receipt_field(line)
        return []

    def _parse_timestamped_line(self, occurred_at: str, message: str, line_number: int) -> list[JournalEvent]:
        upper = message.upper()
        events: list[JournalEvent] = []

        if "TRANSACTION REQUEST" in upper:
            self.in_receipt = False
            self.current_tx = TransactionContext(occurred_at, line_number, self.file_path)
            events.append(
                make_event(
                    file_path=self.file_path,
                    line_number=line_number,
                    occurred_at=occurred_at,
                    event_type="TRANSACTION_START",
                    message=message,
                    tx=self.current_tx,
                )
            )
            return events

        tx = self.current_tx
        serial = SERIAL_RE.search(message)
        if serial:
            if tx is None:
                tx = TransactionContext(occurred_at, line_number, self.file_path)
                self.current_tx = tx
            tx.serial_number = serial.group("value").strip()
            events.append(
                make_event(
                    file_path=self.file_path,
                    line_number=line_number,
                    occurred_at=occurred_at,
                    event_type="TRANSACTION_SERIAL_NUMBER",
                    message=message,
                    tx=tx,
                )
            )
            return events

        cassette = CASSETTE_OUT_RE.search(message)
        if cassette and tx:
            output = {
                "cassette_no": int(cassette.group("cassette")),
                "out": int(cassette.group("out")),
                "reject": int(cassette.group("reject")),
                "denomination": int(cassette.group("denomination")),
            }
            tx.cassette_outputs.append(output)
            events.append(
                make_event(
                    file_path=self.file_path,
                    line_number=line_number,
                    occurred_at=occurred_at,
                    event_type="CASSETTE_OUT",
                    message=message,
                    tx=tx,
                    details=output,
                )
            )
            return events

        if "TRANSACTION RECEIPT DATA" in upper:
            self.in_receipt = True
            return events

        if "<---- TRANSACTION END" in upper:
            self.in_receipt = False
            if tx is None:
                tx = TransactionContext(occurred_at, line_number, self.file_path)
            completed = bool(tx.dispense_success and tx.money_taken)
            severity = "warning" if tx.take_cash_timeout else "info"
            details = {
                "completed": completed,
                "withdrawal": tx.transaction_type == "WID",
                "dispense_success": tx.dispense_success,
                "present_success": tx.present_success,
                "card_taken": tx.card_taken,
                "take_cash_timeout": tx.take_cash_timeout,
                "money_taken": tx.money_taken,
                "response": tx.response,
                "wording": tx.wording,
            }
            events.append(
                make_event(
                    file_path=self.file_path,
                    line_number=line_number,
                    occurred_at=occurred_at,
                    event_type="TRANSACTION_END",
                    message=message,
                    severity=severity,
                    tx=tx,
                    details=details,
                )
            )
            self.current_tx = None
            return events

        for needle, event_type in EVENT_MESSAGES:
            if needle in upper:
                if tx:
                    if event_type == "DISPENSE_SUCCESS":
                        tx.dispense_success = True
                    elif event_type == "PRESENT_SUCCESS":
                        tx.present_success = True
                    elif event_type == "CARD_TAKEN":
                        tx.card_taken = True
                    elif event_type == "TAKE_CASH_TIMEOUT":
                        tx.take_cash_timeout = True
                    elif event_type == "MONEY_TAKEN":
                        tx.money_taken = True
                events.append(
                    make_event(
                        file_path=self.file_path,
                        line_number=line_number,
                        occurred_at=occurred_at,
                        event_type=event_type,
                        message=message,
                        severity="warning" if event_type in {"TAKE_CASH_TIMEOUT", "LINE_DOWN", "ENTER_OFFLINE_MODE", "ENTER_OUTOFSERVICE_MODE"} else "info",
                        tx=tx,
                    )
                )
                return events

        if any(keyword in upper for keyword in PRINTER_KEYWORDS):
            events.append(
                make_event(
                    file_path=self.file_path,
                    line_number=line_number,
                    occurred_at=occurred_at,
                    event_type="PRINTER_EVENT",
                    message=message,
                    severity="warning" if any(word in upper for word in ("ERROR", "FAULT", "JAM", "OUT")) else "info",
                    tx=tx,
                )
            )

        return events

    def _parse_receipt_field(self, line: str) -> None:
        tx = self.current_tx
        if tx is None:
            return
        matched = RECEIPT_FIELD_RE.match(line.strip())
        if not matched:
            return
        key = normalize_receipt_key(matched.group("key"))
        value = matched.group("value").strip()
        if key == "TRANSACTION TYPE":
            tx.transaction_type = value or None
        elif key == "DATE":
            tx.receipt_date = value or None
        elif key == "WORDING":
            tx.wording = value or None
        elif key == "CURRENCY":
            tx.currency = value or None
        elif key == "AMOUNT":
            tx.amount = parse_int(value)
        elif key == "RRN":
            tx.rrn = value or None
        elif key == "STAN":
            tx.stan = value or None
        elif key == "AUTH CODE":
            tx.auth_code = value or None
        elif key == "CARD":
            tx.card_masked = mask_card(value)
        elif key == "RESPONSE":
            tx.response = value or None


def parse_grg_journal_text(text: str, file_path: str = "<memory>") -> list[JournalEvent]:
    parser = GrgJournalParser(file_path)
    return parser.parse_lines(text.splitlines())


def decode_journal_bytes(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")

    sample = data[:4096]
    if sample:
        even_nulls = sample[0::2].count(0)
        odd_nulls = sample[1::2].count(0)
        half = max(1, len(sample) // 2)
        if odd_nulls / half > 0.20 and odd_nulls > even_nulls * 2:
            return data.decode("utf-16-le", errors="replace")
        if even_nulls / half > 0.20 and even_nulls > odd_nulls * 2:
            return data.decode("utf-16-be", errors="replace")

    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_new_text(path: Path, offset: int) -> tuple[str, int]:
    with path.open("rb") as file_obj:
        file_obj.seek(max(0, offset))
        data = file_obj.read()
        new_offset = file_obj.tell()
    return decode_journal_bytes(data), new_offset
