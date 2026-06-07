import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AgentPackage, User
from .checksum_service import sha256_file


PE_MACHINE_X86 = 0x014C


def pe_machine_type(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("File is not a Windows executable")
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if pe_offset <= 0 or pe_offset + 6 > len(data):
        raise ValueError("Invalid PE header")
    if data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        raise ValueError("Invalid PE signature")
    return int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little")


def validate_x86_exe(path: Path, label: str) -> None:
    try:
        machine = pe_machine_type(path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} must be a valid Windows EXE") from exc
    if machine != PE_MACHINE_X86:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be 32-bit x86. Detected PE machine 0x{machine:04x}.",
        )


def copy_upload_to_temp(upload: UploadFile, package_dir: Path) -> Path:
    if not upload.filename or not upload.filename.lower().endswith(".exe"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .exe files are accepted")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".exe", dir=package_dir) as tmp:
        temp_path = Path(tmp.name)
        shutil.copyfileobj(upload.file, tmp)
    return temp_path


def safe_original_filename(filename: str) -> str:
    return Path(filename).name.replace(" ", "_")


def stored_filename(prefix: str, original_filename: str, digest: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{timestamp}_{prefix}_{digest[:12]}_{safe_original_filename(original_filename)}"


def create_agent_package_from_upload(
    db: Session,
    *,
    agent_upload: UploadFile,
    updater_upload: UploadFile,
    version: str,
    notes: str | None,
    created_by: User,
) -> AgentPackage:
    package_version = version.strip()
    if not package_version:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent version is required")
    existing = db.query(AgentPackage).filter(AgentPackage.version == package_version).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent package version already exists")

    package_dir = settings.upload_dir / "agent-packages"
    package_dir.mkdir(parents=True, exist_ok=True)

    temp_paths: list[Path] = []
    stored_paths: list[Path] = []
    try:
        agent_temp = copy_upload_to_temp(agent_upload, package_dir)
        updater_temp = copy_upload_to_temp(updater_upload, package_dir)
        temp_paths.extend([agent_temp, updater_temp])

        validate_x86_exe(agent_temp, "atm-agent.exe")
        validate_x86_exe(updater_temp, "agent-updater.exe")

        agent_digest = sha256_file(agent_temp)
        updater_digest = sha256_file(updater_temp)
        agent_size = agent_temp.stat().st_size
        updater_size = updater_temp.stat().st_size

        agent_original = agent_upload.filename or "atm-agent.exe"
        updater_original = updater_upload.filename or "agent-updater.exe"
        agent_stored = stored_filename("atm-agent", agent_original, agent_digest)
        updater_stored = stored_filename("agent-updater", updater_original, updater_digest)
        agent_storage_path = package_dir / agent_stored
        updater_storage_path = package_dir / updater_stored

        shutil.move(str(agent_temp), agent_storage_path)
        shutil.move(str(updater_temp), updater_storage_path)
        stored_paths.extend([agent_storage_path, updater_storage_path])

        package = AgentPackage(
            version=package_version,
            architecture="x86",
            agent_original_filename=agent_original,
            agent_stored_filename=agent_stored,
            agent_sha256=agent_digest,
            agent_size_bytes=agent_size,
            agent_storage_path=str(agent_storage_path),
            updater_original_filename=updater_original,
            updater_stored_filename=updater_stored,
            updater_sha256=updater_digest,
            updater_size_bytes=updater_size,
            updater_storage_path=str(updater_storage_path),
            notes=notes,
            created_by_id=created_by.id,
        )
        db.add(package)
        db.flush()
        return package
    except Exception:
        for path in stored_paths:
            if path.exists():
                path.unlink()
        raise
    finally:
        for path in temp_paths:
            if path.exists():
                path.unlink()
