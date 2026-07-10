from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from sql_gatekeeper.services.filter_chain import (
    CrossDatasourceFilter,
    ExplainRiskFilter,
    FilterChain,
    FilterContext,
    LimitFilter,
    PhysicalTableValidateFilter,
    PolicyLoadFilter,
    SqlTypeFilter,
)
from sql_gatekeeper.services.precheck import BasicSqlGuard
from sql_gatekeeper.services.routing import RouteDecisionService
from sql_gatekeeper.services.sql_parser import ParsedSql, SqlParser
from sql_gatekeeper.services.sql_rewrite import SqlRewriteEngine


@dataclass(frozen=True)
class CheckResult:
    allowed: bool
    reason_code: str
    message: str
    parsed_sql: ParsedSql | None
    rewritten_sql: str
    logical_tables: list[str]
    physical_tables: list[str]
    datasource_codes: list[str]
    explain_summaries: list[dict]
    route_diagnostics: list[dict]


class SqlCheckService:
    def __init__(self, session: Session):
        self.session = session
        self.sql_guard = BasicSqlGuard()
        self.sql_parser = SqlParser()
        self.route_service = RouteDecisionService(session)
        self.rewrite_engine = SqlRewriteEngine()
        self.filter_chain = FilterChain(
            [
                PolicyLoadFilter(session),
                PhysicalTableValidateFilter(session),
                SqlTypeFilter(),
                CrossDatasourceFilter(),
                LimitFilter(),
                ExplainRiskFilter(),
            ]
        )

    def check(self, sql: str, route_context: dict) -> CheckResult:
        guard_decision = self.sql_guard.evaluate(sql)
        if not guard_decision.allowed:
            return CheckResult(
                allowed=False,
                reason_code=guard_decision.reason_code,
                message=guard_decision.message,
                parsed_sql=None,
                rewritten_sql="",
                logical_tables=[],
                physical_tables=[],
                datasource_codes=[],
                explain_summaries=[],
                route_diagnostics=[],
            )

        parsed_sql = self.sql_parser.parse(sql)
        route_decision = self.route_service.resolve(parsed_sql, route_context)
        if not route_decision.allowed:
            return CheckResult(
                allowed=False,
                reason_code=route_decision.reason_code,
                message=route_decision.message,
                parsed_sql=parsed_sql,
                rewritten_sql="",
                logical_tables=[item.logical_table_name for item in route_decision.diagnostics],
                physical_tables=[],
                datasource_codes=[],
                explain_summaries=[],
                route_diagnostics=[asdict(item) for item in route_decision.diagnostics],
            )

        rewrite_plans = [target.rewrite_plan for target in route_decision.targets if target.rewrite_plan is not None]
        rewritten_sql = self.rewrite_engine.rewrite(parsed_sql, rewrite_plans)
        filter_context = FilterContext(
            sql=sql,
            route_context=route_context,
            parsed_sql=parsed_sql,
            rewritten_sql=rewritten_sql,
            route_decision=route_decision,
        )
        filter_decision = self.filter_chain.run(filter_context)
        if not filter_decision.allowed:
            return CheckResult(
                allowed=False,
                reason_code=filter_decision.reason_code,
                message=filter_decision.message,
                parsed_sql=parsed_sql,
                rewritten_sql=rewritten_sql,
                logical_tables=[target.logical_table_name for target in route_decision.targets],
                physical_tables=[target.physical_table_name for target in route_decision.targets],
                datasource_codes=[target.datasource_code for target in route_decision.targets],
                explain_summaries=[summary.__dict__ for summary in filter_context.explain_summaries],
                route_diagnostics=[asdict(item) for item in route_decision.diagnostics],
            )
        return CheckResult(
            allowed=True,
            reason_code="ALLOW",
            message="SQL passed parsing, routing, rewrite, and filter checks",
            parsed_sql=parsed_sql,
            rewritten_sql=rewritten_sql,
            logical_tables=[target.logical_table_name for target in route_decision.targets],
            physical_tables=[target.physical_table_name for target in route_decision.targets],
            datasource_codes=[target.datasource_code for target in route_decision.targets],
            explain_summaries=[summary.__dict__ for summary in filter_context.explain_summaries],
            route_diagnostics=[asdict(item) for item in route_decision.diagnostics],
        )
