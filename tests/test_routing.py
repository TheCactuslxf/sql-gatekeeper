from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sql_gatekeeper.db.base import Base
from sql_gatekeeper.db.models import (
    DatasourceInstance,
    LogicalTable,
    PhysicalTableRoute,
    RouteFactorDef,
    RouteRule,
)
from sql_gatekeeper.services.routing import RouteDecisionService
from sql_gatekeeper.services.sql_parser import SqlParser
from tests_support import seed_extended_route_metadata


def test_routing_resolves_business_shard_column_without_external_mysql():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        datasource = DatasourceInstance(
            id=1,
            datasource_code="partner_db",
            display_name="Partner DB",
            host="127.0.0.1",
            port=3306,
            database_name="partner",
            username="readonly",
            password_secret_ref="local:readonly",
            read_only=True,
            enabled=True,
            extra={},
        )
        logical_table = LogicalTable(
            id=1,
            table_name="partner__partner_relation_info",
            description="partner relations",
            route_source="sql_and_route_context",
            physical_name_template="partner_relation_info_{route_suffix}",
            default_policy_code="default_select_guard",
            enabled=True,
            extra={"shard_modulus": 2},
        )
        session.add_all([datasource, logical_table])
        session.flush()
        session.add_all(
            [
                RouteFactorDef(
                    id=1,
                    logical_table_id=logical_table.id,
                    factor_name="shard_value",
                    source_type="sql_predicate_from_context",
                    source_key="shard_column",
                    required=True,
                    extractor_config={},
                    enabled=True,
                ),
                RouteRule(
                    id=1,
                    logical_table_id=logical_table.id,
                    rule_name="business_shard_mod",
                    rule_type="mod",
                    expression="str(int(shard_value) % 2)",
                    output_format="{value}",
                    enabled=True,
                ),
                PhysicalTableRoute(
                    id=1,
                    logical_table_id=logical_table.id,
                    route_value="0",
                    physical_table_name="partner_relation_info_0",
                    datasource_id=datasource.id,
                    enabled=True,
                    extra={},
                ),
                PhysicalTableRoute(
                    id=2,
                    logical_table_id=logical_table.id,
                    route_value="1",
                    physical_table_name="partner_relation_info_1",
                    datasource_id=datasource.id,
                    enabled=True,
                    extra={},
                ),
            ]
        )
        session.commit()

        parsed = SqlParser().parse(
            "select count(1) as cnt from partner__partner_relation_info "
            "where from_uid = '97585024' limit 1"
        )
        route_service = RouteDecisionService(session)
        decision = route_service.resolve(parsed, {"shard_column": "from_uid"})

        assert decision.allowed is True
        assert decision.targets[0].route_value == "0"
        assert decision.targets[0].physical_table_name == "partner_relation_info_0"
        assert route_service._derive_legacy_route_suffix(
            logical_table=logical_table,
            parsed_sql=parsed,
            table=parsed.tables[0],
            route_context={"shard_column": "from_uid"},
        ) == "0"


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


def test_routing_derives_legacy_route_suffix_from_business_shard_column(meta_session):
    datasource = DatasourceInstance(
        datasource_code="partner_db",
        display_name="Partner DB",
        host="127.0.0.1",
        port=33062,
        database_name="partner",
        username="readonly",
        password_secret_ref="local:readonly",
        read_only=True,
        enabled=True,
        extra={},
    )
    meta_session.add(datasource)
    meta_session.flush()

    logical_table = LogicalTable(
        table_name="partner__partner_relation_info",
        description="partner relations",
        route_source="route_context_or_sql",
        physical_name_template="partner_relation_info_{route_suffix}",
        default_policy_code="default_select_guard",
        enabled=True,
        extra={"sync_origin": "spy.table_config", "shard_count_values": [2]},
    )
    meta_session.add(logical_table)
    meta_session.flush()
    meta_session.add_all(
        [
            RouteFactorDef(
                logical_table_id=logical_table.id,
                factor_name="route_suffix",
                source_type="route_context",
                source_key="route_suffix",
                required=True,
                extractor_config={},
                enabled=True,
            ),
            RouteRule(
                logical_table_id=logical_table.id,
                rule_name="imported_route_suffix_passthrough",
                rule_type="route_context_passthrough",
                expression="str(int(route_suffix))",
                output_format="{value}",
                enabled=True,
            ),
            PhysicalTableRoute(
                logical_table_id=logical_table.id,
                route_value="0",
                physical_table_name="partner_relation_info_0",
                datasource_id=datasource.id,
                enabled=True,
                extra={},
            ),
            PhysicalTableRoute(
                logical_table_id=logical_table.id,
                route_value="1",
                physical_table_name="partner_relation_info_1",
                datasource_id=datasource.id,
                enabled=True,
                extra={},
            ),
        ]
    )
    meta_session.commit()

    parsed = SqlParser().parse(
        "select count(1) as cnt from partner__partner_relation_info "
        "where from_uid = '97585024' limit 1"
    )
    decision = RouteDecisionService(meta_session).resolve(parsed, {"shard_column": "from_uid"})

    assert decision.allowed is True
    assert decision.targets[0].route_value == "0"
    assert decision.targets[0].physical_table_name == "partner_relation_info_0"


def test_routing_extracts_shard_value_from_context_selected_sql_predicate(meta_session):
    parsed = SqlParser().parse(
        "select * from partner__partner_relation_info where from_uid = '97585024' limit 1"
    )
    factor = RouteFactorDef(
        logical_table_id=1,
        factor_name="shard_value",
        source_type="sql_predicate_from_context",
        source_key="shard_column",
        required=True,
        extractor_config={},
        enabled=True,
    )

    value = RouteDecisionService(meta_session)._extract_factor_value(
        factor,
        parsed,
        parsed.tables[0],
        {"shard_column": "from_uid"},
    )

    assert value == "97585024"


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
