from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from ..auth import get_current_user
from ..models import User

router = APIRouter(prefix="/api/agent-downloads", tags=["agent-downloads"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENT_SOURCE_ZIP = PROJECT_ROOT / "ATM-Agent-Build-Source.zip"
AGENT_EXE = PROJECT_ROOT / "agent" / "dist" / "atm-agent.exe"


@router.get("/source")
def download_agent_source(current_user: User = Depends(get_current_user)) -> FileResponse:
    if not AGENT_SOURCE_ZIP.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent source package is not available")
    return FileResponse(
        AGENT_SOURCE_ZIP,
        media_type="application/zip",
        filename="ATM-Agent-Build-Source.zip",
    )


@router.get("/exe")
def download_agent_exe(current_user: User = Depends(get_current_user)) -> FileResponse:
    if not AGENT_EXE.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="atm-agent.exe is not available. Build it on Windows and place it at agent/dist/atm-agent.exe",
        )
    return FileResponse(
        AGENT_EXE,
        media_type="application/vnd.microsoft.portable-executable",
        filename="atm-agent.exe",
    )
