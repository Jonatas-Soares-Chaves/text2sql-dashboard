from contextlib import contextmanager
from functools import lru_cache
from typing import Generator

import sqlparse
from loguru import logger
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings
from db.models import Base


def _build_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )


@lru_cache(maxsize=1)
def get_engine():
    return _build_engine()


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
    logger.info("Banco inicializado")


def check_connection() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error(f"Falha na conexão: {exc}")
        return False


@lru_cache(maxsize=1)
def get_schema_description() -> str:
    meta = MetaData()
    meta.reflect(bind=get_engine())

    lines: list[str] = ["=== DATABASE SCHEMA ===\n"]

    for table_name, table in meta.tables.items():
        lines.append(f"TABLE {table_name}")

        pk_names = {col.name for col in table.primary_key.columns}

        fk_map: dict[str, str] = {}
        for fk in table.foreign_keys:
            fk_map[fk.parent.name] = str(fk.target_fullname)

        for col in table.columns:
            pk_flag = " (PK)" if col.name in pk_names else ""
            fk_flag = f" (FK → {fk_map[col.name]})" if col.name in fk_map else ""
            lines.append(
                f"  - {col.name:<22}: {str(col.type):<15}{pk_flag}{fk_flag}"
            )

        lines.append("")

    lines.append("=== DOMAIN VALUES ===")
    lines.append("orders.status    : pending | confirmed | shipped | delivered | cancelled")
    lines.append("orders.channel   : web | app | marketplace")
    lines.append("customers.segment: B2B | B2C | VIP")
    lines.append("customers.state  : UF brasileira (SP, RJ, MG, RS, BA...)")

    return "\n".join(lines)


def get_table_sample(table_name: str, limit: int = 3) -> list[dict]:
    with get_engine().connect() as conn:
        result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
        return [dict(row._mapping) for row in result]