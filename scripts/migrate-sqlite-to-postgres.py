from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select, text


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base  # noqa: E402
from app import models  # noqa: F401,E402


def default_sqlite_url() -> str:
    return f"sqlite:///{(BACKEND_DIR / 'atm_media.db').as_posix()}"


def table_has_rows(connection, table) -> bool:
    return bool(connection.execute(select(func.count()).select_from(table)).scalar_one())


def reset_postgres_sequence(connection, table) -> None:
    primary_keys = list(table.primary_key.columns)
    if len(primary_keys) != 1:
        return
    column = primary_keys[0]
    if not str(column.type).upper().startswith("INTEGER"):
        return
    sequence_name = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": table.name, "column_name": column.name},
    ).scalar_one_or_none()
    if not sequence_name:
        return
    max_id = connection.execute(select(func.max(column))).scalar_one()
    if max_id is None:
        connection.execute(
            text("SELECT setval(pg_get_serial_sequence(:table_name, :column_name)::regclass, 1, false)"),
            {"table_name": table.name, "column_name": column.name},
        )
        return
    connection.execute(
        text("SELECT setval(pg_get_serial_sequence(:table_name, :column_name)::regclass, :max_id, true)"),
        {"table_name": table.name, "column_name": column.name, "max_id": max_id},
    )


def copy_table(source_connection, target_connection, table, batch_size: int) -> int:
    rows_copied = 0
    batch: list[dict] = []
    query = select(table)
    primary_keys = list(table.primary_key.columns)
    if primary_keys:
        query = query.order_by(*primary_keys)

    for row in source_connection.execute(query).mappings():
        batch.append(dict(row))
        if len(batch) >= batch_size:
            target_connection.execute(insert(table), batch)
            rows_copied += len(batch)
            batch.clear()

    if batch:
        target_connection.execute(insert(table), batch)
        rows_copied += len(batch)

    return rows_copied


def migrate(sqlite_url: str, postgres_url: str, batch_size: int, force: bool) -> None:
    source_engine = create_engine(sqlite_url)
    target_engine = create_engine(postgres_url)
    tables = list(Base.metadata.sorted_tables)

    Base.metadata.create_all(bind=target_engine)

    with source_engine.connect() as source_connection:
        with target_engine.begin() as target_connection:
            populated_tables = [table.name for table in tables if table_has_rows(target_connection, table)]
            if populated_tables and not force:
                joined = ", ".join(populated_tables)
                raise RuntimeError(
                    "Target PostgreSQL database is not empty. "
                    f"Refusing to copy into populated tables: {joined}. "
                    "Use --force only after taking a backup and confirming this is intentional."
                )

            if populated_tables and force:
                for table in reversed(tables):
                    target_connection.execute(table.delete())

            for table in tables:
                count = copy_table(source_connection, target_connection, table, batch_size)
                print(f"{table.name}: copied {count} rows")

            if target_engine.dialect.name == "postgresql":
                for table in tables:
                    reset_postgres_sequence(target_connection, table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy QIB ATM Manager data from SQLite to PostgreSQL.")
    parser.add_argument("--sqlite-url", default=default_sqlite_url(), help="Source SQLite SQLAlchemy URL.")
    parser.add_argument("--postgres-url", required=True, help="Target PostgreSQL SQLAlchemy URL.")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--force", action="store_true", help="Delete target table rows before copying.")
    args = parser.parse_args()

    migrate(args.sqlite_url, args.postgres_url, args.batch_size, args.force)


if __name__ == "__main__":
    main()
