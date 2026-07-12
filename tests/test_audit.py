from sql_gatekeeper.repositories.audit_log import RequestAuditLogRepository
from sql_gatekeeper.services.audit import AuditLogService, AuditRequest
from sql_gatekeeper.services.checker import CheckResult
from sql_gatekeeper.services.executor import ExecuteResult
from sql_gatekeeper.services.redis_gatekeeper import RedisDecision, RedisExecuteResult


def test_audit_log_service_writes_check_and_execute_records(meta_session):
    service = AuditLogService(meta_session)
    request = AuditRequest(
        request_id="req-001",
        operator="ai-agent",
        scene="report",
        sql="select * from user where uid = 10001 limit 10",
    )
    check_result = CheckResult(
        allowed=True,
        reason_code="ALLOW",
        message="ok",
        parsed_sql=None,
        rewritten_sql="select * from user_1 where uid = 10001 limit 10",
        logical_tables=["user"],
        physical_tables=["user_1"],
        datasource_codes=["biz_user_db"],
        explain_summaries=[{"access_type": "ref"}],
    )
    execute_result = ExecuteResult(
        allowed=True,
        reason_code="EXECUTED",
        message="done",
        rows=[{"uid": 10001}],
        row_count=1,
        execution_ms=12,
    )

    service.log_check(request, check_result)
    service.log_execute(request, check_result, execute_result)
    meta_session.commit()

    records = RequestAuditLogRepository(meta_session).list_by_request_id("req-001")
    assert len(records) == 2
    assert records[0].decision == "ALLOW"
    assert records[1].decision == "EXECUTED"
    assert records[1].execution_ms == 12


def test_audit_log_service_writes_redis_records(meta_session):
    service = AuditLogService(meta_session)
    request = AuditRequest(
        request_id="redis-001",
        operator="ai-agent",
        scene="cache",
        sql="redis:GET demo:user:10001",
    )
    decision = RedisDecision(
        allowed=True,
        reason_code="ALLOW",
        message="ok",
        command="GET",
        args=["demo:user:10001"],
        datasource_code="demo_redis",
        diagnostics=[{"allowed_commands": ["GET"]}],
    )
    execute_result = RedisExecuteResult(
        allowed=True,
        reason_code="EXECUTED",
        message="done",
        rows=[{"key": "demo:user:10001", "value": "bob"}],
        row_count=1,
        execution_ms=4,
    )

    service.log_redis_check(request, decision)
    service.log_redis_execute(request, decision, execute_result)
    meta_session.commit()

    records = RequestAuditLogRepository(meta_session).list_by_request_id("redis-001")
    assert len(records) == 2
    assert records[0].datasource_codes == ["demo_redis"]
    assert records[1].decision == "EXECUTED"
