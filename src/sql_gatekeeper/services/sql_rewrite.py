from __future__ import annotations

from dataclasses import dataclass

from sql_gatekeeper.services.sql_parser import ParsedSql


@dataclass(frozen=True)
class TableRewritePlan:
    original_table_name: str
    physical_table_name: str
    token_start: int
    token_end: int


class SqlRewriteEngine:
    def rewrite(self, parsed_sql: ParsedSql, rewrite_plans: list[TableRewritePlan]) -> str:
        if not rewrite_plans:
            return parsed_sql.original_sql

        rewritten = parsed_sql.original_sql
        for plan in sorted(rewrite_plans, key=lambda item: item.token_start, reverse=True):
            rewritten = (
                rewritten[: plan.token_start]
                + plan.physical_table_name
                + rewritten[plan.token_end :]
            )
        return rewritten

