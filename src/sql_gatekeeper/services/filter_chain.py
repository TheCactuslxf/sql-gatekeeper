from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import DatasourceInstance, PolicySet
from sql_gatekeeper.repositories.datasource import DatasourceInstanceRepository
from sql_gatekeeper.repositories.policy_set import PolicySetRepository
from sql_gatekeeper.services.explain import ExplainPlanSummary, ExplainRiskEvaluator
from sql_gatekeeper.services.routing import RouteDecision, RouteTarget
from sql_gatekeeper.services.sql_parser import ParsedSql


@dataclass
class FilterContext:
    sql: str
    route_context: dict
    parsed_sql: ParsedSql
    rewritten_sql: str
    route_decision: RouteDecision
    policy: PolicySet | None = None
    datasources: dict[str, DatasourceInstance] = field(default_factory=dict)
    explain_summaries: list[ExplainPlanSummary] = field(default_factory=list)


@dataclass(frozen=True)
class FilterDecision:
    allowed: bool
    reason_code: str
    message: str


class SqlFilter(Protocol):
    def apply(self, context: FilterContext) -> FilterDecision:
        ...


class PolicyLoadFilter:
    def __init__(self, session: Session):
        self.policy_repo = PolicySetRepository(session)

    def apply(self, context: FilterContext) -> FilterDecision:
        first_target = context.route_decision.targets[0]
        policy = self.policy_repo.get_enabled_by_code("default_select_guard")
        if policy is None:
            return FilterDecision(False, "POLICY_NOT_FOUND", "No enabled policy set was found")
        context.policy = policy
        return FilterDecision(True, "ALLOW", "Policy loaded")


class PhysicalTableValidateFilter:
    def __init__(self, session: Session):
        self.datasource_repo = DatasourceInstanceRepository(session)

    def apply(self, context: FilterContext) -> FilterDecision:
        for target in context.route_decision.targets:
            datasource = self.datasource_repo.get_enabled_by_code(target.datasource_code)
            if datasource is None:
                return FilterDecision(
                    False,
                    "DATASOURCE_NOT_FOUND",
                    f"Datasource '{target.datasource_code}' was not found",
                )
            context.datasources[target.datasource_code] = datasource
        return FilterDecision(True, "ALLOW", "Physical tables and datasources validated")


class SqlTypeFilter:
    def apply(self, context: FilterContext) -> FilterDecision:
        assert context.policy is not None
        if context.parsed_sql.sql_type not in context.policy.allow_sql_types:
            return FilterDecision(
                False,
                "SQL_TYPE_DENIED",
                f"SQL type '{context.parsed_sql.sql_type}' is not allowed by policy",
            )
        return FilterDecision(True, "ALLOW", "SQL type allowed by policy")


class CrossDatasourceFilter:
    def apply(self, context: FilterContext) -> FilterDecision:
        datasource_codes = {target.datasource_code for target in context.route_decision.targets}
        if len(datasource_codes) > 1:
            return FilterDecision(
                False,
                "CROSS_DATASOURCE_JOIN",
                "A single SQL request cannot span multiple datasources",
            )
        return FilterDecision(True, "ALLOW", "Datasource scope check passed")


class LimitFilter:
    def apply(self, context: FilterContext) -> FilterDecision:
        assert context.policy is not None
        if context.policy.require_limit and not context.parsed_sql.has_limit:
            return FilterDecision(False, "LIMIT_REQUIRED", "A LIMIT clause is required by policy")
        if context.parsed_sql.limit_value is not None and context.parsed_sql.limit_value > context.policy.max_limit:
            return FilterDecision(
                False,
                "LIMIT_EXCEEDED",
                f"LIMIT {context.parsed_sql.limit_value} exceeded policy max {context.policy.max_limit}",
            )
        return FilterDecision(True, "ALLOW", "Limit check passed")


class ExplainRiskFilter:
    def __init__(self, evaluator: ExplainRiskEvaluator | None = None):
        self.evaluator = evaluator or ExplainRiskEvaluator()

    def apply(self, context: FilterContext) -> FilterDecision:
        assert context.policy is not None
        for target in context.route_decision.targets:
            datasource = context.datasources[target.datasource_code]
            explain_decision = self.evaluator.evaluate(
                datasource=datasource,
                rewritten_sql=context.rewritten_sql,
                physical_table_name=target.physical_table_name,
                policy=context.policy,
            )
            if explain_decision.summary is not None:
                context.explain_summaries.append(explain_decision.summary)
            if not explain_decision.allowed:
                return FilterDecision(
                    False,
                    explain_decision.reason_code,
                    explain_decision.message,
                )
        return FilterDecision(True, "ALLOW", "Explain checks passed")


class FilterChain:
    def __init__(self, filters: list[SqlFilter]):
        self.filters = filters

    def run(self, context: FilterContext) -> FilterDecision:
        for sql_filter in self.filters:
            decision = sql_filter.apply(context)
            if not decision.allowed:
                return decision
        return FilterDecision(True, "ALLOW", "All filters passed")
