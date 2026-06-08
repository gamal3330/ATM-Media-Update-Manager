from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


WFS_INF_CDM_STATUS = 301
WFS_INF_CDM_CASH_UNIT_INFO = 303
DEFAULT_TIMEOUT_MS = 20000
DEFAULT_VERSION_RANGE = 0x00031E03  # 3.00 through 3.30

WFS_SUCCESS = 0


XFS_ERRORS = {
    0: "WFS_SUCCESS",
    -1: "WFS_ERR_ALREADY_STARTED",
    -2: "WFS_ERR_API_VER_TOO_HIGH",
    -3: "WFS_ERR_API_VER_TOO_LOW",
    -4: "WFS_ERR_CANCELED",
    -5: "WFS_ERR_CFG_INVALID_HKEY",
    -6: "WFS_ERR_CFG_INVALID_NAME",
    -7: "WFS_ERR_CFG_INVALID_SUBKEY",
    -8: "WFS_ERR_CFG_INVALID_VALUE",
    -9: "WFS_ERR_CFG_KEY_NOT_EMPTY",
    -10: "WFS_ERR_CFG_NAME_TOO_LONG",
    -11: "WFS_ERR_CFG_NO_MORE_ITEMS",
    -12: "WFS_ERR_CFG_VALUE_TOO_LONG",
    -13: "WFS_ERR_DEV_NOT_READY",
    -14: "WFS_ERR_HARDWARE_ERROR",
    -15: "WFS_ERR_INTERNAL_ERROR",
    -16: "WFS_ERR_INVALID_ADDRESS",
    -17: "WFS_ERR_INVALID_APP_HANDLE",
    -18: "WFS_ERR_INVALID_BUFFER",
    -19: "WFS_ERR_INVALID_CATEGORY",
    -20: "WFS_ERR_INVALID_COMMAND",
    -21: "WFS_ERR_INVALID_EVENT_CLASS",
    -22: "WFS_ERR_INVALID_HSERVICE",
    -23: "WFS_ERR_INVALID_HPROVIDER",
    -24: "WFS_ERR_INVALID_HWND",
    -25: "WFS_ERR_INVALID_HWNDREG",
    -26: "WFS_ERR_INVALID_POINTER",
    -27: "WFS_ERR_INVALID_REQ_ID",
    -28: "WFS_ERR_INVALID_RESULT",
    -29: "WFS_ERR_INVALID_SERVPROV",
    -30: "WFS_ERR_INVALID_TIMER",
    -31: "WFS_ERR_INVALID_TRACELEVEL",
    -32: "WFS_ERR_LOCKED",
    -33: "WFS_ERR_NO_BLOCKING_CALL",
    -34: "WFS_ERR_NO_SERVPROV",
    -35: "WFS_ERR_NO_SUCH_THREAD",
    -36: "WFS_ERR_NO_TIMER",
    -37: "WFS_ERR_NOT_LOCKED",
    -38: "WFS_ERR_NOT_OK_TO_UNLOAD",
    -39: "WFS_ERR_NOT_STARTED",
    -40: "WFS_ERR_NOT_REGISTERED",
    -41: "WFS_ERR_OP_IN_PROGRESS",
    -42: "WFS_ERR_OUT_OF_MEMORY",
    -43: "WFS_ERR_SERVICE_NOT_FOUND",
    -44: "WFS_ERR_SPI_VER_TOO_HIGH",
    -45: "WFS_ERR_SPI_VER_TOO_LOW",
    -46: "WFS_ERR_SRVC_VER_TOO_HIGH",
    -47: "WFS_ERR_SRVC_VER_TOO_LOW",
    -48: "WFS_ERR_TIMEOUT",
    -49: "WFS_ERR_UNSUPP_CATEGORY",
    -50: "WFS_ERR_UNSUPP_COMMAND",
    -51: "WFS_ERR_VERSION_ERROR_IN_SRVC",
    -52: "WFS_ERR_INVALID_DATA",
    -53: "WFS_ERR_SOFTWARE_ERROR",
    -54: "WFS_ERR_CONNECTION_LOST",
    -55: "WFS_ERR_USER_ERROR",
    -56: "WFS_ERR_UNSUPP_DATA",
}

CU_TYPES = {
    0: "NA",
    1: "NA",
    2: "REJECT_CASSETTE",
    3: "BILL_CASSETTE",
    4: "COIN_CYLINDER",
    5: "RETRACT_CASSETTE",
    6: "COUPON",
    7: "DOCUMENT",
    8: "REPLENISHMENT_CONTAINER",
    9: "RECYCLING",
}

CU_STATUSES = {
    0: "OK",
    1: "FULL",
    2: "HIGH",
    3: "LOW",
    4: "EMPTY",
    5: "INOPERATIVE",
    6: "MISSING",
    7: "NO_VALUE",
    8: "NO_REFERENCE",
    9: "MANIPULATED",
}

DEVICE_STATUSES = {
    0: "ONLINE",
    1: "OFFLINE",
    2: "POWEROFF",
    3: "NODEVICE",
    4: "HWERROR",
    5: "USERERROR",
    6: "BUSY",
    7: "FRAUDATTEMPT",
    8: "POTENTIALFRAUD",
}

SAFE_DOOR_STATUSES = {
    1: "NOTSUPPORTED",
    2: "OPEN",
    3: "CLOSED",
    4: "UNKNOWN",
}

DISPENSER_STATUSES = {
    0: "OK",
    1: "CUSTATE",
    2: "CUSTOP",
    3: "CUUNKNOWN",
}

INTERMEDIATE_STACKER_STATUSES = {
    0: "EMPTY",
    1: "NOTEMPTY",
    2: "NOTEMPTYCUST",
    3: "NOTEMPTYUNKNOWN",
    4: "UNKNOWN",
    5: "NOTSUPPORTED",
}

SHUTTER_STATUSES = {
    0: "CLOSED",
    1: "OPEN",
    2: "JAMMED",
    3: "UNKNOWN",
    4: "NOTSUPPORTED",
}

TRANSPORT_STATUSES = {
    0: "OK",
    1: "INOPERATIVE",
    2: "UNKNOWN",
    3: "NOTSUPPORTED",
}

TRANSPORT_POSITION_STATUSES = {
    0: "EMPTY",
    1: "NOTEMPTY",
    2: "NOTEMPTYCUST",
    3: "NOTEMPTYUNKNOWN",
    4: "NOTSUPPORTED",
}

JAMMED_SHUTTER_POSITIONS = {
    0: "NOTSUPPORTED",
    1: "NOTJAMMED",
    2: "OPEN",
    3: "PARTIALLYOPEN",
    4: "CLOSED",
    5: "UNKNOWN",
}


class SYSTEMTIME(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("wYear", ctypes.c_ushort),
        ("wMonth", ctypes.c_ushort),
        ("wDayOfWeek", ctypes.c_ushort),
        ("wDay", ctypes.c_ushort),
        ("wHour", ctypes.c_ushort),
        ("wMinute", ctypes.c_ushort),
        ("wSecond", ctypes.c_ushort),
        ("wMilliseconds", ctypes.c_ushort),
    ]


class WFSVERSION(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("wVersion", ctypes.c_ushort),
        ("wLowVersion", ctypes.c_ushort),
        ("wHighVersion", ctypes.c_ushort),
        ("szDescription", ctypes.c_char * 257),
        ("szSystemStatus", ctypes.c_char * 257),
    ]


class WFSRESULT(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("RequestID", ctypes.c_ulong),
        ("hService", ctypes.c_ushort),
        ("tsTimestamp", SYSTEMTIME),
        ("hResult", ctypes.c_long),
        ("dwCommandCode", ctypes.c_ulong),
        ("lpBuffer", ctypes.c_void_p),
    ]


class WFSCDMPHCU(ctypes.Structure):
    _pack_ = 1
    pass


LPWFSCDMPHCU = ctypes.POINTER(WFSCDMPHCU)

WFSCDMPHCU._fields_ = [
    ("lpPhysicalPositionName", ctypes.c_char_p),
    ("cUnitID", ctypes.c_char * 5),
    ("ulInitialCount", ctypes.c_ulong),
    ("ulCount", ctypes.c_ulong),
    ("ulRejectCount", ctypes.c_ulong),
    ("ulMaximum", ctypes.c_ulong),
    ("usPStatus", ctypes.c_ushort),
    ("bHardwareSensor", ctypes.c_int),
    ("ulDispensedCount", ctypes.c_ulong),
    ("ulPresentedCount", ctypes.c_ulong),
    ("ulRetractedCount", ctypes.c_ulong),
]


class WFSCDMCASHUNIT(ctypes.Structure):
    _pack_ = 1
    pass


LPWFSCDMCASHUNIT = ctypes.POINTER(WFSCDMCASHUNIT)

WFSCDMCASHUNIT._fields_ = [
    ("usNumber", ctypes.c_ushort),
    ("usType", ctypes.c_ushort),
    ("lpszCashUnitName", ctypes.c_char_p),
    ("cUnitID", ctypes.c_char * 5),
    ("cCurrencyID", ctypes.c_char * 3),
    ("ulValues", ctypes.c_ulong),
    ("ulInitialCount", ctypes.c_ulong),
    ("ulCount", ctypes.c_ulong),
    ("ulRejectCount", ctypes.c_ulong),
    ("ulMinimum", ctypes.c_ulong),
    ("ulMaximum", ctypes.c_ulong),
    ("bAppLock", ctypes.c_int),
    ("usStatus", ctypes.c_ushort),
    ("usNumPhysicalCUs", ctypes.c_ushort),
    ("lppPhysical", ctypes.POINTER(LPWFSCDMPHCU)),
    ("ulDispensedCount", ctypes.c_ulong),
    ("ulPresentedCount", ctypes.c_ulong),
    ("ulRetractedCount", ctypes.c_ulong),
]


class WFSCDMCUINFO(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("usTellerID", ctypes.c_ushort),
        ("usCount", ctypes.c_ushort),
        ("lppList", ctypes.POINTER(LPWFSCDMCASHUNIT)),
    ]


class WFSCDMSTATUS(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("fwDevice", ctypes.c_ushort),
        ("fwSafeDoor", ctypes.c_ushort),
        ("fwDispenser", ctypes.c_ushort),
        ("fwIntermediateStacker", ctypes.c_ushort),
        ("fwShutter", ctypes.c_ushort),
        ("fwTransport", ctypes.c_ushort),
        ("fwTransportStatus", ctypes.c_ushort),
        ("fwJammedShutterPosition", ctypes.c_ushort),
        ("lpszExtra", ctypes.c_void_p),
    ]


@dataclass
class PhysicalCashUnitRead:
    physical_position_name: str
    unit_id: str
    initial_count: int
    current_count: int
    reject_count: int
    max_capacity: int
    physical_status_code: int
    physical_status: str
    hardware_sensor: bool
    dispensed_count: int
    presented_count: int
    retracted_count: int


@dataclass
class CashUnitRead:
    cassette_no: int
    unit_type_code: int
    unit_type: str
    cassette_name: str
    unit_id: str
    currency: str
    denomination: int
    initial_count: int
    current_count: int
    reject_count: int
    low_threshold: int
    max_capacity: int
    app_lock: bool
    status_code: int
    status: str
    physical_units: list[PhysicalCashUnitRead] = field(default_factory=list)
    dispensed_count: int = 0
    presented_count: int = 0
    retracted_count: int = 0


@dataclass
class XfsCdmReadResult:
    read_only: bool
    process_architecture: str
    msxfs_path: str
    logical_service: str
    version_range: str
    timeout_ms: int
    xfs_manager_version: str
    service_version: str
    spi_version: str
    cash_units: list[CashUnitRead]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class XfsCdmStatusResult:
    read_only: bool
    process_architecture: str
    msxfs_path: str
    logical_service: str
    version_range: str
    timeout_ms: int
    xfs_manager_version: str
    service_version: str
    spi_version: str
    device_code: int
    device_status: str
    safe_door_code: int
    safe_door_status: str
    dispenser_code: int
    dispenser_status: str
    intermediate_stacker_code: int
    intermediate_stacker_status: str
    shutter_code: int
    shutter_status: str
    transport_code: int
    transport_status: str
    transport_position_code: int
    transport_position_status: str
    jammed_shutter_position_code: int
    jammed_shutter_position: str
    extra: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_architecture() -> str:
    return "64-bit" if sys.maxsize > 2**32 else "32-bit"


def decode_bytes(value: bytes | None) -> str:
    if not value:
        return ""
    return value.split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()


def version_to_text(value: int) -> str:
    major = value & 0x00FF
    minor = (value & 0xFF00) >> 8
    return f"{major}.{minor:02d}"


def hresult_name(value: int) -> str:
    return XFS_ERRORS.get(value, f"XFS_ERROR_{value}")


def status_name(value: int) -> str:
    return CU_STATUSES.get(value, f"UNKNOWN_{value}")


def lookup_status(mapping: dict[int, str], value: int) -> str:
    return mapping.get(value, f"UNKNOWN_{value}")


def type_name(value: int) -> str:
    return CU_TYPES.get(value, f"UNKNOWN_{value}")


def candidate_msxfs_paths() -> list[Path]:
    paths: list[Path] = []
    configured = os.environ.get("ATM_MSXFS_PATH")
    if configured:
        paths.append(Path(configured))
    found = ctypes.util.find_library("msxfs")
    if found:
        paths.append(Path(found))
    common_x86 = os.environ.get("CommonProgramFiles(x86)")
    common = os.environ.get("CommonProgramFiles")
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for base in (common_x86, common):
        if base:
            paths.append(Path(base) / "NCR" / "msxfs.dll")
            paths.append(Path(base) / "GRG" / "msxfs.dll")
            paths.append(Path(base) / "XFS" / "msxfs.dll")
            paths.append(Path(base) / "msxfs.dll")
    paths.extend([windir / "SysWOW64" / "msxfs.dll", windir / "System32" / "msxfs.dll"])
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(str(path))
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def resolve_msxfs_path(msxfs_path: str | None = None) -> Path:
    if msxfs_path:
        path = Path(msxfs_path)
        if not path.exists():
            raise RuntimeError(f"msxfs.dll was not found at {path}")
        return path
    for path in candidate_msxfs_paths():
        if path.exists():
            return path
    raise RuntimeError("msxfs.dll was not found. Run xfs-cdm-diagnose first.")


def configure_msxfs(msxfs: ctypes.WinDLL) -> None:
    msxfs.WFSStartUp.argtypes = [ctypes.c_ulong, ctypes.POINTER(WFSVERSION)]
    msxfs.WFSStartUp.restype = ctypes.c_long

    msxfs.WFSCleanUp.argtypes = []
    msxfs.WFSCleanUp.restype = ctypes.c_long

    msxfs.WFSOpen.argtypes = [
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(WFSVERSION),
        ctypes.POINTER(WFSVERSION),
        ctypes.POINTER(ctypes.c_ushort),
    ]
    msxfs.WFSOpen.restype = ctypes.c_long

    msxfs.WFSClose.argtypes = [ctypes.c_ushort]
    msxfs.WFSClose.restype = ctypes.c_long

    msxfs.WFSGetInfo.argtypes = [
        ctypes.c_ushort,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.POINTER(WFSRESULT)),
    ]
    msxfs.WFSGetInfo.restype = ctypes.c_long

    msxfs.WFSFreeResult.argtypes = [ctypes.POINTER(WFSRESULT)]
    msxfs.WFSFreeResult.restype = ctypes.c_long


def decode_extra(pointer: int | None, max_bytes: int = 8192) -> dict[str, str]:
    if not pointer:
        return {}
    raw = bytearray()
    zero_run = 0
    for offset in range(max_bytes):
        chunk = ctypes.string_at(pointer + offset, 1)
        byte = chunk[0]
        raw.append(byte)
        if byte == 0:
            zero_run += 1
            if zero_run >= 2:
                break
        else:
            zero_run = 0
    entries = bytes(raw).split(b"\x00")
    result: dict[str, str] = {}
    for entry in entries:
        text = entry.decode("latin-1", errors="replace").strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            result[key.strip()] = value.strip()
        else:
            result[text] = ""
    return result


def parse_cash_unit(unit: WFSCDMCASHUNIT) -> CashUnitRead:
    physical_units: list[PhysicalCashUnitRead] = []
    for index in range(int(unit.usNumPhysicalCUs)):
        if not unit.lppPhysical:
            break
        physical_ptr = unit.lppPhysical[index]
        if not physical_ptr:
            continue
        physical = physical_ptr.contents
        physical_units.append(
            PhysicalCashUnitRead(
                physical_position_name=decode_bytes(physical.lpPhysicalPositionName),
                unit_id=decode_bytes(physical.cUnitID),
                initial_count=int(physical.ulInitialCount),
                current_count=int(physical.ulCount),
                reject_count=int(physical.ulRejectCount),
                max_capacity=int(physical.ulMaximum),
                physical_status_code=int(physical.usPStatus),
                physical_status=status_name(int(physical.usPStatus)),
                hardware_sensor=bool(physical.bHardwareSensor),
                dispensed_count=int(physical.ulDispensedCount),
                presented_count=int(physical.ulPresentedCount),
                retracted_count=int(physical.ulRetractedCount),
            )
        )

    return CashUnitRead(
        cassette_no=int(unit.usNumber),
        unit_type_code=int(unit.usType),
        unit_type=type_name(int(unit.usType)),
        cassette_name=decode_bytes(unit.lpszCashUnitName),
        unit_id=decode_bytes(unit.cUnitID),
        currency=decode_bytes(unit.cCurrencyID),
        denomination=int(unit.ulValues),
        initial_count=int(unit.ulInitialCount),
        current_count=int(unit.ulCount),
        reject_count=int(unit.ulRejectCount),
        low_threshold=int(unit.ulMinimum),
        max_capacity=int(unit.ulMaximum),
        app_lock=bool(unit.bAppLock),
        status_code=int(unit.usStatus),
        status=status_name(int(unit.usStatus)),
        physical_units=physical_units,
        dispensed_count=int(unit.ulDispensedCount),
        presented_count=int(unit.ulPresentedCount),
        retracted_count=int(unit.ulRetractedCount),
    )


def parse_cash_units(buffer: int) -> list[CashUnitRead]:
    info = ctypes.cast(buffer, ctypes.POINTER(WFSCDMCUINFO)).contents
    units: list[CashUnitRead] = []
    for index in range(int(info.usCount)):
        unit_ptr = info.lppList[index]
        if not unit_ptr:
            continue
        units.append(parse_cash_unit(unit_ptr.contents))
    return units


def parse_cdm_status(buffer: int) -> dict[str, Any]:
    status = ctypes.cast(buffer, ctypes.POINTER(WFSCDMSTATUS)).contents
    device_code = int(status.fwDevice)
    safe_door_code = int(status.fwSafeDoor)
    dispenser_code = int(status.fwDispenser)
    intermediate_stacker_code = int(status.fwIntermediateStacker)
    shutter_code = int(status.fwShutter)
    transport_code = int(status.fwTransport)
    transport_position_code = int(status.fwTransportStatus)
    jammed_shutter_position_code = int(status.fwJammedShutterPosition)
    return {
        "device_code": device_code,
        "device_status": lookup_status(DEVICE_STATUSES, device_code),
        "safe_door_code": safe_door_code,
        "safe_door_status": lookup_status(SAFE_DOOR_STATUSES, safe_door_code),
        "dispenser_code": dispenser_code,
        "dispenser_status": lookup_status(DISPENSER_STATUSES, dispenser_code),
        "intermediate_stacker_code": intermediate_stacker_code,
        "intermediate_stacker_status": lookup_status(INTERMEDIATE_STACKER_STATUSES, intermediate_stacker_code),
        "shutter_code": shutter_code,
        "shutter_status": lookup_status(SHUTTER_STATUSES, shutter_code),
        "transport_code": transport_code,
        "transport_status": lookup_status(TRANSPORT_STATUSES, transport_code),
        "transport_position_code": transport_position_code,
        "transport_position_status": lookup_status(TRANSPORT_POSITION_STATUSES, transport_position_code),
        "jammed_shutter_position_code": jammed_shutter_position_code,
        "jammed_shutter_position": lookup_status(JAMMED_SHUTTER_POSITIONS, jammed_shutter_position_code),
        "extra": decode_extra(int(status.lpszExtra) if status.lpszExtra else None),
    }


def read_cdm_status(
    logical_service: str,
    msxfs_path: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    version_range: int = DEFAULT_VERSION_RANGE,
) -> XfsCdmStatusResult:
    if os.name != "nt":
        raise RuntimeError("XFS CDM status read is only available on Windows.")
    if process_architecture() != "32-bit":
        raise RuntimeError("XFS CDM status read must use a 32-bit atm-agent.exe when the installed XFS Manager/provider is 32-bit.")
    if not logical_service.strip():
        raise RuntimeError("A logical service name is required, for example: MediaDispenser1")

    resolved_msxfs = resolve_msxfs_path(msxfs_path)
    msxfs = ctypes.WinDLL(str(resolved_msxfs))
    configure_msxfs(msxfs)

    manager_version = WFSVERSION()
    service_version = WFSVERSION()
    spi_version = WFSVERSION()
    hservice = ctypes.c_ushort(0)
    result_ptr: ctypes.POINTER(WFSRESULT) | None = None

    started = False
    opened = False
    try:
        rc = msxfs.WFSStartUp(version_range, ctypes.byref(manager_version))
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSStartUp failed: {hresult_name(rc)} ({rc})")
        started = True

        rc = msxfs.WFSOpen(
            logical_service.encode("ascii"),
            None,
            b"ATMUnifiedAgent-CDM-Status-ReadOnly",
            0,
            timeout_ms,
            version_range,
            ctypes.byref(service_version),
            ctypes.byref(spi_version),
            ctypes.byref(hservice),
        )
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSOpen({logical_service}) failed: {hresult_name(rc)} ({rc})")
        opened = True

        result_ptr = ctypes.POINTER(WFSRESULT)()
        rc = msxfs.WFSGetInfo(
            hservice,
            WFS_INF_CDM_STATUS,
            None,
            timeout_ms,
            ctypes.byref(result_ptr),
        )
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSGetInfo(CDM_STATUS) failed: {hresult_name(rc)} ({rc})")
        if not result_ptr:
            raise RuntimeError("WFSGetInfo returned an empty result pointer.")

        result = result_ptr.contents
        if int(result.hResult) != WFS_SUCCESS:
            raise RuntimeError(
                f"WFSGetInfo(CDM_STATUS) result failed: {hresult_name(int(result.hResult))} ({int(result.hResult)})"
            )
        if not result.lpBuffer:
            raise RuntimeError("WFSGetInfo(CDM_STATUS) returned an empty status buffer.")

        status = parse_cdm_status(int(result.lpBuffer))
        return XfsCdmStatusResult(
            read_only=True,
            process_architecture=process_architecture(),
            msxfs_path=str(resolved_msxfs),
            logical_service=logical_service,
            version_range=f"0x{version_range:08X}",
            timeout_ms=timeout_ms,
            xfs_manager_version=version_to_text(int(manager_version.wVersion)),
            service_version=version_to_text(int(service_version.wVersion)),
            spi_version=version_to_text(int(spi_version.wVersion)),
            **status,
        )
    finally:
        if result_ptr:
            msxfs.WFSFreeResult(result_ptr)
        if opened:
            msxfs.WFSClose(hservice)
        if started:
            msxfs.WFSCleanUp()


def read_cash_units(
    logical_service: str,
    msxfs_path: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    version_range: int = DEFAULT_VERSION_RANGE,
) -> XfsCdmReadResult:
    if os.name != "nt":
        raise RuntimeError("XFS CDM read is only available on Windows.")
    if process_architecture() != "32-bit":
        raise RuntimeError("XFS CDM read must use a 32-bit atm-agent.exe when the installed XFS Manager/provider is 32-bit.")
    if not logical_service.strip():
        raise RuntimeError("A logical service name is required, for example: MediaDispenser1")

    resolved_msxfs = resolve_msxfs_path(msxfs_path)
    msxfs = ctypes.WinDLL(str(resolved_msxfs))
    configure_msxfs(msxfs)

    manager_version = WFSVERSION()
    service_version = WFSVERSION()
    spi_version = WFSVERSION()
    hservice = ctypes.c_ushort(0)
    result_ptr: ctypes.POINTER(WFSRESULT) | None = None
    notes: list[str] = []

    started = False
    opened = False
    try:
        rc = msxfs.WFSStartUp(version_range, ctypes.byref(manager_version))
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSStartUp failed: {hresult_name(rc)} ({rc})")
        started = True

        rc = msxfs.WFSOpen(
            logical_service.encode("ascii"),
            None,
            b"ATMUnifiedAgent-CDM-ReadOnly",
            0,
            timeout_ms,
            version_range,
            ctypes.byref(service_version),
            ctypes.byref(spi_version),
            ctypes.byref(hservice),
        )
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSOpen({logical_service}) failed: {hresult_name(rc)} ({rc})")
        opened = True

        result_ptr = ctypes.POINTER(WFSRESULT)()
        rc = msxfs.WFSGetInfo(
            hservice,
            WFS_INF_CDM_CASH_UNIT_INFO,
            None,
            timeout_ms,
            ctypes.byref(result_ptr),
        )
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSGetInfo(CASH_UNIT_INFO) failed: {hresult_name(rc)} ({rc})")
        if not result_ptr:
            raise RuntimeError("WFSGetInfo returned an empty result pointer.")

        result = result_ptr.contents
        if int(result.hResult) != WFS_SUCCESS:
            raise RuntimeError(
                f"WFSGetInfo(CASH_UNIT_INFO) result failed: {hresult_name(int(result.hResult))} ({int(result.hResult)})"
            )
        if not result.lpBuffer:
            raise RuntimeError("WFSGetInfo(CASH_UNIT_INFO) returned an empty cash unit buffer.")

        cash_units = parse_cash_units(int(result.lpBuffer))
        if not cash_units:
            notes.append("WFSGetInfo succeeded but returned zero cash units.")

        return XfsCdmReadResult(
            read_only=True,
            process_architecture=process_architecture(),
            msxfs_path=str(resolved_msxfs),
            logical_service=logical_service,
            version_range=f"0x{version_range:08X}",
            timeout_ms=timeout_ms,
            xfs_manager_version=version_to_text(int(manager_version.wVersion)),
            service_version=version_to_text(int(service_version.wVersion)),
            spi_version=version_to_text(int(spi_version.wVersion)),
            cash_units=cash_units,
            notes=notes,
        )
    finally:
        if result_ptr:
            msxfs.WFSFreeResult(result_ptr)
        if opened:
            msxfs.WFSClose(hservice)
        if started:
            msxfs.WFSCleanUp()


def format_read_result(result: XfsCdmReadResult) -> str:
    lines = [
        "XFS CDM Cash Unit Read - READ ONLY",
        f"Logical Service: {result.logical_service}",
        f"Process Architecture: {result.process_architecture}",
        f"msxfs.dll: {result.msxfs_path}",
        f"XFS Manager Version: {result.xfs_manager_version}",
        f"Service Version: {result.service_version}",
        f"SPI Version: {result.spi_version}",
        "",
        "Cash Units:",
    ]
    for unit in result.cash_units:
        lines.append(
            "  - "
            f"#{unit.cassette_no} {unit.unit_type} {unit.currency} {unit.denomination} "
            f"count={unit.current_count} initial={unit.initial_count} "
            f"reject={unit.reject_count} retract={unit.retracted_count} status={unit.status}"
        )
    if not result.cash_units:
        lines.append("  - none")
    if result.notes:
        lines.append("")
        lines.append("Notes:")
        lines.extend(f"  - {note}" for note in result.notes)
    return "\n".join(lines)


def format_status_result(result: XfsCdmStatusResult) -> str:
    lines = [
        "XFS CDM Status Read - READ ONLY",
        f"Logical Service: {result.logical_service}",
        f"Process Architecture: {result.process_architecture}",
        f"msxfs.dll: {result.msxfs_path}",
        f"XFS Manager Version: {result.xfs_manager_version}",
        f"Service Version: {result.service_version}",
        f"SPI Version: {result.spi_version}",
        "",
        "Status:",
        f"  - Device: {result.device_status} ({result.device_code})",
        f"  - Safe Door: {result.safe_door_status} ({result.safe_door_code})",
        f"  - Dispenser: {result.dispenser_status} ({result.dispenser_code})",
        f"  - Intermediate Stacker: {result.intermediate_stacker_status} ({result.intermediate_stacker_code})",
        f"  - Shutter: {result.shutter_status} ({result.shutter_code})",
        f"  - Transport: {result.transport_status} ({result.transport_code})",
        f"  - Transport Position: {result.transport_position_status} ({result.transport_position_code})",
        f"  - Jammed Shutter Position: {result.jammed_shutter_position} ({result.jammed_shutter_position_code})",
    ]
    if result.extra:
        lines.append("")
        lines.append("Extra:")
        lines.extend(f"  - {key}={value}" for key, value in sorted(result.extra.items()))
    if result.notes:
        lines.append("")
        lines.append("Notes:")
        lines.extend(f"  - {note}" for note in result.notes)
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Read-only XFS CDM cash unit/status read")
    parser.add_argument("--logical-service", default="MediaDispenser1")
    parser.add_argument("--msxfs-path")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--version-range", default=f"0x{DEFAULT_VERSION_RANGE:08X}")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reader = read_cdm_status if args.status else read_cash_units
    result = reader(
        args.logical_service,
        msxfs_path=args.msxfs_path,
        timeout_ms=args.timeout_ms,
        version_range=int(str(args.version_range), 0),
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_status_result(result) if args.status else format_read_result(result))


if __name__ == "__main__":
    main()
