from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import RequestAuditLog
from sql_gatekeeper.repositories.audit_log import RequestAuditLogRepository
from sql_gatekeeper.services.checker import CheckResult
from sql_gatekeeper.services.executor import ExecuteResult
from sql_gatekeeper.services.redis_gatekeeper import RedisDecision, RedisExecuteResult


@dataclass(frozen=True)
class AuditRequest:
    request_id: str
    operator: str
    scene: str
    sql: str
    route_context: dict[str, Any] = field(default_factory=dict)


class AuditLogService:
    def __init__(self, session: Session):
        self.repo = RequestAuditLogRepository(session)

    def log_check(self, request: AuditRequest, check_result: CheckResult) -> None:
        self.repo.add(
            RequestAuditLog(
                request_id=request.request_id,
                operator=request.operator,
                scene=request.scene,
                original_sql=request.sql,
                rewritten_sql=check_result.rewritten_sql,
                logical_tables=check_result.logical_tables,
                physical_tables=check_result.physical_tables,
                datasource_codes=check_result.datasource_codes,
                decision="ALLOW" if check_result.allowed else "REJECT",
                reason_code=check_result.reason_code,
                reason_detail=check_result.message,
                execution_ms=0,
                explain_summary={"plans": check_result.explain_summaries},
            )
        )

    def log_execute(self, request: AuditRequest, check_result: CheckResult, execute_result: ExecuteResult) -> None:
        self.repo.add(
            RequestAuditLog(
                request_id=request.request_id,
                operator=request.operator,
                scene=request.scene,
                original_sql=request.sql,
                rewritten_sql=check_result.rewritten_sql,
                logical_tables=check_result.logical_tables,
                physical_tables=check_result.physical_tables,
                datasource_codes=check_result.datasource_codes,
                decision="EXECUTED" if execute_result.allowed else "REJECT",
                reason_code=execute_result.reason_code,
                reason_detail=execute_result.message,
                execution_ms=execute_result.execution_ms,
                explain_summary={"plans": check_result.explain_summaries},
            )
        )

    def log_redis_check(self, request: AuditRequest, decision: RedisDecision) -> None:
        self.repo.add(
            RequestAuditLog(
                request_id=request.request_id,
                operator=request.operator,
                scene=request.scene,
                original_sql=request.sql,
                rewritten_sql="",
                logical_tables=[],
                physical_tables=[],
                datasource_codes=[decision.datasource_code],
                decision="ALLOW" if decision.allowed else "REJECT",
                reason_code=decision.reason_code,
                reason_detail=decision.message,
                execution_ms=0,
                explain_summary={"redis_diagnostics": decision.diagnostics},
            )
        )

    def log_redis_execute(
        self,
        request: AuditRequest,
        decision: RedisDecision,
        execute_result: RedisExecuteResult,
    ) -> None:
        self.repo.add(
            RequestAuditLog(
                request_id=request.request_id,
                operator=request.operator,
                scene=request.scene,
                original_sql=request.sql,
                rewritten_sql="",
                logical_tables=[],
                physical_tables=[],
                datasource_codes=[decision.datasource_code],
                decision="EXECUTED" if execute_result.allowed else "REJECT",
                reason_code=execute_result.reason_code,
                reason_detail=execute_result.message,
                execution_ms=execute_result.execution_ms,
                explain_summary={"redis_diagnostics": decision.diagnostics},
            )
        )
