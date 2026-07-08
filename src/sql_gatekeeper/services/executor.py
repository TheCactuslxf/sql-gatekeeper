from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import DatasourceInstance
from sql_gatekeeper.repositories.datasource import DatasourceInstanceRepository
from sql_gatekeeper.repositories.policy_set import PolicySetRepository
from sql_gatekeeper.services.checker import CheckResult
from sql_gatekeeper.services.datasource_runtime import create_runtime_engine


@dataclass(frozen=True)
class ExecuteResult:
    allowed: bool
    reason_code: str
    message: str
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: int


class SqlExecutionService:
    def __init__(self, session: Session):
        self.session = session
        self.datasource_repo = DatasourceInstanceRepository(session)
        self.policy_repo = PolicySetRepository(session)

    def execute(self, check_result: CheckResult) -> ExecuteResult:
        if not check_result.allowed:
            return ExecuteResult(False, check_result.reason_code, check_result.message, [], 0, 0)

        unique_datasources = sorted(set(check_result.datasource_codes))
        if len(unique_datasources) != 1:
            return ExecuteResult(
                False,
                "CROSS_DATASOURCE_UNSUPPORTED",
                "Execution currently supports exactly one datasource per request",
                [],
                0,
                0,
            )

        datasource = self.datasource_repo.get_enabled_by_code(unique_datasources[0])
        if datasource is None:
            return ExecuteResult(False, "DATASOURCE_NOT_FOUND", "Execution datasource was not found", [], 0, 0)

        policy = self.policy_repo.get_enabled_by_code("default_select_guard")
        if policy is None:
            return ExecuteResult(False, "POLICY_NOT_FOUND", "Execution policy was not found", [], 0, 0)

        started_at = time.perf_counter()
        rows = self._fetch_rows(datasource, check_result.rewritten_sql, policy.max_limit)
        execution_ms = int((time.perf_counter() - started_at) * 1000)

        if len(rows) > policy.max_limit:
            return ExecuteResult(
                False,
                "RESULT_ROWS_EXCEEDED",
                f"Execution returned {len(rows)} rows, exceeding max {policy.max_limit}",
                [],
                0,
                execution_ms,
            )

        return ExecuteResult(
            True,
            "EXECUTED",
            "SQL executed successfully",
            rows,
            len(rows),
            execution_ms,
        )

    @staticmethod
    def _fetch_rows(datasource: DatasourceInstance, rewritten_sql: str, max_limit: int) -> list[dict[str, Any]]:
        engine = create_runtime_engine(datasource)
        guarded_sql = f"/*+ MAX_EXECUTION_TIME(5000) */ {rewritten_sql}"
        with engine.connect() as connection:
            result = connection.execute(text(guarded_sql))
            rows = result.mappings().fetchmany(max_limit + 1)
        return [dict(row) for row in rows]
