from fastapi import APIRouter

from sql_gatekeeper.api.schemas import HealthResponse, SqlDecisionResponse, SqlRequest
from sql_gatekeeper.config import get_settings
from sql_gatekeeper.db.session import create_session_factory
from sql_gatekeeper.services.audit import AuditLogService, AuditRequest
from sql_gatekeeper.services.checker import SqlCheckService
from sql_gatekeeper.services.executor import SqlExecutionService

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
        physical_tables=decision.physical_tables,
        datasource_codes=decision.datasource_codes,
        explain_summaries=decision.explain_summaries,
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
                physical_tables=decision.physical_tables,
                datasource_codes=decision.datasource_codes,
                explain_summaries=decision.explain_summaries,
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
        physical_tables=decision.physical_tables,
        datasource_codes=decision.datasource_codes,
        explain_summaries=decision.explain_summaries,
        execution_ms=0,
        row_count=0,
        rows=[],
    )
