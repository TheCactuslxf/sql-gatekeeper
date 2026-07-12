from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sql_gatekeeper.config import Settings, get_settings
from sql_gatekeeper.db.base import Base
from sql_gatekeeper.db.models import (
    DatasourceInstance,
    LogicalTable,
    PhysicalTableRoute,
    PolicySet,
    RouteFactorDef,
    RouteRule,
)


@dataclass(frozen=True)
class SeedPlan:
    datasource_codes: list[str]
    logical_tables: list[str]
    policy_codes: list[str]


def build_seed_plan() -> SeedPlan:
    return SeedPlan(
        datasource_codes=["biz_user_db", "biz_order_db"],
        logical_tables=["user", "order"],
        policy_codes=["default_select_guard"],
    )


def create_metadata_schema(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    engine = create_engine(app_settings.meta_db_dsn, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)


def seed_reference_data(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    engine = create_engine(app_settings.meta_db_dsn, pool_pre_ping=True)

    with Session(engine) as session:
        _upsert_policy(session)
        user_ds_id = _upsert_datasource(
            session,
            datasource_code="biz_user_db",
            display_name="Business User DB",
            host=app_settings.demo_user_db_host,
            port=app_settings.demo_user_db_port,
            database_name=app_settings.demo_user_db_name,
            username=app_settings.demo_user_db_user,
            password_secret_ref=f"local:{app_settings.demo_user_db_password}",
        )
        order_ds_id = _upsert_datasource(
            session,
            datasource_code="biz_order_db",
            display_name="Business Order DB",
            host=app_settings.demo_order_db_host,
            port=app_settings.demo_order_db_port,
            database_name=app_settings.demo_order_db_name,
            username=app_settings.demo_order_db_user,
            password_secret_ref=f"local:{app_settings.demo_order_db_password}",
        )
        user_table_id = _upsert_logical_table(
            session,
            table_name="user",
            description="Logical user table",
            route_source="sql_or_physical_table",
            physical_name_template="user_{suffix}",
        )
        order_table_id = _upsert_logical_table(
            session,
            table_name="order",
            description="Logical order table",
            route_source="route_context_or_sql",
            physical_name_template="order_{biz_date}",
        )
        _upsert_route_factor(
            session,
            logical_table_id=user_table_id,
            factor_name="uid",
            source_type="sql_predicate",
            source_key="uid",
        )
        _upsert_route_factor(
            session,
            logical_table_id=order_table_id,
            factor_name="biz_date",
            source_type="route_context",
            source_key="biz_date",
        )
        _upsert_route_rule(
            session,
            logical_table_id=user_table_id,
            rule_name="user_mod_2",
            rule_type="mod",
            expression="int(uid) % 2",
            output_format="{value}",
        )
        _upsert_route_rule(
            session,
            logical_table_id=order_table_id,
            rule_name="order_month",
            rule_type="format",
            expression="biz_date.replace('-', '_')",
            output_format="{value}",
        )
        _upsert_physical_route(session, user_table_id, "0", "user_0", user_ds_id)
        _upsert_physical_route(session, user_table_id, "1", "user_1", user_ds_id)
        _upsert_physical_route(session, order_table_id, "2025_06", "order_2025_06", order_ds_id)
        _upsert_physical_route(session, order_table_id, "2025_07", "order_2025_07", order_ds_id)
        session.commit()


def main() -> None:
    create_metadata_schema()
    seed_reference_data()
    print("metadata schema created and seed data loaded")


def _upsert_policy(session: Session) -> None:
    existing = session.query(PolicySet).filter_by(policy_code="default_select_guard").one_or_none()
    if existing is None:
        session.add(
            PolicySet(
                policy_code="default_select_guard",
                allow_sql_types=["select"],
                require_limit=True,
                max_limit=1000,
                large_table_row_threshold=100000,
                max_scan_rows=10000,
                reject_full_scan_on_large_table=True,
                reject_using_temporary=True,
                reject_using_filesort=True,
                enabled=True,
            )
        )


def _upsert_datasource(
    session: Session,
    *,
    datasource_code: str,
    display_name: str,
    host: str,
    port: int,
    database_name: str,
    username: str,
    password_secret_ref: str,
) -> int:
    existing = session.query(DatasourceInstance).filter_by(datasource_code=datasource_code).one_or_none()
    if existing is None:
        existing = DatasourceInstance(
            datasource_code=datasource_code,
            display_name=display_name,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            password_secret_ref=password_secret_ref,
            read_only=True,
            enabled=True,
            extra={},
        )
        session.add(existing)
        session.flush()
    else:
        existing.display_name = display_name
        existing.host = host
        existing.port = port
        existing.database_name = database_name
        existing.username = username
        existing.password_secret_ref = password_secret_ref
        existing.read_only = True
        existing.enabled = True
    return existing.id


def _upsert_logical_table(
    session: Session,
    *,
    table_name: str,
    description: str,
    route_source: str,
    physical_name_template: str,
) -> int:
    existing = session.query(LogicalTable).filter_by(table_name=table_name).one_or_none()
    if existing is None:
        existing = LogicalTable(
            table_name=table_name,
            description=description,
            route_source=route_source,
            physical_name_template=physical_name_template,
            default_policy_code="default_select_guard",
            enabled=True,
            extra={},
        )
        session.add(existing)
        session.flush()
    return existing.id


def _upsert_route_factor(
    session: Session,
    *,
    logical_table_id: int,
    factor_name: str,
    source_type: str,
    source_key: str,
) -> None:
    existing = (
        session.query(RouteFactorDef)
        .filter_by(logical_table_id=logical_table_id, factor_name=factor_name)
        .one_or_none()
    )
    if existing is None:
        session.add(
            RouteFactorDef(
                logical_table_id=logical_table_id,
                factor_name=factor_name,
                source_type=source_type,
                source_key=source_key,
                required=True,
                extractor_config={},
                enabled=True,
            )
        )


def _upsert_route_rule(
    session: Session,
    *,
    logical_table_id: int,
    rule_name: str,
    rule_type: str,
    expression: str,
    output_format: str,
) -> None:
    existing = session.query(RouteRule).filter_by(logical_table_id=logical_table_id, rule_name=rule_name).one_or_none()
    if existing is None:
        session.add(
            RouteRule(
                logical_table_id=logical_table_id,
                rule_name=rule_name,
                rule_type=rule_type,
                expression=expression,
                output_format=output_format,
                enabled=True,
            )
        )


def _upsert_physical_route(
    session: Session,
    logical_table_id: int,
    route_value: str,
    physical_table_name: str,
    datasource_id: int,
) -> None:
    existing = (
        session.query(PhysicalTableRoute)
        .filter_by(logical_table_id=logical_table_id, route_value=route_value)
        .one_or_none()
    )
    if existing is None:
        session.add(
            PhysicalTableRoute(
                logical_table_id=logical_table_id,
                route_value=route_value,
                physical_table_name=physical_table_name,
                datasource_id=datasource_id,
                enabled=True,
                extra={},
            )
        )


if __name__ == "__main__":
    main()

