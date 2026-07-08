from sql_gatekeeper.db.models import (
    DatasourceInstance,
    LogicalTable,
    PhysicalTableRoute,
)
from sql_gatekeeper.services.routing import RouteDecisionService
from sql_gatekeeper.services.sql_parser import SqlParser
from tests_support import seed_extended_route_metadata


def test_routing_resolves_existing_physical_table_without_rewrite(meta_session):
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
    meta_session.add(user_ds)
    meta_session.flush()
    logical_table = LogicalTable(
        table_name="user",
        description="user",
        route_source="sql_or_physical_table",
        physical_name_template="user_{suffix}",
        default_policy_code="default_select_guard",
        enabled=True,
        extra={},
    )
    meta_session.add(logical_table)
    meta_session.flush()
    meta_session.add(
        PhysicalTableRoute(
            logical_table_id=logical_table.id,
            route_value="1",
            physical_table_name="user_1",
            datasource_id=user_ds.id,
            enabled=True,
            extra={},
        )
    )
    meta_session.commit()

    parsed = SqlParser().parse("select * from user_1 where uid = 10001")
    decision = RouteDecisionService(meta_session).resolve(parsed, {})

    assert decision.allowed is True
    assert decision.targets[0].requires_rewrite is False
    assert decision.targets[0].physical_table_name == "user_1"


def test_routing_resolves_logical_user_table_by_uid_mod(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from user where uid = '10001'")
    decision = RouteDecisionService(meta_session).resolve(parsed, {})

    assert decision.allowed is True
    assert decision.targets[0].requires_rewrite is True
    assert decision.targets[0].physical_table_name == "user_1"
    assert decision.targets[0].datasource_code == "biz_user_db"


def test_routing_resolves_logical_user_table_to_another_shard(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from user where uid = '10000'")
    decision = RouteDecisionService(meta_session).resolve(parsed, {})

    assert decision.allowed is True
    assert decision.targets[0].requires_rewrite is True
    assert decision.targets[0].physical_table_name == "user_0"
    assert decision.targets[0].datasource_code == "biz_user_db"


def test_routing_resolves_time_shard_from_route_context(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from order where order_id = 'A1001'")
    decision = RouteDecisionService(meta_session).resolve(parsed, {"biz_date": "2025-06"})

    assert decision.allowed is True
    assert decision.targets[0].requires_rewrite is True
    assert decision.targets[0].physical_table_name == "order_2025_06"
    assert decision.targets[0].datasource_code == "biz_order_db"


def test_routing_resolves_time_shard_to_another_month(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from order where order_id = 'A1002'")
    decision = RouteDecisionService(meta_session).resolve(parsed, {"biz_date": "2025-07"})

    assert decision.allowed is True
    assert decision.targets[0].requires_rewrite is True
    assert decision.targets[0].physical_table_name == "order_2025_07"
    assert decision.targets[0].datasource_code == "biz_order_db"


def test_routing_resolves_multi_alias_dynamic_shards(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse(
        "select * from user u join user v on u.uid <> v.uid where u.uid = '10000' and v.uid = '10001'"
    )
    decision = RouteDecisionService(meta_session).resolve(parsed, {})

    assert decision.allowed is True
    assert [target.physical_table_name for target in decision.targets] == ["user_0", "user_1"]


def test_routing_resolves_combined_sql_and_route_context(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from invoice where uid = '10001'")
    decision = RouteDecisionService(meta_session).resolve(parsed, {"biz_date": "2025-07"})

    assert decision.allowed is True
    assert decision.targets[0].physical_table_name == "invoice_2025_07_1"
    assert decision.targets[0].datasource_code == "biz_order_db"


def test_routing_rejects_when_route_context_is_missing(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from order where order_id = 'A1001'")
    decision = RouteDecisionService(meta_session).resolve(parsed, {})

    assert decision.allowed is False
    assert decision.reason_code == "MISSING_ROUTE_FACTOR"


def test_routing_rejects_invalid_physical_table_name(meta_session):
    seed_extended_route_metadata(meta_session)
    parsed = SqlParser().parse("select * from user_99 where uid = 10099")
    decision = RouteDecisionService(meta_session).resolve(parsed, {})

    assert decision.allowed is False
    assert decision.reason_code == "INVALID_PHYSICAL_TABLE"
