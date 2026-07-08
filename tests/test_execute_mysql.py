import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sql_gatekeeper.bootstrap.meta import create_metadata_schema, seed_reference_data
from sql_gatekeeper.config import Settings
from sql_gatekeeper.db.models import PolicySet
from sql_gatekeeper.services.checker import SqlCheckService
from sql_gatekeeper.services.executor import SqlExecutionService
from tests_support import ensure_large_order_shard, ensure_order_route


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="Docker MySQL tests are disabled by default",
)


def test_execute_returns_rows_from_docker_mysql():
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
    with Session(meta_engine) as session:
        check_result = SqlCheckService(session).check(
            "select uid, user_name from user where uid = 10001 limit 1",
            {},
        )
        execute_result = SqlExecutionService(session).execute(check_result)

    assert check_result.allowed is True
    assert execute_result.allowed is True
    assert execute_result.row_count == 1
    assert execute_result.rows[0]["uid"] == 10001
    assert execute_result.rows[0]["user_name"] == "bob"


def test_execute_returns_rows_from_time_shard_table_in_docker_mysql():
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
    with Session(meta_engine) as session:
        check_result = SqlCheckService(session).check(
            "select order_id, amount from order where order_id = 'A1002' limit 1",
            {"biz_date": "2025-07"},
        )
        execute_result = SqlExecutionService(session).execute(check_result)

    assert check_result.allowed is True
    assert check_result.rewritten_sql == "select order_id, amount from order_2025_07 where order_id = 'A1002' limit 1"
    assert execute_result.allowed is True
    assert execute_result.row_count == 1
    assert execute_result.rows[0]["order_id"] == "A1002"


def test_check_rejects_full_scan_for_large_time_shard_without_index():
    large_row_count = ensure_large_order_shard()
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
    with Session(meta_engine) as session:
        ensure_order_route(session, route_value="2025_08", physical_table_name="order_2025_08")
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 100000
        policy.max_scan_rows = 5_000_000
        session.commit()

        check_result = SqlCheckService(session).check(
            "select * from order where tenant_id = 't1' limit 10",
            {"biz_date": "2025-08"},
        )

    assert large_row_count == 1_000_000
    assert check_result.allowed is False
    assert check_result.reason_code == "FULL_SCAN_ON_LARGE_TABLE"
    assert check_result.rewritten_sql == "select * from order_2025_08 where tenant_id = 't1' limit 10"
    assert check_result.explain_summaries[0]["access_type"].upper() == "ALL"
    assert check_result.explain_summaries[0]["estimated_table_rows"] >= 100000


def test_check_allows_primary_key_lookup_for_large_time_shard():
    large_row_count = ensure_large_order_shard()
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
    with Session(meta_engine) as session:
        ensure_order_route(session, route_value="2025_08", physical_table_name="order_2025_08")
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 100000
        policy.max_scan_rows = 10
        session.commit()

        check_result = SqlCheckService(session).check(
            "select * from order where order_id = 'B0001001' limit 1",
            {"biz_date": "2025-08"},
        )

    assert large_row_count == 1_000_000
    assert check_result.allowed is True
    assert check_result.reason_code == "ALLOW"
    assert check_result.rewritten_sql == "select * from order_2025_08 where order_id = 'B0001001' limit 1"
    assert check_result.explain_summaries[0]["access_type"].lower() in {"const", "ref"}


def test_check_rejects_using_filesort_for_large_time_shard():
    ensure_large_order_shard()
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
    with Session(meta_engine) as session:
        ensure_order_route(session, route_value="2025_08", physical_table_name="order_2025_08")
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 2_000_000
        policy.max_scan_rows = 5_000_000
        session.commit()

        check_result = SqlCheckService(session).check(
            "select * from order order by amount limit 10",
            {"biz_date": "2025-08"},
        )

    assert check_result.allowed is False
    assert check_result.reason_code == "USING_FILESORT"
    assert "Using filesort" in check_result.explain_summaries[0]["extra"]


def test_check_rejects_using_temporary_for_large_time_shard():
    ensure_large_order_shard()
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
    with Session(meta_engine) as session:
        ensure_order_route(session, route_value="2025_08", physical_table_name="order_2025_08")
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 2_000_000
        policy.max_scan_rows = 5_000_000
        session.commit()

        check_result = SqlCheckService(session).check(
            "select tenant_id, count(*) from order group by tenant_id order by count(*) limit 10",
            {"biz_date": "2025-08"},
        )

    assert check_result.allowed is False
    assert check_result.reason_code == "USING_TEMPORARY"
    assert "Using temporary" in check_result.explain_summaries[0]["extra"]
