import os
from pathlib import Path


class Settings:
    app_name: str = "ATM Media Update Manager"
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

