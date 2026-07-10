from sql_gatekeeper.tools.spy_table_config_sync import (
    ImportedDatasourceTarget,
    TableConfigRow,
    build_sync_bundle,
    make_datasource_code,
    make_logical_table_name,
)


def test_make_identifiers_are_stable_and_bounded():
    datasource_code = make_datasource_code("Yanyin-TestDB")
    logical_table_name = make_logical_table_name("user-100", "appUser")

    assert datasource_code == "spy_src_yanyin_testdb"
    assert logical_table_name == "user_100__appuser"
    assert len(datasource_code) <= 64
    assert len(logical_table_name) <= 128


def test_build_sync_bundle_expands_sharded_rows_and_deduplicates_segments():
    bundle = build_sync_bundle(
        [
            TableConfigRow(
                source_name="user1",
                catlog_name="user",
                table_name="appUser",
                begin_index=0,
                end_index=1,
                shard_count=2,
            ),
            TableConfigRow(
                source_name="user1",
                catlog_name="user",
                table_name="appUser",
                begin_index=0,
                end_index=1,
                shard_count=2,
            ),
            TableConfigRow(
                source_name="user2",
                catlog_name="user",
                table_name="appUser",
                begin_index=2,
                end_index=3,
                shard_count=4,
            ),
            TableConfigRow(
                source_name="main",
                catlog_name="main",
                table_name="app_signature",
                begin_index=0,
                end_index=0,
                shard_count=0,
            ),
            TableConfigRow(
                source_name="main",
                catlog_name="main",
                table_name=" ",
                begin_index=0,
                end_index=0,
                shard_count=0,
            ),
        ]
        ,
        ImportedDatasourceTarget(
            host="db.example.com",
            port=3306,
            database_name="demo",
            username="reader",
            password_secret_ref="local:secret",
        ),
    )

    assert bundle.skipped_rows == 1
    assert len(bundle.datasources) == 3
    assert bundle.datasources[0]["host"] == "db.example.com"
    assert bundle.datasources[0]["database_name"] == "demo"
    assert len(bundle.logical_tables) == 2
    assert len(bundle.route_factors) == 1
    assert len(bundle.route_rules) == 2
    assert len(bundle.physical_routes) == 5

    sharded_logical = next(item for item in bundle.logical_tables if item["table_name"] == "user__appuser")
    assert sharded_logical["route_source"] == "sql_and_route_context"
    assert sharded_logical["physical_name_template"] == "appUser_{route_suffix}"
    assert sharded_logical["extra"]["shard_modulus"] == 4
    assert sharded_logical["extra"]["business_factor_routing"] is True

    factor = bundle.route_factors[0]
    assert factor["factor_name"] == "shard_value"
    assert factor["source_type"] == "sql_predicate_from_context"
    assert factor["source_key"] == "shard_column"

    sharded_rule = next(
        item for item in bundle.route_rules if item["logical_table_name"] == "user__appuser"
    )
    assert sharded_rule["expression"] == "str(int(shard_value) % 4)"

    physical_routes = {
        (item["logical_table_name"], item["route_value"]): (item["physical_table_name"], item["datasource_code"])
        for item in bundle.physical_routes
    }
    assert physical_routes[("user__appuser", "0")] == ("appUser_0", "spy_src_user1")
    assert physical_routes[("user__appuser", "3")] == ("appUser_3", "spy_src_user2")
    assert physical_routes[("main__app_signature", "0")] == ("app_signature", "spy_src_main")


def test_build_sync_bundle_routes_multi_source_single_table_by_source_name():
    bundle = build_sync_bundle(
        [
            TableConfigRow(
                source_name="main",
                catlog_name="lottery",
                table_name="app_lottery",
                begin_index=0,
                end_index=0,
                shard_count=0,
            ),
            TableConfigRow(
                source_name="lottery",
                catlog_name="lottery",
                table_name="app_lottery",
                begin_index=0,
                end_index=0,
                shard_count=0,
            ),
        ]
        ,
        ImportedDatasourceTarget(
            host="db.example.com",
            port=3306,
            database_name="demo",
            username="reader",
            password_secret_ref="local:secret",
        ),
    )

    assert len(bundle.logical_tables) == 1
    assert len(bundle.route_factors) == 1
    assert len(bundle.route_rules) == 1
    assert len(bundle.physical_routes) == 2

    logical_table = bundle.logical_tables[0]
    assert logical_table["table_name"] == "lottery__app_lottery"
    assert logical_table["route_source"] == "route_context_or_sql"

    factor = bundle.route_factors[0]
    assert factor["factor_name"] == "source_name"

    physical_routes = {
        item["route_value"]: (item["physical_table_name"], item["datasource_code"])
        for item in bundle.physical_routes
    }
    assert physical_routes["main"] == ("app_lottery", "spy_src_main")
    assert physical_routes["lottery"] == ("app_lottery", "spy_src_lottery")
