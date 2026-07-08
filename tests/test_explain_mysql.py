import os

import pytest
from sqlalchemy import create_engine, text

from sql_gatekeeper.bootstrap.meta import create_metadata_schema, seed_reference_data
from sql_gatekeeper.config import Settings
from sql_gatekeeper.db.models import DatasourceInstance, PolicySet
from sql_gatekeeper.services.explain import ExplainRiskEvaluator


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="Docker MySQL tests are disabled by default",
)


def test_explain_rejects_full_scan_on_large_table():
    settings = Settings(
        META_DB_HOST="127.0.0.1",
        META_DB_PORT=33061,
        META_DB_NAME="gatekeeper_meta",
        META_DB_USER="gatekeeper",
        META_DB_PASSWORD="gatekeeper",
    )
    create_metadata_schema(settings)
    seed_reference_data(settings)

    meta_engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    with meta_engine.begin() as connection:
        connection.execute(
            text(
                """
                update policy_set
                set large_table_row_threshold = 1,
                    max_scan_rows = 1000,
                    reject_full_scan_on_large_table = 1
                where policy_code = 'default_select_guard'
                """
            )
        )
        datasource_row = connection.execute(
            text(
                """
                select datasource_code, display_name, db_type, host, port, database_name, username, password_secret_ref,
                       read_only, enabled, extra, created_at, updated_at, id
                from datasource_instance
                where datasource_code = 'biz_user_db'
                """
            )
        ).mappings().one()
        policy_row = connection.execute(
            text("select * from policy_set where policy_code = 'default_select_guard'")
        ).mappings().one()

    datasource = DatasourceInstance(**dict(datasource_row))
    policy = PolicySet(**dict(policy_row))

    evaluator = ExplainRiskEvaluator()
    decision = evaluator.evaluate(
        datasource=datasource,
        rewritten_sql="select * from user_1 where status = 1 limit 10",
        physical_table_name="user_1",
        policy=policy,
    )

    assert decision.allowed is False
    assert decision.reason_code == "FULL_SCAN_ON_LARGE_TABLE"
    assert decision.summary is not None
    assert decision.summary.access_type.upper() == "ALL"
