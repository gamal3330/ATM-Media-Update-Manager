from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_existing_schema()


def migrate_existing_schema() -> None:
    """Small MVP migration helper for SQLite/local installs without Alembic yet."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = inspector.get_table_names()
        if "users" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("users")}
            if "allowed_pages" not in existing_columns:
                if connection.dialect.name == "postgresql":
                    connection.execute(text("ALTER TABLE users ADD COLUMN allowed_pages JSONB NOT NULL DEFAULT '[]'::jsonb"))
                else:
                    connection.execute(text("ALTER TABLE users ADD COLUMN allowed_pages JSON NOT NULL DEFAULT '[]'"))

            all_pages_json = (
                '["dashboard","atms","upload","packages","agent-downloads","logs","settings","users"]'
            )
            default_pages_json = '["dashboard"]'
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET allowed_pages = :all_pages
                    WHERE role = 'admin' AND (allowed_pages IS NULL OR allowed_pages = '[]')
                    """
                ),
                {"all_pages": all_pages_json},
            )
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET allowed_pages = :default_pages
                    WHERE role != 'admin' AND (allowed_pages IS NULL OR allowed_pages = '[]')
                    """
                ),
                {"default_pages": default_pages_json},
            )

        if "atms" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("atms")}
            datetime_type = "TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME"
            atm_columns = {
                "last_heartbeat_at": datetime_type,
                "current_package_version": "VARCHAR(120)",
                "agent_version": "VARCHAR(80)",
                "latency_ms": "INTEGER",
                "media_path": "VARCHAR(500) NOT NULL DEFAULT 'C:\\ATM\\Media'",
                "backup_path": "VARCHAR(500) NOT NULL DEFAULT 'C:\\ATM\\Media_Backup'",
                "temp_path": "VARCHAR(500) NOT NULL DEFAULT 'C:\\ATM\\Temp'",
                "config_version": "INTEGER NOT NULL DEFAULT 1",
                "config_updated_at": datetime_type,
                "applied_config_version": "INTEGER NOT NULL DEFAULT 0",
                "last_config_sync_at": datetime_type,
                "last_config_error": "TEXT",
                "heartbeat_interval_seconds": "INTEGER NOT NULL DEFAULT 60",
                "check_interval_seconds": "INTEGER NOT NULL DEFAULT 300",
            }

            for name, definition in atm_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE atms ADD COLUMN {name} {definition}"))

            connection.execute(
                text(
                    """
                    UPDATE atms
                    SET
                        last_heartbeat_at = COALESCE(last_heartbeat_at, last_seen),
                        current_package_version = COALESCE(current_package_version, last_image_version),
                        config_updated_at = COALESCE(config_updated_at, updated_at, created_at)
                    """
                )
            )

        if "update_targets" not in table_names:
            return

        existing_columns = {column["name"] for column in inspector.get_columns("update_targets")}
        datetime_type = "TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME"
        columns = {
            "progress_percent": "INTEGER NOT NULL DEFAULT 0",
            "progress_phase": "VARCHAR(40) NOT NULL DEFAULT 'pending'",
            "progress_message": "TEXT",
            "bytes_downloaded": "INTEGER",
            "total_bytes": "INTEGER",
            "last_progress_at": datetime_type,
        }

        for name, definition in columns.items():
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE update_targets ADD COLUMN {name} {definition}"))
