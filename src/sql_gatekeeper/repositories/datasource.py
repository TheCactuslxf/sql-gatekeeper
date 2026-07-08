from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import DatasourceInstance


class DatasourceInstanceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_enabled_by_code(self, datasource_code: str) -> DatasourceInstance | None:
        stmt = select(DatasourceInstance).where(
            DatasourceInstance.datasource_code == datasource_code,
            DatasourceInstance.enabled.is_(True),
        )
        return self.session.execute(stmt).scalar_one_or_none()
