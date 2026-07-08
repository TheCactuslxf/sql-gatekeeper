from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sql_gatekeeper.config import Settings, get_settings


def create_engine_from_settings(settings: Settings | None = None):
    app_settings = settings or get_settings()
    return create_engine(app_settings.meta_db_dsn, pool_pre_ping=True)


def create_session_factory(settings: Settings | None = None):
    engine = create_engine_from_settings(settings)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
