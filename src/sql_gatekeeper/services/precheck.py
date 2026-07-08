import re
from dataclasses import dataclass


DISALLOWED_SQL_PREFIXES = {"update", "delete", "insert", "replace", "drop", "alter", "truncate"}


@dataclass(frozen=True)
class PrecheckDecision:
    allowed: bool
    reason_code: str
    message: str


class BasicSqlGuard:
    def evaluate(self, sql: str) -> PrecheckDecision:
        normalized = sql.strip()
        if not normalized:
            return PrecheckDecision(False, "EMPTY_SQL", "SQL must not be empty")

        lowered = normalized.lower()
        sql_without_trailing_semicolon = lowered.rstrip(";").strip()
        if ";" in sql_without_trailing_semicolon:
            return PrecheckDecision(False, "MULTI_STATEMENT", "Multiple SQL statements are not allowed")

        if lowered.startswith("--") or lowered.startswith("/*"):
            return PrecheckDecision(False, "LEADING_COMMENT", "Leading comments are not allowed")

        first_token_match = re.match(r"^\s*([a-zA-Z]+)", lowered)
        first_token = first_token_match.group(1) if first_token_match else ""
        if first_token in DISALLOWED_SQL_PREFIXES:
            return PrecheckDecision(False, "SQL_TYPE_DENIED", f"SQL type '{first_token}' is not allowed")

        if first_token != "select":
            return PrecheckDecision(False, "UNSUPPORTED_SQL", "Only SELECT SQL is supported in the current stage")

        return PrecheckDecision(True, "ALLOW", "SQL passed the basic precheck")

