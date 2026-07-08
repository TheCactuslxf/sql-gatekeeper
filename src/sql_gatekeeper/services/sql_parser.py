from __future__ import annotations

import re
from dataclasses import dataclass


TABLE_PATTERN = re.compile(
    r"\b(from|join)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)
PREDICATE_PATTERN = re.compile(
    r"(?:(?P<qualifier>[A-Za-z_][A-Za-z0-9_]*)\.)?(?P<column>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>'[^']*'|\"[^\"]*\"|-?\d+)",
    re.IGNORECASE,
)
LIMIT_PATTERN = re.compile(r"\blimit\s+(\d+)(?:\s*,\s*(\d+))?\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedTable:
    table_name: str
    alias: str | None
    token_start: int
    token_end: int


@dataclass(frozen=True)
class ParsedPredicate:
    qualifier: str | None
    column: str
    value: str


@dataclass(frozen=True)
class ParsedSql:
    original_sql: str
    sql_type: str
    tables: list[ParsedTable]
    predicates: list[ParsedPredicate]
    has_limit: bool
    limit_value: int | None
    is_multi_statement: bool

    def predicate_value(self, column: str, qualifier: str | None = None) -> str | None:
        for predicate in self.predicates:
            if predicate.column.lower() != column.lower():
                continue
            if qualifier is not None and (predicate.qualifier or "").lower() != qualifier.lower():
                continue
            return predicate.value
        return None


class SqlParser:
    def parse(self, sql: str) -> ParsedSql:
        stripped = sql.strip()
        lowered = stripped.lower()
        sql_without_trailing_semicolon = lowered.rstrip(";").strip()
        is_multi_statement = ";" in sql_without_trailing_semicolon

        sql_type_match = re.match(r"^\s*([a-zA-Z]+)", stripped)
        sql_type = sql_type_match.group(1).lower() if sql_type_match else "unknown"

        tables: list[ParsedTable] = []
        for match in TABLE_PATTERN.finditer(sql):
            table_name = match.group(2)
            tables.append(
                ParsedTable(
                    table_name=table_name,
                    alias=match.group(3),
                    token_start=match.start(2),
                    token_end=match.end(2),
                )
            )

        predicates: list[ParsedPredicate] = []
        for match in PREDICATE_PATTERN.finditer(sql):
            predicates.append(
                ParsedPredicate(
                    qualifier=match.group("qualifier"),
                    column=match.group("column"),
                    value=self._normalize_value(match.group("value")),
                )
            )

        return ParsedSql(
            original_sql=sql,
            sql_type=sql_type,
            tables=tables,
            predicates=predicates,
            has_limit=LIMIT_PATTERN.search(sql) is not None,
            limit_value=self._parse_limit_value(sql),
            is_multi_statement=is_multi_statement,
        )

    @staticmethod
    def _normalize_value(raw_value: str) -> str:
        if raw_value.startswith(("'", '"')) and raw_value.endswith(("'", '"')):
            return raw_value[1:-1]
        return raw_value

    @staticmethod
    def _parse_limit_value(sql: str) -> int | None:
        match = LIMIT_PATTERN.search(sql)
        if match is None:
            return None
        if match.group(2) is not None:
            return int(match.group(2))
        return int(match.group(1))
