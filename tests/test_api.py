import pytest
from fastapi.testclient import TestClient

from sql_gatekeeper.api import routes
from sql_gatekeeper.api.app import create_app
from sql_gatekeeper.db.models import DatasourceInstance
from sql_gatekeeper.services.explain import ExplainPlanSummary, ExplainRiskDecision, ExplainRiskEvaluator
from sql_gatekeeper.services.executor import SqlExecutionService, ExecuteResult
from sql_gatekeeper.services.redis_gatekeeper import RedisExecuteResult, RedisGatekeeperService
from tests_support import seed_extended_route_metadata


@pytest.fixture()
def client(meta_session_factory, monkeypatch):
    with meta_session_factory() as session:
        seed_extended_route_metadata(session)
        session.add(
            DatasourceInstance(
                datasource_code="demo_redis",
                display_name="Demo Redis",
                db_type="redis",
                host="127.0.0.1",
                port=6379,
                database_name="0",
                username="",
                password_secret_ref="",
                read_only=True,
                enabled=True,
                extra={
                    "catlog_name": "demo",
                    "allowed_key_prefixes": ["demo:"],
                },
            )
        )
        session.commit()
    monkeypatch.setattr(routes, "session_factory", meta_session_factory)
    return TestClient(create_app())


def _mock_explain_allow(monkeypatch):
    def fake_evaluate(self, datasource, rewritten_sql, physical_table_name, policy):
        return ExplainRiskDecision(
            allowed=True,
            reason_code="ALLOW",
            message="mock explain allow",
            summary=ExplainPlanSummary(
                access_type="ref",
                key="PRIMARY",
                rows_examined=1,
                extra="",
                table_name=physical_table_name,
                estimated_table_rows=2,
            ),
        )

    monkeypatch.setattr(ExplainRiskEvaluator, "evaluate", fake_evaluate)


def _mock_execute_allow(monkeypatch):
    def fake_execute(self, check_result):
        return ExecuteResult(
            allowed=True,
            reason_code="EXECUTED",
            message="SQL executed successfully",
            rows=[{"uid": 10001, "user_name": "bob"}],
            row_count=1,
            execution_ms=8,
        )

    monkeypatch.setattr(SqlExecutionService, "execute", fake_execute)


def _mock_redis_execute_allow(monkeypatch):
    def fake_execute(self, decision):
        return RedisExecuteResult(
            allowed=True,
            reason_code="EXECUTED",
            message="Redis command executed successfully",
            rows=[{"key": "demo:user:10001", "value": "bob"}],
            row_count=1,
            execution_ms=3,
        )

    monkeypatch.setattr(RedisGatekeeperService, "execute", fake_execute)


def test_health_endpoint(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_check_redis_endpoint_allows_safe_get(client):
    response = client.post(
        "/api/v1/redis/check",
        json={
            "request_id": "redis-001",
            "operator": "ai-agent",
            "scene": "cache",
            "command": "GET",
            "args": ["demo:user:10001"],
            "redis_context": {"catlog_name": "demo"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["reason_code"] == "ALLOW"
    assert body["command"] == "GET"
    assert body["datasource_code"] == "demo_redis"


def test_check_redis_endpoint_rejects_write_command(client):
    response = client.post(
        "/api/v1/redis/check",
        json={
            "request_id": "redis-002",
            "operator": "ai-agent",
            "scene": "cache",
            "command": "SET",
            "args": ["demo:user:10001", "bob"],
            "redis_context": {"catlog_name": "demo"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "REDIS_COMMAND_DENIED"


def test_execute_redis_endpoint_returns_rows(monkeypatch, client):
    _mock_redis_execute_allow(monkeypatch)
    response = client.post(
        "/api/v1/redis/execute",
        json={
            "request_id": "redis-003",
            "operator": "ai-agent",
            "scene": "cache",
            "command": "GET",
            "args": ["demo:user:10001"],
            "redis_context": {"catlog_name": "demo"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["reason_code"] == "EXECUTED"
    assert body["rows"] == [{"key": "demo:user:10001", "value": "bob"}]


def test_check_sql_endpoint_allows_simple_select(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-001",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from user where uid = 10001 limit 10",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["reason_code"] == "ALLOW"
    assert body["rewritten_sql"] == "select * from user_1 where uid = 10001 limit 10"
    assert body["logical_tables"] == ["user"]
    assert body["physical_tables"] == ["user_1"]
    assert body["datasource_codes"] == ["biz_user_db"]
    assert body["route_diagnostics"][0]["evaluated_route_value"] == "1"
    assert len(body["explain_summaries"]) == 1


def test_check_sql_endpoint_rejects_multi_statement(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-002",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select 1; select 2",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "MULTI_STATEMENT"


def test_check_sql_endpoint_rejects_missing_route_context(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-003",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from order where order_id = 'A1001'",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "MISSING_ROUTE_FACTOR"
    assert body["logical_tables"] == ["order"]
    assert body["route_diagnostics"] == [
        {
            "original_table_name": "order",
            "logical_table_name": "order",
            "route_source": "route_context_or_sql",
            "required_factors": [
                {
                    "factor_name": "biz_date",
                    "source_type": "route_context",
                    "source_key": "biz_date",
                    "required": True,
                    "provided_value": None,
                    "extractor_config": {},
                }
            ],
            "missing_factors": ["biz_date"],
            "extracted_values": {},
            "route_rule": {
                "rule_name": "order_month",
                "rule_type": "format",
                "expression": "biz_date.replace('-', '_')",
                "output_format": "{value}",
            },
            "evaluated_route_value": None,
            "available_route_values_sample": ["2025_06", "2025_07"],
            "available_route_count": 2,
        }
    ]


def test_check_sql_endpoint_resolves_time_shard(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-003a",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from order where order_id = 'A1002' limit 10",
            "route_context": {"biz_date": "2025-07"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["rewritten_sql"] == "select * from order_2025_07 where order_id = 'A1002' limit 10"
    assert body["physical_tables"] == ["order_2025_07"]
    assert body["datasource_codes"] == ["biz_order_db"]


def test_check_sql_endpoint_resolves_dynamic_shard(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-003b",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from user where uid = 10000 limit 10",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["rewritten_sql"] == "select * from user_0 where uid = 10000 limit 10"
    assert body["physical_tables"] == ["user_0"]


def test_check_sql_endpoint_resolves_combined_route(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-003c",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from invoice where uid = 10001 limit 10",
            "route_context": {"biz_date": "2025-07"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["rewritten_sql"] == "select * from invoice_2025_07_1 where uid = 10001 limit 10"
    assert body["physical_tables"] == ["invoice_2025_07_1"]


def test_check_sql_endpoint_rejects_invalid_physical_table(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-003d",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from user_99 where uid = 10099 limit 10",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "INVALID_PHYSICAL_TABLE"


def test_check_sql_endpoint_rejects_cross_datasource_join(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/check",
        json={
            "request_id": "req-003e",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from user u join order o on 1 = 1 where u.uid = 10001 and o.order_id = 'A1002' limit 10",
            "route_context": {"biz_date": "2025-07"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "CROSS_DATASOURCE_JOIN"


def test_execute_sql_endpoint_returns_rows(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    _mock_execute_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/execute",
        json={
            "request_id": "req-004",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from user where uid = 10001 limit 10",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["reason_code"] == "EXECUTED"
    assert body["row_count"] == 1
    assert body["execution_ms"] == 8
    assert body["rows"] == [{"uid": 10001, "user_name": "bob"}]


def test_execute_sql_endpoint_returns_rows_for_time_shard(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    _mock_execute_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/execute",
        json={
            "request_id": "req-004a",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from order where order_id = 'A1002' limit 1",
            "route_context": {"biz_date": "2025-07"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["rewritten_sql"] == "select * from order_2025_07 where order_id = 'A1002' limit 1"
    assert body["physical_tables"] == ["order_2025_07"]


def test_execute_sql_endpoint_rejects_when_limit_exceeded(monkeypatch, client):
    _mock_explain_allow(monkeypatch)
    response = client.post(
        "/api/v1/sql/execute",
        json={
            "request_id": "req-005",
            "operator": "ai-agent",
            "scene": "report",
            "sql": "select * from user where uid = 10001 limit 1001",
            "route_context": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "LIMIT_EXCEEDED"
