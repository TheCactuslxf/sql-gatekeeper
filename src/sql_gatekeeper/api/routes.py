from fastapi import APIRouter

from sql_gatekeeper.api.schemas import HealthResponse, RedisDecisionResponse, RedisRequest, SqlDecisionResponse, SqlRequest
from sql_gatekeeper.config import get_settings
from sql_gatekeeper.db.session import create_session_factory
from sql_gatekeeper.services.audit import AuditLogService, AuditRequest
from sql_gatekeeper.services.checker import SqlCheckService
from sql_gatekeeper.services.executor import SqlExecutionService
from sql_gatekeeper.services.redis_gatekeeper import RedisGatekeeperService

router = APIRouter()
session_factory = create_session_factory()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(app_name=settings.app_name, status="ok")


@router.post("/api/v1/sql/check", response_model=SqlDecisionResponse)
def check_sql(request: SqlRequest) -> SqlDecisionResponse:
    with session_factory() as session:
        decision = SqlCheckService(session).check(request.sql, request.route_context)
        AuditLogService(session).log_check(
            AuditRequest(
                request_id=request.request_id,
                operator=request.operator,
                scene=request.scene,
                sql=request.sql,
                route_context=request.route_context,
            ),
            decision,
        )
        session.commit()
    return SqlDecisionResponse(
        request_id=request.request_id,
        allowed=decision.allowed,
        reason_code=decision.reason_code,
        message=decision.message,
        rewritten_sql=decision.rewritten_sql,
        logical_tables=decision.logical_tables,
        physical_tables=decision.physical_tables,
        datasource_codes=decision.datasource_codes,
        explain_summaries=decision.explain_summaries,
        route_diagnostics=decision.route_diagnostics,
        execution_ms=0,
        row_count=0,
        rows=[],
    )


@router.post("/api/v1/sql/execute", response_model=SqlDecisionResponse)
def execute_sql(request: SqlRequest) -> SqlDecisionResponse:
    with session_factory() as session:
        decision = SqlCheckService(session).check(request.sql, request.route_context)
        audit_service = AuditLogService(session)
        if decision.allowed:
            execute_result = SqlExecutionService(session).execute(decision)
            audit_service.log_execute(
                AuditRequest(
                    request_id=request.request_id,
                    operator=request.operator,
                    scene=request.scene,
                    sql=request.sql,
                    route_context=request.route_context,
                ),
                decision,
                execute_result,
            )
            session.commit()
            return SqlDecisionResponse(
                request_id=request.request_id,
                allowed=execute_result.allowed,
                reason_code=execute_result.reason_code,
                message=execute_result.message,
                rewritten_sql=decision.rewritten_sql,
                logical_tables=decision.logical_tables,
                physical_tables=decision.physical_tables,
                datasource_codes=decision.datasource_codes,
                explain_summaries=decision.explain_summaries,
                route_diagnostics=decision.route_diagnostics,
                execution_ms=execute_result.execution_ms,
                row_count=execute_result.row_count,
                rows=execute_result.rows,
            )
        audit_service.log_check(
            AuditRequest(
                request_id=request.request_id,
                operator=request.operator,
                scene=request.scene,
                sql=request.sql,
                route_context=request.route_context,
            ),
            decision,
        )
        session.commit()
    return SqlDecisionResponse(
        request_id=request.request_id,
        allowed=decision.allowed,
        reason_code=decision.reason_code,
        message=decision.message,
        rewritten_sql=decision.rewritten_sql,
        logical_tables=decision.logical_tables,
        physical_tables=decision.physical_tables,
        datasource_codes=decision.datasource_codes,
        explain_summaries=decision.explain_summaries,
        route_diagnostics=decision.route_diagnostics,
        execution_ms=0,
        row_count=0,
        rows=[],
    )


@router.post("/api/v1/redis/check", response_model=RedisDecisionResponse)
def check_redis(request: RedisRequest) -> RedisDecisionResponse:
    with session_factory() as session:
        decision = RedisGatekeeperService(session=session).check(request.command, request.args, request.redis_context)
        AuditLogService(session).log_redis_check(_redis_audit_request(request), decision)
        session.commit()
    return RedisDecisionResponse(
        request_id=request.request_id,
        allowed=decision.allowed,
        reason_code=decision.reason_code,
        message=decision.message,
        command=decision.command,
        args=decision.args,
        datasource_code=decision.datasource_code,
        diagnostics=decision.diagnostics,
        execution_ms=0,
        row_count=0,
        rows=[],
    )


@router.post("/api/v1/redis/execute", response_model=RedisDecisionResponse)
def execute_redis(request: RedisRequest) -> RedisDecisionResponse:
    audit_request = _redis_audit_request(request)
    with session_factory() as session:
        service = RedisGatekeeperService(session=session)
        decision = service.check(request.command, request.args, request.redis_context)
        audit_service = AuditLogService(session)
        if decision.allowed:
            execute_result = service.execute(decision)
            audit_service.log_redis_execute(audit_request, decision, execute_result)
            session.commit()
            return RedisDecisionResponse(
                request_id=request.request_id,
                allowed=execute_result.allowed,
                reason_code=execute_result.reason_code,
                message=execute_result.message,
                command=decision.command,
                args=decision.args,
                datasource_code=decision.datasource_code,
                diagnostics=decision.diagnostics,
                execution_ms=execute_result.execution_ms,
                row_count=execute_result.row_count,
                rows=execute_result.rows,
            )
        audit_service.log_redis_check(audit_request, decision)
        session.commit()
    return RedisDecisionResponse(
        request_id=request.request_id,
        allowed=decision.allowed,
        reason_code=decision.reason_code,
        message=decision.message,
        command=decision.command,
        args=decision.args,
        datasource_code=decision.datasource_code,
        diagnostics=decision.diagnostics,
        execution_ms=0,
        row_count=0,
        rows=[],
    )


def _redis_audit_request(request: RedisRequest) -> AuditRequest:
    return AuditRequest(
        request_id=request.request_id,
        operator=request.operator,
        scene=request.scene,
        sql=f"redis:{request.command} {' '.join(request.args)}",
        route_context=request.redis_context,
    )
