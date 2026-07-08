from __future__ import annotations

from sqlalchemy import create_engine

from sql_gatekeeper.db.models import DatasourceInstance


def build_runtime_dsn(datasource: DatasourceInstance) -> str:
    password = _resolve_password(datasource.password_secret_ref)
    return (
        f"mysql+pymysql://{datasource.username}:{password}"
        f"@{datasource.host}:{datasource.port}/{datasource.database_name}"
    )


def create_runtime_engine(datasource: DatasourceInstance):
    return create_engine(build_runtime_dsn(datasource), pool_pre_ping=True)


def _resolve_password(secret_ref: str) -> str:
    if secret_ref.startswith("local:"):
        return secret_ref.split(":", 1)[1]
    return secret_ref

