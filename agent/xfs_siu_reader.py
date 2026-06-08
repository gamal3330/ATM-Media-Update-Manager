from __future__ import annotations

import ctypes
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from xfs_cdm_reader import (
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VERSION_RANGE,
    DEVICE_STATUSES,
    WFS_SUCCESS,
    WFSRESULT,
    WFSVERSION,
    configure_msxfs,
    decode_extra,
    hresult_name,
    lookup_status,
    process_architecture,
    resolve_msxfs_path,
    version_to_text,
)


WFS_INF_SIU_STATUS = 801

WFS_SIU_SENSORS_SIZE = 32
WFS_SIU_DOORS_SIZE = 16
WFS_SIU_INDICATORS_SIZE = 16
WFS_SIU_AUXILIARIES_SIZE = 16
WFS_SIU_GUIDLIGHTS_SIZE = 16

SENSOR_NAMES = {
    0: "operator_switch",
    1: "tamper",
    2: "internal_tamper",
    3: "seismic",
    4: "heat",
    5: "proximity",
    6: "ambient_light",
}

DOOR_NAMES = {
    0: "cabinet",
    1: "safe",
    2: "vandal_shield",
}

INDICATOR_NAMES = {
    0: "open_close",
    1: "fascia_light",
    2: "audio",
    3: "heating",
}

AUXILIARY_NAMES = {
    0: "volume",
    1: "ups",
    2: "remote_status_monitor",
    3: "audible_alarm",
}

GUID_LIGHT_NAMES = {
    0: "card_unit",
    1: "pin_pad",
    2: "notes_dispenser",
    3: "coin_dispenser",
    4: "receipt_printer",
    5: "passbook_printer",
    6: "envelope_depository",
    7: "cheque_unit",
    8: "bill_acceptor",
    9: "envelope_dispenser",
    10: "document_printer",
    11: "coin_acceptor",
    12: "scanner",
}

SENSOR_FLAGS = {
    0x0001: "ON",
    0x0002: "OFF",
    0x0004: "SLOW_FLASH",
    0x0008: "MEDIUM_FLASH",
    0x0010: "QUICK_FLASH",
    0x0080: "CONTINUOUS",
}

OPERATOR_SWITCH_FLAGS = {
    0x0001: "RUN",
    0x0002: "MAINTENANCE",
    0x0004: "SUPERVISOR",
}

PROXIMITY_FLAGS = {
    0x0001: "PRESENT",
    0x0002: "NOT_PRESENT",
}

AMBIENT_LIGHT_FLAGS = {
    0x0001: "VERY_DARK",
    0x0002: "DARK",
    0x0004: "MEDIUM_LIGHT",
    0x0008: "LIGHT",
    0x0010: "VERY_LIGHT",
}

DOOR_FLAGS = {
    0x0001: "CLOSED",
    0x0002: "OPEN",
    0x0004: "LOCKED",
    0x0008: "BOLTED",
    0x0010: "SERVICE",
    0x0020: "KEYBOARD",
    0x0040: "AJAR",
    0x0080: "JAMMED",
}

AUDIO_FLAGS = {
    0x0002: "KEYPRESS",
    0x0004: "EXCLAMATION",
    0x0008: "WARNING",
    0x0010: "ERROR",
    0x0020: "CRITICAL",
}

UPS_FLAGS = {
    0x0002: "LOW",
    0x0004: "ENGAGED",
    0x0008: "POWERING",
    0x0010: "RECOVERED",
}

REMOTE_STATUS_MONITOR_FLAGS = {
    0x0001: "GREEN_LED_ON",
    0x0002: "GREEN_LED_OFF",
    0x0004: "AMBER_LED_ON",
    0x0008: "AMBER_LED_OFF",
    0x0010: "RED_LED_ON",
    0x0020: "RED_LED_OFF",
}


class WFSSIUSTATUS(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("fwDevice", ctypes.c_ushort),
        ("fwSensors", ctypes.c_ushort * WFS_SIU_SENSORS_SIZE),
        ("fwDoors", ctypes.c_ushort * WFS_SIU_DOORS_SIZE),
        ("fwIndicators", ctypes.c_ushort * WFS_SIU_INDICATORS_SIZE),
        ("fwAuxiliaries", ctypes.c_ushort * WFS_SIU_AUXILIARIES_SIZE),
        ("fwGuidLights", ctypes.c_ushort * WFS_SIU_GUIDLIGHTS_SIZE),
        ("lpszExtra", ctypes.c_void_p),
    ]


@dataclass
class SiuPortStatus:
    index: int
    name: str
    code: int
    statuses: list[str]


@dataclass
class XfsSiuStatusResult:
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
    sensors: dict[str, dict[str, Any]] = field(default_factory=dict)
    doors: dict[str, dict[str, Any]] = field(default_factory=dict)
    indicators: dict[str, dict[str, Any]] = field(default_factory=dict)
    auxiliaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    guid_lights: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decode_flags(value: int, mapping: dict[int, str]) -> list[str]:
    if value == 0:
        return ["NOT_AVAILABLE"]
    flags = [name for bit, name in sorted(mapping.items()) if value & bit]
    return flags or [f"UNKNOWN_{value}"]


def port_status(index: int, name: str, code: int, flags: dict[int, str]) -> dict[str, Any]:
    return asdict(SiuPortStatus(index=index, name=name, code=code, statuses=decode_flags(code, flags)))


def sensor_flags(index: int) -> dict[int, str]:
    if index == 0:
        return OPERATOR_SWITCH_FLAGS
    if index == 5:
        return PROXIMITY_FLAGS
    if index == 6:
        return AMBIENT_LIGHT_FLAGS
    return SENSOR_FLAGS


def indicator_flags(index: int) -> dict[int, str]:
    if index == 2:
        return AUDIO_FLAGS
    return SENSOR_FLAGS


def auxiliary_flags(index: int) -> dict[int, str]:
    if index == 1:
        return UPS_FLAGS
    if index == 2:
        return REMOTE_STATUS_MONITOR_FLAGS
    return SENSOR_FLAGS


def parse_ports(values: Any, names: dict[int, str], flags: dict[int, str] | None = None, flags_factory=None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, code in enumerate(values):
        value = int(code)
        name = names.get(index, f"port_{index}")
        active_flags = flags_factory(index) if flags_factory else flags or SENSOR_FLAGS
        result[name] = port_status(index, name, value, active_flags)
    return result


def parse_siu_status(buffer: int) -> dict[str, Any]:
    status = ctypes.cast(buffer, ctypes.POINTER(WFSSIUSTATUS)).contents
    device_code = int(status.fwDevice)
    return {
        "device_code": device_code,
        "device_status": lookup_status(DEVICE_STATUSES, device_code),
        "sensors": parse_ports(status.fwSensors, SENSOR_NAMES, flags_factory=sensor_flags),
        "doors": parse_ports(status.fwDoors, DOOR_NAMES, DOOR_FLAGS),
        "indicators": parse_ports(status.fwIndicators, INDICATOR_NAMES, flags_factory=indicator_flags),
        "auxiliaries": parse_ports(status.fwAuxiliaries, AUXILIARY_NAMES, flags_factory=auxiliary_flags),
        "guid_lights": parse_ports(status.fwGuidLights, GUID_LIGHT_NAMES, SENSOR_FLAGS),
        "extra": decode_extra(int(status.lpszExtra) if status.lpszExtra else None),
    }


def read_siu_status(
    logical_service: str = "SIU",
    msxfs_path: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    version_range: int = DEFAULT_VERSION_RANGE,
) -> XfsSiuStatusResult:
    if os.name != "nt":
        raise RuntimeError("XFS SIU status read is only available on Windows.")
    if process_architecture() != "32-bit":
        raise RuntimeError("XFS SIU status read must use a 32-bit atm-agent.exe when the installed XFS Manager/provider is 32-bit.")
    if not logical_service.strip():
        raise RuntimeError("A SIU logical service name is required, for example: SIU")

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
            b"ATMUnifiedAgent-SIU-Status-ReadOnly",
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
            WFS_INF_SIU_STATUS,
            None,
            timeout_ms,
            ctypes.byref(result_ptr),
        )
        if rc != WFS_SUCCESS:
            raise RuntimeError(f"WFSGetInfo(SIU_STATUS) failed: {hresult_name(rc)} ({rc})")
        if not result_ptr:
            raise RuntimeError("WFSGetInfo returned an empty result pointer.")

        result = result_ptr.contents
        if int(result.hResult) != WFS_SUCCESS:
            raise RuntimeError(
                f"WFSGetInfo(SIU_STATUS) result failed: {hresult_name(int(result.hResult))} ({int(result.hResult)})"
            )
        if not result.lpBuffer:
            raise RuntimeError("WFSGetInfo(SIU_STATUS) returned an empty status buffer.")

        status = parse_siu_status(int(result.lpBuffer))
        return XfsSiuStatusResult(
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


def format_status_result(result: XfsSiuStatusResult) -> str:
    lines = [
        "XFS SIU Status Read - READ ONLY",
        f"Logical Service: {result.logical_service}",
        f"Process Architecture: {result.process_architecture}",
        f"msxfs.dll: {result.msxfs_path}",
        f"XFS Manager Version: {result.xfs_manager_version}",
        f"Service Version: {result.service_version}",
        f"SPI Version: {result.spi_version}",
        "",
        f"Device: {result.device_status} ({result.device_code})",
        "",
        "Doors:",
    ]
    for item in result.doors.values():
        lines.append(f"  - {item['name']}: {'+'.join(item['statuses'])} ({item['code']})")
    lines.append("")
    lines.append("Sensors:")
    for name in ("operator_switch", "tamper", "internal_tamper", "seismic", "heat", "proximity", "ambient_light"):
        item = result.sensors.get(name)
        if item:
            lines.append(f"  - {item['name']}: {'+'.join(item['statuses'])} ({item['code']})")
    if result.extra:
        lines.append("")
        lines.append("Extra:")
        lines.extend(f"  - {key}={value}" for key, value in sorted(result.extra.items()))
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Read-only XFS SIU status read")
    parser.add_argument("--logical-service", default="SIU")
    parser.add_argument("--msxfs-path")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--version-range", default=f"0x{DEFAULT_VERSION_RANGE:08X}")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = read_siu_status(
        args.logical_service,
        msxfs_path=args.msxfs_path,
        timeout_ms=args.timeout_ms,
        version_range=int(str(args.version_range), 0),
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_status_result(result))


if __name__ == "__main__":
    main()
