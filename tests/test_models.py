from sql_gatekeeper.db.models import (
    DatasourceInstance,
    LogicalTable,
    PhysicalTableRoute,
    PolicySet,
    RequestAuditLog,
    RouteFactorDef,
    RouteRule,
    TableStatsSnapshot,
)


def test_metadata_tables_are_registered():
    table_names = {
        DatasourceInstance.__tablename__,
        LogicalTable.__tablename__,
        RouteFactorDef.__tablename__,
        RouteRule.__tablename__,
        PhysicalTableRoute.__tablename__,
        PolicySet.__tablename__,
        TableStatsSnapshot.__tablename__,
        RequestAuditLog.__tablename__,
    }

    assert table_names == {
        "datasource_instance",
        "logical_table",
        "route_factor_def",
        "route_rule",
        "physical_table_route",
        "policy_set",
        "table_stats_snapshot",
        "request_audit_log",
    }
