from __future__ import annotations

import argparse
import ctypes.util
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CDM_HINTS = (
    "CDM",
    "CASH",
    "CURRENCY DISPENSER",
    "MEDIA DISPENSER",
    "DISPENSER",
    "NCR_CDM",
    "NCR_CDMSP",
    "NCR_CDM2SP",
    "GRG",
)
REGISTRY_ROOTS = (
    r"SOFTWARE\XFS",
    r"SOFTWARE\WOW6432Node\XFS",
    r"SOFTWARE\WOSA",
    r"SOFTWARE\WOW6432Node\WOSA",
    r"SOFTWARE\NCR",
    r"SOFTWARE\WOW6432Node\NCR",
    r"SOFTWARE\GRG",
    r"SOFTWARE\WOW6432Node\GRG",
)


@dataclass
class FileEntry:
    path: str
    exists: bool
    size_bytes: int | None = None


@dataclass
class RegistryHit:
    root: str
    path: str
    name: str
    value: str


@dataclass
class XfsCdmDiagnostics:
    read_only: bool
    os_name: str
    os_architecture: str
    process_architecture: str
    xfs_root: str | None
    aptra_root: str | None
    xfs_manager_dir: str | None
    cdm_provider_dir: str | None
    cdm_provider_files: list[FileEntry] = field(default_factory=list)
    xfs_manager_files: list[FileEntry] = field(default_factory=list)
    msxfs_candidates: list[FileEntry] = field(default_factory=list)
    registry_hits: list[RegistryHit] = field(default_factory=list)
    logical_service_candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_architecture() -> str:
    return "64-bit" if sys.maxsize > 2**32 else "32-bit"


def candidate_xfs_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value) / "NCR APTRA")
            roots.append(Path(value) / "GRG Banking")
            roots.append(Path(value) / "GRG")
    roots.extend(
        [
            Path(r"C:\Program Files (x86)\NCR APTRA"),
            Path(r"C:\Program Files\NCR APTRA"),
            Path(r"C:\Program Files (x86)\GRG Banking"),
            Path(r"C:\Program Files\GRG Banking"),
            Path(r"C:\Program Files (x86)\GRG"),
            Path(r"C:\Program Files\GRG"),
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for item in roots:
        key = os.path.normcase(str(item))
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def resolve_xfs_root(xfs_root: str | None = None) -> Path | None:
    if xfs_root:
        root = Path(xfs_root)
        return root if root.exists() else root
    for root in candidate_xfs_roots():
        if root.exists():
            return root
    return None


def resolve_aptra_root(aptra_root: str | None = None) -> Path | None:
    return resolve_xfs_root(aptra_root)


def file_entry(path: Path) -> FileEntry:
    if not path.exists():
        return FileEntry(path=str(path), exists=False)
    return FileEntry(path=str(path), exists=True, size_bytes=path.stat().st_size)


def list_directory_files(path: Path | None, patterns: tuple[str, ...]) -> list[FileEntry]:
    if path is None or not path.exists():
        return []
    suffixes = {Path(pattern).suffix.lower() for pattern in patterns if Path(pattern).suffix}
    entries = [
        file_entry(item)
        for item in sorted(path.iterdir())
        if item.is_file() and (not suffixes or item.suffix.lower() in suffixes)
    ]
    deduped: list[FileEntry] = []
    seen: set[str] = set()
    for entry in entries:
        key = os.path.normcase(entry.path)
        if key not in seen:
            deduped.append(entry)
            seen.add(key)
    return deduped


def msxfs_candidate_paths(aptra_root: Path | None) -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("ATM_MSXFS_PATH")
    if configured:
        candidates.append(Path(configured))
    found = ctypes.util.find_library("msxfs")
    if found:
        candidates.append(Path(found))
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates.extend([windir / "System32" / "msxfs.dll", windir / "SysWOW64" / "msxfs.dll"])
    common_x86 = os.environ.get("CommonProgramFiles(x86)")
    common = os.environ.get("CommonProgramFiles")
    for base in (common_x86, common):
        if base:
            candidates.append(Path(base) / "NCR" / "msxfs.dll")
            candidates.append(Path(base) / "GRG" / "msxfs.dll")
            candidates.append(Path(base) / "XFS" / "msxfs.dll")
            candidates.append(Path(base) / "msxfs.dll")
    if aptra_root is not None:
        candidates.extend(
            [
                aptra_root / "XFS Manager" / "msxfs.dll",
                aptra_root / "XFS Manager" / "xfs1.cab",
            ]
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = os.path.normcase(str(item))
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def value_to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def registry_contains_cdm(text: str) -> bool:
    upper = text.upper()
    return any(hint in upper for hint in CDM_HINTS)


def scan_registry_key(winreg_module, root_handle, root_name: str, subkey: str, max_depth: int = 5) -> list[RegistryHit]:
    hits: list[RegistryHit] = []

    def walk(path: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            with winreg_module.OpenKey(root_handle, path) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg_module.EnumValue(key, index)
                    except OSError:
                        break
                    text = value_to_text(value)
                    if registry_contains_cdm(path) or registry_contains_cdm(name) or registry_contains_cdm(text):
                        hits.append(RegistryHit(root=root_name, path=path, name=name or "(default)", value=text))
                    index += 1

                index = 0
                while True:
                    try:
                        child = winreg_module.EnumKey(key, index)
                    except OSError:
                        break
                    child_path = f"{path}\\{child}"
                    if registry_contains_cdm(child_path):
                        hits.append(RegistryHit(root=root_name, path=child_path, name="(key)", value=child))
                    walk(child_path, depth + 1)
                    index += 1
        except OSError:
            return

    walk(subkey, 0)
    return hits


def scan_registry_for_cdm() -> list[RegistryHit]:
    if os.name != "nt":
        return []
    import winreg

    hits: list[RegistryHit] = []
    for subkey in REGISTRY_ROOTS:
        hits.extend(scan_registry_key(winreg, winreg.HKEY_LOCAL_MACHINE, "HKLM", subkey))
    return hits


def logical_service_candidates(registry_hits: list[RegistryHit]) -> list[str]:
    candidates: set[str] = set()
    for hit in registry_hits:
        parts = hit.path.split("\\")
        for index, part in enumerate(parts):
            if part.upper() in {"LOGICAL_SERVICES", "LOGICALSERVICES", "LOGICAL SERVICE", "LOGICALSERVICE"}:
                if index + 1 < len(parts):
                    candidates.add(parts[index + 1])
        for token in (hit.name, hit.value):
            text = str(token).strip()
            if text and registry_contains_cdm(text) and len(text) <= 80:
                candidates.add(text)
    return sorted(candidates)


def build_next_steps(result: XfsCdmDiagnostics) -> list[str]:
    steps: list[str] = []
    if result.process_architecture == "64-bit":
        steps.append("Build and run the real XFS CDM reader as 32-bit if the ATM XFS Manager/provider is 32-bit.")
    if not result.logical_service_candidates:
        steps.append("Find the CDM logical service name from the ATM XFS configuration before enabling xfs_cdm.")
    else:
        steps.append("Use one listed logical service candidate for the first read-only WFSGetInfo test.")
    steps.append("Keep cash monitoring disabled until read-only XFS CDM diagnostics are confirmed.")
    return steps


def diagnose_xfs_cdm(xfs_root: str | None = None) -> XfsCdmDiagnostics:
    root = resolve_xfs_root(xfs_root)
    xfs_manager_dir = root / "XFS Manager" if root is not None else None
    cdm_provider_dir = root / "XFS CDM Service Provider" if root is not None else None
    registry_hits = scan_registry_for_cdm()
    result = XfsCdmDiagnostics(
        read_only=True,
        os_name=platform.platform(),
        os_architecture=platform.machine() or platform.architecture()[0],
        process_architecture=process_architecture(),
        xfs_root=str(root) if root is not None else None,
        aptra_root=str(root) if root is not None else None,
        xfs_manager_dir=str(xfs_manager_dir) if xfs_manager_dir is not None else None,
        cdm_provider_dir=str(cdm_provider_dir) if cdm_provider_dir is not None else None,
        cdm_provider_files=list_directory_files(cdm_provider_dir, ("*.dll", "*.ini", "*.cfg", "*.xml")),
        xfs_manager_files=list_directory_files(xfs_manager_dir, ("*.dll", "*.cab", "*.ini", "*.cfg", "*.xml")),
        msxfs_candidates=[file_entry(path) for path in msxfs_candidate_paths(root)],
        registry_hits=registry_hits,
        logical_service_candidates=logical_service_candidates(registry_hits),
    )
    if root is None or not root.exists():
        result.warnings.append("XFS root was not found automatically. Registry scan may still find logical service names.")
    if cdm_provider_dir is None or not cdm_provider_dir.exists():
        result.warnings.append("XFS CDM Service Provider directory was not found.")
    if xfs_manager_dir is None or not xfs_manager_dir.exists():
        result.warnings.append("XFS Manager directory was not found.")
    if not any(entry.exists and entry.path.lower().endswith(".dll") for entry in result.cdm_provider_files):
        result.warnings.append("No CDM provider DLLs were found.")
    if os.name != "nt":
        result.warnings.append("Registry scan skipped because this is not Windows.")
    result.next_steps = build_next_steps(result)
    return result


def format_diagnostics(result: XfsCdmDiagnostics) -> str:
    lines = [
        "XFS CDM Diagnostic - READ ONLY",
        f"OS: {result.os_name}",
        f"OS Architecture: {result.os_architecture}",
        f"Agent Process Architecture: {result.process_architecture}",
        f"XFS Root: {result.xfs_root or result.aptra_root or '-'}",
        f"XFS Manager Directory: {result.xfs_manager_dir or '-'}",
        f"CDM Provider Directory: {result.cdm_provider_dir or '-'}",
        "",
        "CDM Provider Files:",
    ]
    lines.extend(f"  - {entry.path} ({entry.size_bytes or 0} bytes)" for entry in result.cdm_provider_files if entry.exists)
    if not any(entry.exists for entry in result.cdm_provider_files):
        lines.append("  - none")

    lines.append("")
    lines.append("XFS Manager Files:")
    lines.extend(f"  - {entry.path} ({entry.size_bytes or 0} bytes)" for entry in result.xfs_manager_files if entry.exists)
    if not any(entry.exists for entry in result.xfs_manager_files):
        lines.append("  - none")

    lines.append("")
    lines.append("msxfs.dll Candidates:")
    lines.extend(f"  - {entry.path}: {'found' if entry.exists else 'missing'}" for entry in result.msxfs_candidates)

    lines.append("")
    lines.append("Logical Service Candidates:")
    lines.extend(f"  - {item}" for item in result.logical_service_candidates)
    if not result.logical_service_candidates:
        lines.append("  - none detected from registry")

    if result.registry_hits:
        lines.append("")
        lines.append("Registry CDM Hints:")
        for hit in result.registry_hits[:50]:
            lines.append(f"  - {hit.root}\\{hit.path} | {hit.name} = {hit.value}")
        if len(result.registry_hits) > 50:
            lines.append(f"  - ... {len(result.registry_hits) - 50} more")

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {item}" for item in result.warnings)

    lines.append("")
    lines.append("Next Steps:")
    lines.extend(f"  - {item}" for item in result.next_steps)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only XFS CDM diagnostic")
    parser.add_argument("--xfs-root")
    parser.add_argument("--aptra-root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = diagnose_xfs_cdm(args.xfs_root or args.aptra_root)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_diagnostics(result))


if __name__ == "__main__":
    main()
