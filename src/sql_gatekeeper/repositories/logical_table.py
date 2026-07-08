from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import LogicalTable


class LogicalTableRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_enabled_by_name(self, table_name: str) -> LogicalTable | None:
        stmt = select(LogicalTable).where(
            LogicalTable.table_name == table_name,
            LogicalTable.enabled.is_(True),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_enabled(self) -> list[LogicalTable]:
        stmt = select(LogicalTable).where(LogicalTable.enabled.is_(True))
        return list(self.session.execute(stmt).scalars())
