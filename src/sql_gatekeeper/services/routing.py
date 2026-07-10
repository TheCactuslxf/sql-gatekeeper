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
class RouteFactorDiagnostic:
    factor_name: str
    source_type: str
    source_key: str
    required: bool
    provided_value: str | None
    extractor_config: dict


@dataclass(frozen=True)
class RouteDiagnostic:
    original_table_name: str
    logical_table_name: str
    route_source: str
    required_factors: list[RouteFactorDiagnostic]
    missing_factors: list[str]
    extracted_values: dict[str, str]
    route_rule: dict | None
    evaluated_route_value: str | None
    available_route_values_sample: list[str]
    available_route_count: int


@dataclass(frozen=True)
class RouteDecision:
    allowed: bool
    reason_code: str
    message: str
    targets: list[RouteTarget]
    diagnostics: list[RouteDiagnostic]


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
            return RouteDecision(False, "TABLE_NOT_FOUND", "No SQL table was found", [], [])

        targets: list[RouteTarget] = []
        diagnostics: list[RouteDiagnostic] = []
        for table in parsed_sql.tables:
            physical_match = self.physical_table_route_repo.get_enabled_by_physical_table_name(table.table_name)
            if physical_match is not None:
                target = self._build_physical_target(table, physical_match)
                if target is None:
                    return RouteDecision(
                        False,
                        "DATASOURCE_NOT_FOUND",
                        "Datasource for physical table was not found",
                        [],
                        diagnostics,
                    )
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
                        diagnostics,
                    )
                return RouteDecision(
                    False,
                    "LOGICAL_TABLE_NOT_FOUND",
                    f"Logical table '{table.table_name}' was not found",
                    [],
                    diagnostics,
                )

            factors = self.route_factor_repo.list_required_enabled_by_logical_table(logical_table.id)
            route_rule = self.route_rule_repo.get_enabled_by_logical_table(logical_table.id)
            available_route_values_sample = self.physical_table_route_repo.list_enabled_route_values_by_logical_table(
                logical_table.id
            )
            available_route_count = self.physical_table_route_repo.count_enabled_by_logical_table(logical_table.id)
            if route_rule is None:
                diagnostics.append(
                    self._build_route_diagnostic(
                        table=table,
                        logical_table=logical_table,
                        factors=factors,
                        extracted_values={},
                        missing_factors=[],
                        route_rule=None,
                        evaluated_route_value=None,
                        available_route_values_sample=available_route_values_sample,
                        available_route_count=available_route_count,
                    )
                )
                return RouteDecision(
                    False,
                    "ROUTE_RULE_NOT_FOUND",
                    f"No route rule for '{table.table_name}'",
                    [],
                    diagnostics,
                )

            extracted_values: dict[str, str] = {}
            missing_factors: list[str] = []
            for factor in factors:
                factor_value = self._extract_factor_value(factor, parsed_sql, table, route_context)
                if factor_value is None and factor.source_key == "route_suffix":
                    factor_value = self._derive_legacy_route_suffix(
                        logical_table=logical_table,
                        parsed_sql=parsed_sql,
                        table=table,
                        route_context=route_context,
                    )
                if factor_value is None:
                    missing_factors.append(factor.factor_name)
                else:
                    extracted_values[factor.factor_name] = factor_value

            if missing_factors:
                diagnostics.append(
                    self._build_route_diagnostic(
                        table=table,
                        logical_table=logical_table,
                        factors=factors,
                        extracted_values=extracted_values,
                        missing_factors=missing_factors,
                        route_rule=route_rule,
                        evaluated_route_value=None,
                        available_route_values_sample=available_route_values_sample,
                        available_route_count=available_route_count,
                    )
                )
                return RouteDecision(
                    False,
                    "MISSING_ROUTE_FACTOR",
                    f"Missing route factors for '{table.table_name}': {', '.join(missing_factors)}",
                    [],
                    diagnostics,
                )

            route_value = self._evaluate_route_rule(route_rule, extracted_values)
            diagnostics.append(
                self._build_route_diagnostic(
                    table=table,
                    logical_table=logical_table,
                    factors=factors,
                    extracted_values=extracted_values,
                    missing_factors=[],
                    route_rule=route_rule,
                    evaluated_route_value=route_value,
                    available_route_values_sample=available_route_values_sample,
                    available_route_count=available_route_count,
                )
            )
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
                    diagnostics,
                )

            datasource = self.datasource_repo.get_enabled_by_code(
                self._datasource_code_from_id(physical_route.datasource_id)
            )
            if datasource is None:
                return RouteDecision(
                    False,
                    "DATASOURCE_NOT_FOUND",
                    "Datasource for route target was not found",
                    [],
                    diagnostics,
                )

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

        return RouteDecision(True, "ALLOW", "Route resolution succeeded", targets, diagnostics)

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
        if source_type == "sql_predicate_from_context":
            column = route_context.get(factor.source_key)
            if not isinstance(column, str) or not column:
                return None
            return parsed_sql.predicate_value(column, qualifier=table.alias) or parsed_sql.predicate_value(column)
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

    def _derive_legacy_route_suffix(
        self,
        *,
        logical_table: LogicalTable,
        parsed_sql: ParsedSql,
        table: ParsedTable,
        route_context: dict,
    ) -> str | None:
        column = route_context.get("shard_column")
        if not isinstance(column, str) or not column:
            return None

        value = parsed_sql.predicate_value(column, qualifier=table.alias) or parsed_sql.predicate_value(column)
        if value is None:
            return None

        route_count = self.physical_table_route_repo.count_enabled_by_logical_table(logical_table.id)
        if route_count <= 0:
            return None

        try:
            return str(int(value) % route_count)
        except (TypeError, ValueError):
            return None

    def _build_route_diagnostic(
        self,
        *,
        table: ParsedTable,
        logical_table: LogicalTable,
        factors: list[RouteFactorDef],
        extracted_values: dict[str, str],
        missing_factors: list[str],
        route_rule: RouteRule | None,
        evaluated_route_value: str | None,
        available_route_values_sample: list[str],
        available_route_count: int,
    ) -> RouteDiagnostic:
        return RouteDiagnostic(
            original_table_name=table.table_name,
            logical_table_name=logical_table.table_name,
            route_source=logical_table.route_source,
            required_factors=[
                RouteFactorDiagnostic(
                    factor_name=factor.factor_name,
                    source_type=factor.source_type,
                    source_key=factor.source_key,
                    required=factor.required,
                    provided_value=extracted_values.get(factor.factor_name),
                    extractor_config=factor.extractor_config,
                )
                for factor in factors
            ],
            missing_factors=missing_factors,
            extracted_values=extracted_values,
            route_rule=None
            if route_rule is None
            else {
                "rule_name": route_rule.rule_name,
                "rule_type": route_rule.rule_type,
                "expression": route_rule.expression,
                "output_format": route_rule.output_format,
            },
            evaluated_route_value=evaluated_route_value,
            available_route_values_sample=available_route_values_sample,
            available_route_count=available_route_count,
        )

    def _datasource_code_from_id(self, datasource_id: int) -> str:
        datasource = self.session.get(DatasourceInstance, datasource_id)
        return datasource.datasource_code if datasource is not None else ""

    def _match_invalid_physical_table(self, table_name: str) -> LogicalTable | None:
        for logical_table in self.logical_table_repo.list_enabled():
            prefix = logical_table.physical_name_template.split("{", 1)[0]
            if prefix and table_name.startswith(prefix):
                return logical_table
        return None
