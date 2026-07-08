from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from sql_gatekeeper.db.models import DatasourceInstance, LogicalTable, PhysicalTableRoute, RouteFactorDef, RouteRule
from sql_gatekeeper.repositories.datasource import DatasourceInstanceRepository
from sql_gatekeeper.repositories.logical_table import LogicalTableRepository
from sql_gatekeeper.repositories.physical_table_route import PhysicalTableRouteRepository
from sql_gatekeeper.repositories.route_factor import RouteFactorDefRepository
from sql_gatekeeper.repositories.route_rule import RouteRuleRepository
from sql_gatekeeper.services.sql_parser import ParsedSql, ParsedTable
from sql_gatekeeper.services.sql_rewrite import TableRewritePlan


@dataclass(frozen=True)
class RouteTarget:
    original_table_name: str
    logical_table_name: str
    physical_table_name: str
    datasource_code: str
    requires_rewrite: bool
    rewrite_plan: TableRewritePlan | None
    route_value: str


@dataclass(frozen=True)
class RouteDecision:
    allowed: bool
    reason_code: str
    message: str
    targets: list[RouteTarget]


class RouteDecisionService:
    def __init__(self, session: Session):
        self.session = session
        self.logical_table_repo = LogicalTableRepository(session)
        self.physical_table_route_repo = PhysicalTableRouteRepository(session)
        self.route_factor_repo = RouteFactorDefRepository(session)
        self.route_rule_repo = RouteRuleRepository(session)
        self.datasource_repo = DatasourceInstanceRepository(session)

    def resolve(self, parsed_sql: ParsedSql, route_context: dict) -> RouteDecision:
        if not parsed_sql.tables:
            return RouteDecision(False, "TABLE_NOT_FOUND", "No SQL table was found", [])

        targets: list[RouteTarget] = []
        for table in parsed_sql.tables:
            physical_match = self.physical_table_route_repo.get_enabled_by_physical_table_name(table.table_name)
            if physical_match is not None:
                target = self._build_physical_target(table, physical_match)
                if target is None:
                    return RouteDecision(False, "DATASOURCE_NOT_FOUND", "Datasource for physical table was not found", [])
                targets.append(target)
                continue

            logical_table = self.logical_table_repo.get_enabled_by_name(table.table_name)
            if logical_table is None:
                invalid_physical_logical_table = self._match_invalid_physical_table(table.table_name)
                if invalid_physical_logical_table is not None:
                    return RouteDecision(
                        False,
                        "INVALID_PHYSICAL_TABLE",
                        f"Physical table '{table.table_name}' is not registered for logical table '{invalid_physical_logical_table.table_name}'",
                        [],
                    )
                return RouteDecision(
                    False,
                    "LOGICAL_TABLE_NOT_FOUND",
                    f"Logical table '{table.table_name}' was not found",
                    [],
                )

            factors = self.route_factor_repo.list_required_enabled_by_logical_table(logical_table.id)
            route_rule = self.route_rule_repo.get_enabled_by_logical_table(logical_table.id)
            if route_rule is None:
                return RouteDecision(False, "ROUTE_RULE_NOT_FOUND", f"No route rule for '{table.table_name}'", [])

            extracted_values: dict[str, str] = {}
            missing_factors: list[str] = []
            for factor in factors:
                factor_value = self._extract_factor_value(factor, parsed_sql, table, route_context)
                if factor_value is None:
                    missing_factors.append(factor.factor_name)
                else:
                    extracted_values[factor.factor_name] = factor_value

            if missing_factors:
                return RouteDecision(
                    False,
                    "MISSING_ROUTE_FACTOR",
                    f"Missing route factors for '{table.table_name}': {', '.join(missing_factors)}",
                    [],
                )

            route_value = self._evaluate_route_rule(route_rule, extracted_values)
            physical_route = self.physical_table_route_repo.get_enabled_by_logical_table_and_route_value(
                logical_table.id,
                route_value,
            )
            if physical_route is None:
                return RouteDecision(
                    False,
                    "PHYSICAL_ROUTE_NOT_FOUND",
                    f"No physical route found for '{table.table_name}' with route value '{route_value}'",
                    [],
                )

            datasource = self.datasource_repo.get_enabled_by_code(
                self._datasource_code_from_id(physical_route.datasource_id)
            )
            if datasource is None:
                return RouteDecision(False, "DATASOURCE_NOT_FOUND", "Datasource for route target was not found", [])

            targets.append(
                RouteTarget(
                    original_table_name=table.table_name,
                    logical_table_name=logical_table.table_name,
                    physical_table_name=physical_route.physical_table_name,
                    datasource_code=datasource.datasource_code,
                    requires_rewrite=True,
                    rewrite_plan=TableRewritePlan(
                        original_table_name=table.table_name,
                        physical_table_name=physical_route.physical_table_name,
                        token_start=table.token_start,
                        token_end=table.token_end,
                    ),
                    route_value=route_value,
                )
            )

        return RouteDecision(True, "ALLOW", "Route resolution succeeded", targets)

    def _build_physical_target(self, table: ParsedTable, physical_route: PhysicalTableRoute) -> RouteTarget | None:
        datasource_code = self._datasource_code_from_id(physical_route.datasource_id)
        datasource = self.datasource_repo.get_enabled_by_code(datasource_code)
        if datasource is None:
            return None
        logical_table = self.session.get(LogicalTable, physical_route.logical_table_id)
        logical_table_name = logical_table.table_name if logical_table is not None else table.table_name
        return RouteTarget(
            original_table_name=table.table_name,
            logical_table_name=logical_table_name,
            physical_table_name=physical_route.physical_table_name,
            datasource_code=datasource.datasource_code,
            requires_rewrite=False,
            rewrite_plan=None,
            route_value=physical_route.route_value,
        )

    def _extract_factor_value(
        self,
        factor: RouteFactorDef,
        parsed_sql: ParsedSql,
        table: ParsedTable,
        route_context: dict,
    ) -> str | None:
        source_type = factor.source_type.lower()
        if source_type == "sql_predicate":
            return parsed_sql.predicate_value(factor.source_key, qualifier=table.alias) or parsed_sql.predicate_value(
                factor.source_key
            )
        if source_type == "route_context":
            value = route_context.get(factor.source_key)
            return None if value is None else str(value)
        if source_type == "physical_table_name":
            return table.table_name
        return None

    def _evaluate_route_rule(self, route_rule: RouteRule, extracted_values: dict[str, str]) -> str:
        safe_globals = {"__builtins__": {}, "int": int, "str": str}
        safe_locals = dict(extracted_values)
        route_value = eval(route_rule.expression, safe_globals, safe_locals)
        return route_rule.output_format.format(value=route_value, **extracted_values)

    def _datasource_code_from_id(self, datasource_id: int) -> str:
        datasource = self.session.get(DatasourceInstance, datasource_id)
        return datasource.datasource_code if datasource is not None else ""

    def _match_invalid_physical_table(self, table_name: str) -> LogicalTable | None:
        for logical_table in self.logical_table_repo.list_enabled():
            prefix = logical_table.physical_name_template.split("{", 1)[0]
            if prefix and table_name.startswith(prefix):
                return logical_table
        return None
