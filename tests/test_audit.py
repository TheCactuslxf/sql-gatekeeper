from sql_gatekeeper.repositories.audit_log import RequestAuditLogRepository
from sql_gatekeeper.services.audit import AuditLogService, AuditRequest
from sql_gatekeeper.services.checker import CheckResult
from sql_gatekeeper.services.executor import ExecuteResult


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
