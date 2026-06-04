import os
from pathlib import Path


def load_env_file() -> None:
    """Load simple KEY=VALUE pairs without requiring an extra dependency."""
    project_root = Path(__file__).resolve().parents[2]
    for env_path in (project_root / ".env", project_root / "backend" / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


load_env_file()


class Settings:
    app_name: str = "QIB ATM Manager"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./atm_media.db")
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-this-local-secret")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123!")
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]


settings = Settings()
