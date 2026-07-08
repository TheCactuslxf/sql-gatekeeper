from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import PhysicalTableRoute


class PhysicalTableRouteRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_enabled_by_logical_table_and_route_value(
        self,
        logical_table_id: int,
        route_value: str,
    ) -> PhysicalTableRoute | None:
        stmt = select(PhysicalTableRoute).where(
            PhysicalTableRoute.logical_table_id == logical_table_id,
            PhysicalTableRoute.route_value == route_value,
            PhysicalTableRoute.enabled.is_(True),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_enabled_by_physical_table_name(self, physical_table_name: str) -> PhysicalTableRoute | None:
        stmt = select(PhysicalTableRoute).where(
            PhysicalTableRoute.physical_table_name == physical_table_name,
            PhysicalTableRoute.enabled.is_(True),
        )
        return self.session.execute(stmt).scalar_one_or_none()
