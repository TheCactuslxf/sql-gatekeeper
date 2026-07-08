from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import PolicySet


class PolicySetRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_enabled_by_code(self, policy_code: str) -> PolicySet | None:
        stmt = select(PolicySet).where(
            PolicySet.policy_code == policy_code,
            PolicySet.enabled.is_(True),
        )
        return self.session.execute(stmt).scalar_one_or_none()

