from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import RouteFactorDef


class RouteFactorDefRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_required_enabled_by_logical_table(self, logical_table_id: int) -> list[RouteFactorDef]:
        stmt = select(RouteFactorDef).where(
            RouteFactorDef.logical_table_id == logical_table_id,
            RouteFactorDef.enabled.is_(True),
            RouteFactorDef.required.is_(True),
        )
        return list(self.session.execute(stmt).scalars())

