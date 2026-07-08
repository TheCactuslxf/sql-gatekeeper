import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sql_gatekeeper.config import Settings
from sql_gatekeeper.db.base import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests_support import build_mysql_settings


def docker_mysql_is_enabled() -> bool:
    return os.getenv("RUN_DOCKER_TESTS") == "1"


def docker_mysql_skip_reason() -> str:
    return "Docker MySQL tests are disabled by default"
@pytest.fixture()
def mysql_settings() -> Settings:
    if not docker_mysql_is_enabled():
        pytest.skip(docker_mysql_skip_reason())
    return build_mysql_settings()


@pytest.fixture()
def meta_session_factory(mysql_settings: Settings):
    engine = create_engine(mysql_settings.meta_db_dsn, pool_pre_ping=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


@pytest.fixture()
def meta_session(meta_session_factory):
    with meta_session_factory() as session:
        yield session
