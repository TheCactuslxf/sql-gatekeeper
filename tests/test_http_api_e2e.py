import os
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from sql_gatekeeper.bootstrap.meta import create_metadata_schema, seed_reference_data
from sql_gatekeeper.config import Settings
from sql_gatekeeper.db.base import Base
from sql_gatekeeper.db.models import PolicySet
from tests_support import build_mysql_settings, ensure_large_order_shard, ensure_order_route


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="Docker MySQL tests are disabled by default",
)

PROJECT_ROOT = Path("/Users/wan/code/python/sql-gatekeeper")
VENV_PYTHON = PROJECT_ROOT / ".venv/bin/python"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _audit_count(settings: Settings) -> int:
    engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    with engine.connect() as connection:
        return int(connection.execute(text("select count(*) from request_audit_log")).scalar_one())


@pytest.fixture(scope="module")
def http_server():
    settings = build_mysql_settings()
    meta_engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    Base.metadata.drop_all(bind=meta_engine)
    Base.metadata.create_all(bind=meta_engine)
    seed_reference_data(settings)
    ensure_large_order_shard()

    with Session(meta_engine) as session:
        ensure_order_route(session, route_value="2025_08", physical_table_name="order_2025_08")

    port = _pick_free_port()
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
            "META_DB_HOST": settings.meta_db_host,
            "META_DB_PORT": str(settings.meta_db_port),
            "META_DB_NAME": settings.meta_db_name,
            "META_DB_USER": settings.meta_db_user,
            "META_DB_PASSWORD": settings.meta_db_password,
            "API_HOST": "127.0.0.1",
            "API_PORT": str(port),
        }
    )

    process = subprocess.Popen(
        [
            str(VENV_PYTHON),
            "-m",
            "uvicorn",
            "sql_gatekeeper.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base_url = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=base_url, timeout=10.0)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                response = client.get("/health")
                if response.status_code == 200:
                    yield settings, client
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()
            raise AssertionError(f"HTTP server did not become ready.\n{output}")
    finally:
        client.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _request_payload(sql: str, route_context: Optional[dict] = None) -> dict:
    return {
        "request_id": f"req-{uuid.uuid4()}",
        "operator": "ai-agent",
        "scene": "http-e2e",
        "sql": sql,
        "route_context": route_context or {},
    }


def test_http_health_endpoint(http_server):
    _, client = http_server

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_http_check_allows_dynamic_user_shard_and_writes_audit(http_server):
    settings, client = http_server
    before = _audit_count(settings)

    response = client.post(
        "/api/v1/sql/check",
        json=_request_payload("select * from user where uid = 10001 limit 10"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["rewritten_sql"] == "select * from user_1 where uid = 10001 limit 10"
    assert body["physical_tables"] == ["user_1"]
    assert _audit_count(settings) == before + 1


def test_http_check_rejects_missing_route_context_and_writes_audit(http_server):
    settings, client = http_server
    before = _audit_count(settings)

    response = client.post(
        "/api/v1/sql/check",
        json=_request_payload("select * from order where order_id = 'A1001' limit 10"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "MISSING_ROUTE_FACTOR"
    assert _audit_count(settings) == before + 1


def test_http_execute_returns_rows_and_writes_audit(http_server):
    settings, client = http_server
    before = _audit_count(settings)

    response = client.post(
        "/api/v1/sql/execute",
        json=_request_payload("select uid, user_name from user where uid = 10001 limit 1"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["reason_code"] == "EXECUTED"
    assert body["row_count"] == 1
    assert body["rows"][0]["uid"] == 10001
    assert _audit_count(settings) == before + 1


def test_http_check_rejects_cross_datasource_join(http_server):
    _, client = http_server

    response = client.post(
        "/api/v1/sql/check",
        json=_request_payload(
            "select * from user u join order o on 1 = 1 where u.uid = 10001 and o.order_id = 'A1002' limit 10",
            {"biz_date": "2025-07"},
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "CROSS_DATASOURCE_JOIN"


def test_http_check_rejects_large_full_scan(http_server):
    settings, client = http_server
    meta_engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    with Session(meta_engine) as session:
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 100000
        policy.max_scan_rows = 5_000_000
        session.commit()

    response = client.post(
        "/api/v1/sql/check",
        json=_request_payload(
            "select * from order where tenant_id = 't1' limit 10",
            {"biz_date": "2025-08"},
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "FULL_SCAN_ON_LARGE_TABLE"
    assert body["rewritten_sql"] == "select * from order_2025_08 where tenant_id = 't1' limit 10"
    assert body["explain_summaries"][0]["access_type"].upper() == "ALL"


def test_http_check_rejects_using_filesort(http_server):
    settings, client = http_server
    meta_engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    with Session(meta_engine) as session:
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 2_000_000
        policy.max_scan_rows = 5_000_000
        session.commit()

    response = client.post(
        "/api/v1/sql/check",
        json=_request_payload(
            "select * from order order by amount limit 10",
            {"biz_date": "2025-08"},
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "USING_FILESORT"
    assert "Using filesort" in body["explain_summaries"][0]["extra"]


def test_http_check_rejects_using_temporary(http_server):
    settings, client = http_server
    meta_engine = create_engine(settings.meta_db_dsn, pool_pre_ping=True)
    with Session(meta_engine) as session:
        policy = session.query(PolicySet).filter_by(policy_code="default_select_guard").one()
        policy.large_table_row_threshold = 2_000_000
        policy.max_scan_rows = 5_000_000
        session.commit()

    response = client.post(
        "/api/v1/sql/check",
        json=_request_payload(
            "select tenant_id, count(*) from order group by tenant_id order by count(*) limit 10",
            {"biz_date": "2025-08"},
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "USING_TEMPORARY"
    assert "Using temporary" in body["explain_summaries"][0]["extra"]
