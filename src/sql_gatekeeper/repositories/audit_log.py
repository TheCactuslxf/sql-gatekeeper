from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import RequestAuditLog


class RequestAuditLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, audit_log: RequestAuditLog) -> None:
        self.session.add(audit_log)

    def list_by_request_id(self, request_id: str) -> list[RequestAuditLog]:
        stmt = select(RequestAuditLog).where(RequestAuditLog.request_id == request_id)
        return list(self.session.execute(stmt).scalars())

