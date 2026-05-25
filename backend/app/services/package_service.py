import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import settings
from ..models import UpdatePackage, User
from .checksum_service import sha256_file


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
DISALLOWED_PACKAGE_EXTENSIONS = {
    ".exe",
    ".ps1",
    ".bat",
    ".cmd",
    ".vbs",
    ".js",
    ".jse",
    ".msi",
    ".dll",
    ".scr",
    ".com",
    ".reg",
}
IGNORED_ZIP_FILENAMES = {".ds_store", "thumbs.db", "desktop.ini"}


def _safe_zip_member_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or any(part.endswith(":") for part in path.parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsafe path in ZIP member: {name}",
        )
    return path


def _is_ignored_zip_member(path: PurePosixPath) -> bool:
    parts = [part.lower() for part in path.parts]
    filename = parts[-1] if parts else ""
    return "__macosx" in parts or any(part.startswith("._") for part in parts) or filename in IGNORED_ZIP_FILENAMES


def validate_image_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            image_count = 0
            for member in archive.infolist():
                member_path = _safe_zip_member_name(member.filename)
                if member.is_dir() or _is_ignored_zip_member(member_path):
                    continue
                extension = member_path.suffix.lower()
                if extension in DISALLOWED_PACKAGE_EXTENSIONS:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Executable or script file is not allowed in ZIP: {member.filename}",
                    )
                if extension not in ALLOWED_IMAGE_EXTENSIONS:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unsupported file extension in ZIP: {member.filename}",
                    )
                image_count += 1
            if image_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ZIP package must contain at least one image file",
                )
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ZIP file") from exc


def create_package_from_upload(
    db: Session,
    *,
    upload: UploadFile,
    version: str | None,
    notes: str | None,
    created_by: User,
) -> UpdatePackage:
    if not upload.filename or not upload.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only ZIP packages are accepted")

    package_dir = settings.upload_dir / "packages"
    package_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=package_dir) as tmp:
        temp_path = Path(tmp.name)
        shutil.copyfileobj(upload.file, tmp)

    try:
        validate_image_zip(temp_path)
        digest = sha256_file(temp_path)
        size_bytes = temp_path.stat().st_size

        clean_original = Path(upload.filename).name.replace(" ", "_")
        stored_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{digest[:12]}_{clean_original}"
        storage_path = package_dir / stored_filename
        shutil.move(str(temp_path), storage_path)

        package_version = version or f"media-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{digest[:8]}"
        existing = db.query(UpdatePackage).filter(UpdatePackage.version == package_version).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Package version already exists")

        package = UpdatePackage(
            version=package_version,
            original_filename=upload.filename,
            stored_filename=stored_filename,
            sha256=digest,
            size_bytes=size_bytes,
            storage_path=str(storage_path),
            notes=notes,
            created_by_id=created_by.id,
        )
        db.add(package)
        db.flush()
        return package
    finally:
        if temp_path.exists():
            temp_path.unlink()
