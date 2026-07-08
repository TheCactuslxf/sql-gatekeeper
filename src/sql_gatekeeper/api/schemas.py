from typing import Any

from pydantic import BaseModel, Field


class SqlRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    operator: str = Field(min_length=1, max_length=128)
    scene: str = Field(default="", max_length=64)
    sql: str = Field(min_length=1)
    route_context: dict[str, Any] = Field(default_factory=dict)


class SqlDecisionResponse(BaseModel):
    request_id: str
    allowed: bool
    reason_code: str
    message: str
    rewritten_sql: str = ""
    physical_tables: list[str] = Field(default_factory=list)
    datasource_codes: list[str] = Field(default_factory=list)
    explain_summaries: list[dict[str, Any]] = Field(default_factory=list)
    execution_ms: int = 0
    row_count: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    app_name: str
    status: str
