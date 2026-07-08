from dataclasses import dataclass

from sql_gatekeeper.db.models import DatasourceInstance, LogicalTable, PhysicalTableRoute, PolicySet
from sql_gatekeeper.services.explain import ExplainPlanSummary, ExplainRiskDecision
from sql_gatekeeper.services.filter_chain import (
    ExplainRiskFilter,
    FilterChain,
    FilterContext,
    LimitFilter,
    PhysicalTableValidateFilter,
    PolicyLoadFilter,
    SqlTypeFilter,
)
from sql_gatekeeper.services.routing import RouteDecision, RouteTarget
from sql_gatekeeper.services.sql_parser import SqlParser


@dataclass
class FakeExplainEvaluator:
    allowed: bool
    reason_code: str = "ALLOW"
    message: str = "ok"

    def evaluate(self, datasource, rewritten_sql, physical_table_name, policy):
        return ExplainRiskDecision(
            allowed=self.allowed,
            reason_code=self.reason_code,
            message=self.message,
            summary=ExplainPlanSummary(
                access_type="ref",
                key="PRIMARY",
                rows_examined=1,
                extra="",
                table_name=physical_table_name,
                estimated_table_rows=2,
            ),
        )

def _seed_user_policy(session, *, max_limit: int = 1000, require_limit: bool = True) -> None:
    datasource = DatasourceInstance(
        datasource_code="biz_user_db",
        display_name="User DB",
        host="127.0.0.1",
        port=33062,
        database_name="biz_user",
        username="readonly",
        password_secret_ref="local:readonly",
        read_only=True,
        enabled=True,
        extra={},
    )
    policy = PolicySet(
        policy_code="default_select_guard",
        allow_sql_types=["select"],
        require_limit=require_limit,
        max_limit=max_limit,
        large_table_row_threshold=1,
        max_scan_rows=100,
        reject_full_scan_on_large_table=True,
        reject_using_temporary=True,
        reject_using_filesort=True,
        enabled=True,
    )
    logical_table = LogicalTable(
        table_name="user",
        description="user",
        route_source="sql_or_physical_table",
        physical_name_template="user_{suffix}",
        default_policy_code="default_select_guard",
        enabled=True,
        extra={},
    )
    session.add_all([datasource, policy, logical_table])
    session.flush()
    session.add(
        PhysicalTableRoute(
            logical_table_id=logical_table.id,
            route_value="1",
            physical_table_name="user_1",
            datasource_id=datasource.id,
            enabled=True,
            extra={},
        )
    )
    session.commit()


def _build_context(sql: str) -> FilterContext:
    parsed_sql = SqlParser().parse(sql)
    return FilterContext(
        sql=parsed_sql.original_sql,
        route_context={},
        parsed_sql=parsed_sql,
        rewritten_sql=parsed_sql.original_sql,
        route_decision=RouteDecision(
            allowed=True,
            reason_code="ALLOW",
            message="ok",
            targets=[
                RouteTarget(
                    original_table_name="user_1",
                    logical_table_name="user",
                    physical_table_name="user_1",
                    datasource_code="biz_user_db",
                    requires_rewrite=False,
                    rewrite_plan=None,
                    route_value="1",
                )
            ],
        ),
    )


def _build_chain(session, allowed: bool = True) -> FilterChain:
    return FilterChain(
        [
            PolicyLoadFilter(session),
            PhysicalTableValidateFilter(session),
            SqlTypeFilter(),
            LimitFilter(),
            ExplainRiskFilter(FakeExplainEvaluator(allowed)),
        ]
    )


def test_filter_chain_rejects_missing_limit(meta_session):
    _seed_user_policy(meta_session)
    context = _build_context("select * from user_1 where uid = 10001")
    decision = _build_chain(meta_session).run(context)

    assert decision.allowed is False
    assert decision.reason_code == "LIMIT_REQUIRED"


def test_filter_chain_allows_sql_when_limit_and_explain_pass(meta_session):
    _seed_user_policy(meta_session)
    context = _build_context("select * from user_1 where uid = 10001 limit 10")
    decision = _build_chain(meta_session).run(context)

    assert decision.allowed is True
    assert decision.reason_code == "ALLOW"
    assert len(context.explain_summaries) == 1


def test_filter_chain_rejects_limit_above_policy_max(meta_session):
    _seed_user_policy(meta_session, max_limit=100)
    context = _build_context("select * from user_1 where uid = 10001 limit 1000")
    decision = _build_chain(meta_session).run(context)

    assert decision.allowed is False
    assert decision.reason_code == "LIMIT_EXCEEDED"
