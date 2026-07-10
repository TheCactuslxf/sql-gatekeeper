from __future__ import annotations

from sqlalchemy import func, select
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

    def list_enabled_route_values_by_logical_table(self, logical_table_id: int, *, limit: int = 20) -> list[str]:
        stmt = (
            select(PhysicalTableRoute.route_value)
            .where(
                PhysicalTableRoute.logical_table_id == logical_table_id,
                PhysicalTableRoute.enabled.is_(True),
            )
            .order_by(PhysicalTableRoute.route_value.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def count_enabled_by_logical_table(self, logical_table_id: int) -> int:
        stmt = select(func.count()).select_from(PhysicalTableRoute).where(
            PhysicalTableRoute.logical_table_id == logical_table_id,
            PhysicalTableRoute.enabled.is_(True),
        )
        return int(self.session.execute(stmt).scalar_one())
