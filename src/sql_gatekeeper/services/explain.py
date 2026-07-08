from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from sql_gatekeeper.db.models import DatasourceInstance, PolicySet
from sql_gatekeeper.services.datasource_runtime import create_runtime_engine


@dataclass(frozen=True)
class ExplainPlanSummary:
    access_type: str
    key: str | None
    rows_examined: int
    extra: str
    table_name: str
    estimated_table_rows: int


@dataclass(frozen=True)
class ExplainRiskDecision:
    allowed: bool
    reason_code: str
    message: str
    summary: ExplainPlanSummary | None


class ExplainRiskEvaluator:
    def evaluate(
        self,
        datasource: DatasourceInstance,
        rewritten_sql: str,
        physical_table_name: str,
        policy: PolicySet,
    ) -> ExplainRiskDecision:
        engine = create_runtime_engine(datasource)
        with engine.connect() as connection:
            row_count = int(
                connection.execute(
                    text(
                        """
                        select coalesce(table_rows, 0)
                        from information_schema.tables
                        where table_schema = :schema_name and table_name = :table_name
                        """
                    ),
                    {"schema_name": datasource.database_name, "table_name": physical_table_name},
                ).scalar_one_or_none()
                or 0
            )
            if row_count <= 0:
                row_count = int(
                    connection.execute(
                        text(f"select count(*) from {physical_table_name}")
                    ).scalar_one()
                )
            explain_row = connection.execute(text(f"EXPLAIN {rewritten_sql}")).mappings().first()

        if explain_row is None:
            return ExplainRiskDecision(False, "EXPLAIN_EMPTY", "EXPLAIN returned no rows", None)

        access_type = str(explain_row.get("type") or "")
        key = explain_row.get("key")
        rows_examined = int(explain_row.get("rows") or 0)
        extra = str(explain_row.get("Extra") or "")
        table_name = str(explain_row.get("table") or physical_table_name)
        summary = ExplainPlanSummary(
            access_type=access_type,
            key=key,
            rows_examined=rows_examined,
            extra=extra,
            table_name=table_name,
            estimated_table_rows=row_count,
        )

        if rows_examined > policy.max_scan_rows:
            return ExplainRiskDecision(
                False,
                "EXPLAIN_SCAN_ROWS_EXCEEDED",
                f"Explain rows {rows_examined} exceeded limit {policy.max_scan_rows}",
                summary,
            )

        if (
            policy.reject_full_scan_on_large_table
            and access_type.upper() == "ALL"
            and row_count >= policy.large_table_row_threshold
        ):
            return ExplainRiskDecision(
                False,
                "FULL_SCAN_ON_LARGE_TABLE",
                f"Full scan detected on table '{physical_table_name}' with estimated rows {row_count}",
                summary,
            )

        if policy.reject_using_temporary and "Using temporary" in extra:
            return ExplainRiskDecision(
                False,
                "USING_TEMPORARY",
                "Explain extra contains Using temporary",
                summary,
            )

        if policy.reject_using_filesort and "Using filesort" in extra:
            return ExplainRiskDecision(
                False,
                "USING_FILESORT",
                "Explain extra contains Using filesort",
                summary,
            )

        return ExplainRiskDecision(True, "ALLOW", "Explain plan passed", summary)
