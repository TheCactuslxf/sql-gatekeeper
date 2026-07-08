from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from sql_gatekeeper.config import Settings
from sql_gatekeeper.db.models import (
    DatasourceInstance,
    LogicalTable,
    PhysicalTableRoute,
    PolicySet,
    RouteFactorDef,
    RouteRule,
)


ORDER_DB_ROOT_DSN = "mysql+pymysql://root:root@127.0.0.1:33063/biz_order"


def build_mysql_settings() -> Settings:
    return Settings(
        META_DB_HOST="127.0.0.1",
        META_DB_PORT=33061,
        META_DB_NAME="gatekeeper_meta",
        META_DB_USER="gatekeeper",
        META_DB_PASSWORD="gatekeeper",
    )


def ensure_large_order_shard(
    physical_table_name: str = "order_2025_08",
    target_rows: int = 1_000_000,
) -> int:
    engine = create_engine(ORDER_DB_ROOT_DSN, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                create table if not exists {physical_table_name} (
                  order_id varchar(64) primary key,
                  amount decimal(10,2) not null,
                  tenant_id varchar(64) not null
                )
                """
            )
        )
        current_count = int(connection.execute(text(f"select count(*) from {physical_table_name}")).scalar_one())
        if current_count >= target_rows:
            return current_count

        connection.execute(text(f"truncate table {physical_table_name}"))
        connection.execute(
            text(
                f"""
                insert into {physical_table_name} (order_id, amount, tenant_id)
                select concat('B', lpad(seq, 7, '0')),
                       mod(seq, 100000) / 100,
                       concat('t', mod(seq, 100))
                from (
                  select ones.n
                         + tens.n * 10
                         + hundreds.n * 100
                         + thousands.n * 1000
                         + tenthousands.n * 10000
                         + hundredthousands.n * 100000
                         + 1 as seq
                  from (select 0 n union all select 1 union all select 2 union all select 3 union all select 4 union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) ones
                  cross join (select 0 n union all select 1 union all select 2 union all select 3 union all select 4 union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) tens
                  cross join (select 0 n union all select 1 union all select 2 union all select 3 union all select 4 union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) hundreds
                  cross join (select 0 n union all select 1 union all select 2 union all select 3 union all select 4 union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) thousands
                  cross join (select 0 n union all select 1 union all select 2 union all select 3 union all select 4 union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) tenthousands
                  cross join (select 0 n union all select 1 union all select 2 union all select 3 union all select 4 union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) hundredthousands
                ) as generated_rows
                where generated_rows.seq <= :target_rows
                """
            ),
            {"target_rows": target_rows},
        )
    return target_rows


def ensure_order_route(
    session: Session,
    *,
    route_value: str,
    physical_table_name: str,
) -> None:
    logical_table = session.execute(select(LogicalTable).where(LogicalTable.table_name == "order")).scalar_one()
    datasource = session.execute(
        select(DatasourceInstance).where(DatasourceInstance.datasource_code == "biz_order_db")
    ).scalar_one()
    existing = session.execute(
        select(PhysicalTableRoute).where(
            PhysicalTableRoute.logical_table_id == logical_table.id,
            PhysicalTableRoute.route_value == route_value,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            PhysicalTableRoute(
                logical_table_id=logical_table.id,
                route_value=route_value,
                physical_table_name=physical_table_name,
                datasource_id=datasource.id,
                enabled=True,
                extra={},
            )
        )
        session.commit()


def seed_extended_route_metadata(session: Session) -> None:
    policy = PolicySet(
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
    session.add(policy)

    user_ds = DatasourceInstance(
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
    order_ds = DatasourceInstance(
        datasource_code="biz_order_db",
        display_name="Order DB",
        host="127.0.0.1",
        port=33063,
        database_name="biz_order",
        username="readonly",
        password_secret_ref="local:readonly",
        read_only=True,
        enabled=True,
        extra={},
    )
    session.add_all([user_ds, order_ds])
    session.flush()

    user_table = LogicalTable(
        table_name="user",
        description="user",
        route_source="sql_or_physical_table",
        physical_name_template="user_{suffix}",
        default_policy_code="default_select_guard",
        enabled=True,
        extra={},
    )
    order_table = LogicalTable(
        table_name="order",
        description="order",
        route_source="route_context_or_sql",
        physical_name_template="order_{biz_date}",
        default_policy_code="default_select_guard",
        enabled=True,
        extra={},
    )
    invoice_table = LogicalTable(
        table_name="invoice",
        description="invoice",
        route_source="sql_and_route_context",
        physical_name_template="invoice_{route_key}",
        default_policy_code="default_select_guard",
        enabled=True,
        extra={},
    )
    session.add_all([user_table, order_table, invoice_table])
    session.flush()

    session.add_all(
        [
            RouteFactorDef(
                logical_table_id=user_table.id,
                factor_name="uid",
                source_type="sql_predicate",
                source_key="uid",
                required=True,
                extractor_config={},
                enabled=True,
            ),
            RouteFactorDef(
                logical_table_id=order_table.id,
                factor_name="biz_date",
                source_type="route_context",
                source_key="biz_date",
                required=True,
                extractor_config={},
                enabled=True,
            ),
            RouteFactorDef(
                logical_table_id=invoice_table.id,
                factor_name="uid",
                source_type="sql_predicate",
                source_key="uid",
                required=True,
                extractor_config={},
                enabled=True,
            ),
            RouteFactorDef(
                logical_table_id=invoice_table.id,
                factor_name="biz_date",
                source_type="route_context",
                source_key="biz_date",
                required=True,
                extractor_config={},
                enabled=True,
            ),
        ]
    )
    session.add_all(
        [
            RouteRule(
                logical_table_id=user_table.id,
                rule_name="user_mod_2",
                rule_type="mod",
                expression="int(uid) % 2",
                output_format="{value}",
                enabled=True,
            ),
            RouteRule(
                logical_table_id=order_table.id,
                rule_name="order_month",
                rule_type="format",
                expression="biz_date.replace('-', '_')",
                output_format="{value}",
                enabled=True,
            ),
            RouteRule(
                logical_table_id=invoice_table.id,
                rule_name="invoice_month_uid",
                rule_type="format",
                expression="biz_date.replace('-', '_') + '_' + str(int(uid) % 2)",
                output_format="{value}",
                enabled=True,
            ),
        ]
    )
    session.add_all(
        [
            PhysicalTableRoute(
                logical_table_id=user_table.id,
                route_value="0",
                physical_table_name="user_0",
                datasource_id=user_ds.id,
                enabled=True,
                extra={},
            ),
            PhysicalTableRoute(
                logical_table_id=user_table.id,
                route_value="1",
                physical_table_name="user_1",
                datasource_id=user_ds.id,
                enabled=True,
                extra={},
            ),
            PhysicalTableRoute(
                logical_table_id=order_table.id,
                route_value="2025_06",
                physical_table_name="order_2025_06",
                datasource_id=order_ds.id,
                enabled=True,
                extra={},
            ),
            PhysicalTableRoute(
                logical_table_id=order_table.id,
                route_value="2025_07",
                physical_table_name="order_2025_07",
                datasource_id=order_ds.id,
                enabled=True,
                extra={},
            ),
            PhysicalTableRoute(
                logical_table_id=invoice_table.id,
                route_value="2025_07_1",
                physical_table_name="invoice_2025_07_1",
                datasource_id=order_ds.id,
                enabled=True,
                extra={},
            ),
        ]
    )
    session.commit()
