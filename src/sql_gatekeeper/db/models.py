from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sql_gatekeeper.db.base import Base

ID_TYPE = BigInteger()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class DatasourceInstance(TimestampMixin, Base):
    __tablename__ = "datasource_instance"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    datasource_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    db_type: Mapped[str] = mapped_column(String(32), default="mysql", nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class LogicalTable(TimestampMixin, Base):
    __tablename__ = "logical_table"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    route_source: Mapped[str] = mapped_column(String(32), nullable=False)
    physical_name_template: Mapped[str] = mapped_column(String(255), nullable=False)
    default_policy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RouteFactorDef(TimestampMixin, Base):
    __tablename__ = "route_factor_def"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    logical_table_id: Mapped[int] = mapped_column(ForeignKey("logical_table.id"), nullable=False)
    factor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extractor_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("logical_table_id", "factor_name", name="uq_route_factor_table_name"),)


class RouteRule(TimestampMixin, Base):
    __tablename__ = "route_rule"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    logical_table_id: Mapped[int] = mapped_column(ForeignKey("logical_table.id"), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    output_format: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("logical_table_id", "rule_name", name="uq_route_rule_table_name"),)


class PhysicalTableRoute(TimestampMixin, Base):
    __tablename__ = "physical_table_route"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    logical_table_id: Mapped[int] = mapped_column(ForeignKey("logical_table.id"), nullable=False)
    route_value: Mapped[str] = mapped_column(String(128), nullable=False)
    physical_table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasource_instance.id"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("logical_table_id", "route_value", name="uq_table_route_value"),)


class PolicySet(TimestampMixin, Base):
    __tablename__ = "policy_set"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    policy_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    allow_sql_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    require_limit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    large_table_row_threshold: Mapped[int] = mapped_column(Integer, default=100000, nullable=False)
    max_scan_rows: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    reject_full_scan_on_large_table: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reject_using_temporary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reject_using_filesort: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TableStatsSnapshot(TimestampMixin, Base):
    __tablename__ = "table_stats_snapshot"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasource_instance.id"), nullable=False)
    physical_table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    data_length_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    index_length_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_analyzed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("datasource_id", "physical_table_name", name="uq_stats_table"),)


class RequestAuditLog(Base):
    __tablename__ = "request_audit_log"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    scene: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    original_sql: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_sql: Mapped[str] = mapped_column(Text, default="", nullable=False)
    logical_tables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    physical_tables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    datasource_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    explain_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
