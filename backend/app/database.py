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
            datetime_type = "TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME"
            if "allowed_pages" not in existing_columns:
                if connection.dialect.name == "postgresql":
                    connection.execute(text("ALTER TABLE users ADD COLUMN allowed_pages JSONB NOT NULL DEFAULT '[]'::jsonb"))
                else:
                    connection.execute(text("ALTER TABLE users ADD COLUMN allowed_pages JSON NOT NULL DEFAULT '[]'"))
            user_columns = {
                "active_session_hash": "VARCHAR(128)",
                "active_session_started_at": datetime_type,
            }
            for name, definition in user_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))

            all_pages_json = (
                '["dashboard","atms","upload","packages","agent-updates","cash","notifications","agent-downloads","logs","settings","users"]'
            )
            default_pages_json = '["dashboard"]'
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET allowed_pages = :all_pages
                    WHERE role IN ('admin', 'system_admin')
                        AND (allowed_pages IS NULL OR allowed_pages = '[]' OR allowed_pages NOT LIKE '%"agent-updates"%')
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
                "config_sync_interval_seconds": "INTEGER NOT NULL DEFAULT 120",
                "check_interval_seconds": "INTEGER NOT NULL DEFAULT 300",
                "media_update_enabled": "BOOLEAN NOT NULL DEFAULT 1",
                "cash_monitoring_enabled": "BOOLEAN NOT NULL DEFAULT 0",
                "module_status_json": "JSON NOT NULL DEFAULT '{}'",
                "cash_provider": "VARCHAR(40) NOT NULL DEFAULT 'xfs_cdm'",
                "xfs_profile": "VARCHAR(40) NOT NULL DEFAULT 'ncr_aptra'",
                "xfs_logical_service": "VARCHAR(120) NOT NULL DEFAULT 'MediaDispenser1'",
                "xfs_msxfs_path": "VARCHAR(500)",
                "xfs_version_range": "VARCHAR(20) NOT NULL DEFAULT '0x00031E03'",
                "atm_cash_mode": "VARCHAR(40) NOT NULL DEFAULT 'DISPENSE_ONLY'",
                "cash_layout_json": "JSON NOT NULL DEFAULT '[]'",
                "cash_read_interval_seconds": "INTEGER NOT NULL DEFAULT 120",
                "cash_low_threshold_default": "INTEGER NOT NULL DEFAULT 300",
                "cash_critical_threshold_default": "INTEGER NOT NULL DEFAULT 100",
                "cash_stale_after_minutes": "INTEGER NOT NULL DEFAULT 10",
                "switch_probe_host": "VARCHAR(120) NOT NULL DEFAULT '172.16.25.75'",
                "switch_probe_port": "INTEGER NOT NULL DEFAULT 10200",
                "switch_probe_interval_seconds": "INTEGER NOT NULL DEFAULT 30",
                "journal_reader_enabled": "BOOLEAN NOT NULL DEFAULT 0",
                "journal_log_glob": "VARCHAR(500) NOT NULL DEFAULT 'D:\\Program Files\\DTATMW\\Bin\\ATMAPP\\Log\\EJ*.log'",
                "journal_read_interval_seconds": "INTEGER NOT NULL DEFAULT 60",
                "last_switch_probe_status": "VARCHAR(30)",
                "last_switch_probe_latency_ms": "INTEGER",
                "last_switch_probe_error": "TEXT",
                "last_switch_probe_at": datetime_type,
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
            connection.execute(
                text(
                    """
                    UPDATE atms
                    SET
                        cash_provider = 'xfs_cdm',
                        config_version = config_version + 1,
                        config_updated_at = COALESCE(updated_at, created_at, config_updated_at)
                    WHERE cash_provider = 'mock'
                    """
                )
            )

        if "atm_agent_configs" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("atm_agent_configs")}
            config_columns = {
                "cash_provider": "VARCHAR(40) NOT NULL DEFAULT 'xfs_cdm'",
                "atm_cash_mode": "VARCHAR(40) NOT NULL DEFAULT 'DISPENSE_ONLY'",
                "xfs_profile": "VARCHAR(40) NOT NULL DEFAULT 'ncr_aptra'",
                "xfs_logical_service": "VARCHAR(120) NOT NULL DEFAULT 'MediaDispenser1'",
                "xfs_msxfs_path": "VARCHAR(500)",
                "xfs_version_range": "VARCHAR(20) NOT NULL DEFAULT '0x00031E03'",
                "cash_layout_json": "JSON NOT NULL DEFAULT '[]'",
                "switch_probe_interval_seconds": "INTEGER NOT NULL DEFAULT 30",
            }
            for name, definition in config_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE atm_agent_configs ADD COLUMN {name} {definition}"))
            connection.execute(text("UPDATE atm_agent_configs SET cash_provider = 'xfs_cdm' WHERE cash_provider = 'mock'"))

        if "atm_cash_units" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("atm_cash_units")}
            cash_unit_columns = {
                "cassette_no": "INTEGER NOT NULL DEFAULT 1",
                "expected_currency": "VARCHAR(10) NOT NULL DEFAULT 'YER'",
                "expected_denomination": "INTEGER NOT NULL DEFAULT 1000",
                "reported_currency": "VARCHAR(10) NOT NULL DEFAULT 'YER'",
                "reported_denomination": "INTEGER NOT NULL DEFAULT 1000",
                "retract_count": "INTEGER NOT NULL DEFAULT 0",
                "low_threshold": "INTEGER NOT NULL DEFAULT 300",
                "critical_threshold": "INTEGER NOT NULL DEFAULT 100",
                "layout_match_status": "VARCHAR(40) NOT NULL DEFAULT 'MATCH'",
            }
            for name, definition in cash_unit_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE atm_cash_units ADD COLUMN {name} {definition}"))

            connection.execute(
                text(
                    """
                    UPDATE atm_cash_units
                    SET
                        cassette_no = COALESCE(cassette_no, unit_no),
                        expected_currency = COALESCE(expected_currency, currency),
                        expected_denomination = COALESCE(expected_denomination, denomination),
                        reported_currency = COALESCE(reported_currency, currency),
                        reported_denomination = COALESCE(reported_denomination, denomination),
                        retract_count = COALESCE(retract_count, retracted_count),
                        low_threshold = COALESCE(low_threshold, min_threshold),
                        critical_threshold = COALESCE(critical_threshold, 100)
                    """
                )
            )

        datetime_type = "TIMESTAMP WITH TIME ZONE" if connection.dialect.name == "postgresql" else "DATETIME"

        if "notification_settings" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("notification_settings")}
            default_true = (
                "BOOLEAN NOT NULL DEFAULT TRUE"
                if connection.dialect.name == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 1"
            )
            default_false = (
                "BOOLEAN NOT NULL DEFAULT FALSE"
                if connection.dialect.name == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 0"
            )
            notification_columns = {
                "email_enabled": default_false,
                "whatsapp_enabled": default_false,
                "whatsapp_gateway_url": "VARCHAR(500)",
                "whatsapp_gateway_token": "TEXT",
                "whatsapp_default_recipient": "VARCHAR(40)",
                "whatsapp_default_recipients_json": "JSON NOT NULL DEFAULT '[]'",
                "notify_switch_disconnected": default_true,
                "notify_whatsapp_disconnected": default_true,
                "last_whatsapp_gateway_status": "VARCHAR(40)",
                "last_whatsapp_gateway_error": "TEXT",
                "last_whatsapp_gateway_status_at": datetime_type,
                "last_whatsapp_disconnect_alert_at": datetime_type,
            }
            for name, definition in notification_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE notification_settings ADD COLUMN {name} {definition}"))
            if "email_enabled" not in existing_columns and "enabled" in existing_columns:
                connection.execute(text("UPDATE notification_settings SET email_enabled = enabled"))
            if "whatsapp_default_recipient" in existing_columns and "whatsapp_default_recipients_json" not in existing_columns:
                json_array_expression = (
                    "json_build_array(whatsapp_default_recipient)"
                    if connection.dialect.name == "postgresql"
                    else "json_array(whatsapp_default_recipient)"
                )
                connection.execute(
                    text(
                        f"""
                        UPDATE notification_settings
                        SET whatsapp_default_recipients_json = {json_array_expression}
                        WHERE whatsapp_default_recipient IS NOT NULL AND whatsapp_default_recipient != ''
                        """
                    )
                )
            if "enabled" in existing_columns:
                if connection.dialect.name == "postgresql":
                    connection.execute(
                        text(
                            """
                            UPDATE notification_settings
                            SET enabled = TRUE
                            WHERE COALESCE(email_enabled, FALSE) = TRUE
                                OR COALESCE(whatsapp_enabled, FALSE) = TRUE
                            """
                        )
                    )
                else:
                    connection.execute(
                        text(
                            """
                            UPDATE notification_settings
                            SET enabled = 1
                            WHERE COALESCE(email_enabled, 0) = 1 OR COALESCE(whatsapp_enabled, 0) = 1
                            """
                        )
                    )

        if "notification_recipients" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("notification_recipients")}
            recipient_columns = {
                "whatsapp_number": "VARCHAR(40)",
                "whatsapp_numbers_json": "JSON NOT NULL DEFAULT '[]'",
            }
            for name, definition in recipient_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE notification_recipients ADD COLUMN {name} {definition}"))
            if "whatsapp_number" in existing_columns and "whatsapp_numbers_json" not in existing_columns:
                json_array_expression = (
                    "json_build_array(whatsapp_number)"
                    if connection.dialect.name == "postgresql"
                    else "json_array(whatsapp_number)"
                )
                connection.execute(
                    text(
                        f"""
                        UPDATE notification_recipients
                        SET whatsapp_numbers_json = {json_array_expression}
                        WHERE whatsapp_number IS NOT NULL AND whatsapp_number != ''
                        """
                    )
                )

        if "notification_deliveries" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("notification_deliveries")}
            delivery_columns = {
                "body": "TEXT",
                "html_body": "TEXT",
                "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                "next_retry_at": datetime_type,
            }
            for name, definition in delivery_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE notification_deliveries ADD COLUMN {name} {definition}"))
            if "attempt_count" not in existing_columns:
                connection.execute(
                    text(
                        """
                        UPDATE notification_deliveries
                        SET attempt_count = 1
                        WHERE status IN ('sent', 'failed')
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
