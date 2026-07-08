import os

import pytest
from sqlalchemy import create_engine, inspect, text

from sql_gatekeeper.bootstrap.meta import create_metadata_schema, seed_reference_data
from sql_gatekeeper.config import Settings


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="Docker MySQL tests are disabled by default",
)


def test_bootstrap_creates_tables_and_seed_data():
    settings = Settings(
        META_DB_HOST="127.0.0.1",
        META_DB_PORT=33061,
        META_DB_NAME="gatekeeper_meta",
        META_DB_USER="gatekeeper",
        META_DB_PASSWORD="gatekeeper",
    )

    create_metadata_schema(settings)
    seed_reference_data(settings)

    engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert "datasource_instance" in table_names
    assert "logical_table" in table_names
    assert "request_audit_log" in table_names

    with engine.connect() as connection:
        datasource_count = connection.execute(text("select count(*) from datasource_instance")).scalar_one()
        logical_table_count = connection.execute(text("select count(*) from logical_table")).scalar_one()

    assert datasource_count >= 2
    assert logical_table_count >= 2
