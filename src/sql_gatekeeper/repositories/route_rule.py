from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import RouteRule


class RouteRuleRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_enabled_by_logical_table(self, logical_table_id: int) -> RouteRule | None:
        stmt = select(RouteRule).where(
            RouteRule.logical_table_id == logical_table_id,
            RouteRule.enabled.is_(True),
        )
        return self.session.execute(stmt).scalar_one_or_none()
