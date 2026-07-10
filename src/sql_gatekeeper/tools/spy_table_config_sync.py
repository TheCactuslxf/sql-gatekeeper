from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pymysql
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from sql_gatekeeper.bootstrap.meta import create_metadata_schema
from sql_gatekeeper.config import Settings
from sql_gatekeeper.db.models import (
    DatasourceInstance,
    LogicalTable,
    PhysicalTableRoute,
    PolicySet,
    RouteFactorDef,
    RouteRule,
)

SYNC_ORIGIN = "spy.table_config"
DEFAULT_POLICY_CODE = "default_select_guard"
DEFAULT_ROUTE_FACTOR = "route_suffix"
BUSINESS_SHARD_FACTOR = "shard_value"
BUSINESS_SHARD_COLUMN_CONTEXT = "shard_column"
SOURCE_ROUTE_FACTOR = "source_name"


@dataclass(frozen=True)
class TableConfigRow:
    source_name: str
    catlog_name: str
    table_name: str
    begin_index: int
    end_index: int
    shard_count: int
    update_time: datetime | None = None


@dataclass(frozen=True)
class SyncBundle:
    datasources: list[dict[str, Any]]
    logical_tables: list[dict[str, Any]]
    route_factors: list[dict[str, Any]]
    route_rules: list[dict[str, Any]]
    physical_routes: list[dict[str, Any]]
    skipped_rows: int


@dataclass(frozen=True)
class ImportedDatasourceTarget:
    host: str
    port: int
    database_name: str
    username: str
    password_secret_ref: str


def make_stable_identifier(raw: str, *, prefix: str, max_length: int) -> str:
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in raw).strip("_")
    if not base:
        base = "unknown"

    candidate = f"{prefix}{base}"
    if len(candidate) <= max_length:
        return candidate

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    available = max_length - len(prefix) - len(digest) - 1
    truncated = base[: max(1, available)].rstrip("_")
    return f"{prefix}{truncated}_{digest}"


def make_datasource_code(source_name: str) -> str:
    return make_stable_identifier(source_name or "unknown_source", prefix="spy_src_", max_length=64)


def make_logical_table_name(catlog_name: str, table_name: str) -> str:
    raw = f"{catlog_name or 'unknown_catalog'}__{table_name}"
    return make_stable_identifier(raw, prefix="", max_length=128)


def build_imported_datasource_target_from_env() -> ImportedDatasourceTarget:
    password = os.environ.get("SPY_DB_PASSWORD")
    if not password:
        raise RuntimeError("SPY_DB_PASSWORD is required for imported datasource connection settings")

    return ImportedDatasourceTarget(
        host=os.environ.get("SPY_DB_HOST", "devtest.wb.sql.wb-intra.com"),
        port=int(os.environ.get("SPY_DB_PORT", "13306")),
        database_name=os.environ.get("SPY_DB_NAME", "spy"),
        username=os.environ.get("SPY_DB_USER", "test_liuxiaofeng"),
        password_secret_ref=f"local:{password}",
    )


def build_sync_bundle(
    rows: list[TableConfigRow],
    imported_target: ImportedDatasourceTarget,
) -> SyncBundle:
    datasource_map: dict[str, dict[str, Any]] = {}
    logical_groups: dict[str, list[TableConfigRow]] = {}
    skipped_rows = 0

    for row in rows:
        normalized_table_name = row.table_name.strip()
        if not normalized_table_name:
            skipped_rows += 1
            continue

        source_name = row.source_name.strip()
        catlog_name = row.catlog_name.strip()

        datasource_code = make_datasource_code(source_name)
        datasource_map.setdefault(
            datasource_code,
            {
                "datasource_code": datasource_code,
                "display_name": source_name or "unknown_source",
                "db_type": "mysql",
                "host": imported_target.host,
                "port": imported_target.port,
                "database_name": imported_target.database_name,
                "username": imported_target.username,
                "password_secret_ref": imported_target.password_secret_ref,
                "read_only": True,
                "enabled": True,
                "extra": {
                    "sync_origin": SYNC_ORIGIN,
                    "original_source_name": source_name,
                    "connection_origin": "db_skill_env",
                },
            },
        )

        group_key = make_logical_table_name(catlog_name, normalized_table_name)
        logical_groups.setdefault(group_key, []).append(
            TableConfigRow(
                source_name=source_name,
                catlog_name=catlog_name,
                table_name=normalized_table_name,
                begin_index=row.begin_index,
                end_index=row.end_index,
                shard_count=row.shard_count,
                update_time=row.update_time,
            )
        )

    logical_tables: list[dict[str, Any]] = []
    route_factors: list[dict[str, Any]] = []
    route_rules: list[dict[str, Any]] = []
    physical_routes: list[dict[str, Any]] = []

    for logical_name, group_rows in sorted(logical_groups.items()):
        sample = group_rows[0]
        unique_segments = {
            (
                row.source_name,
                row.begin_index,
                row.end_index,
                row.shard_count,
            ): row
            for row in group_rows
        }
        deduped_rows = list(unique_segments.values())
        is_sharded = any(row.shard_count > 0 for row in deduped_rows)
        distinct_source_names = sorted({row.source_name or "unknown_source" for row in deduped_rows})
        requires_source_routing = not is_sharded and len(distinct_source_names) > 1
        shard_suffixes = {
            suffix
            for row in deduped_rows
            if row.shard_count > 0
            for suffix in range(row.begin_index, row.end_index + 1)
        }
        shard_modulus = max((row.shard_count for row in deduped_rows), default=0)
        supports_business_factor_routing = bool(
            is_sharded
            and shard_modulus > 0
            and shard_suffixes == set(range(shard_modulus))
        )

        logical_tables.append(
            {
                "table_name": logical_name,
                "description": f"Imported from {SYNC_ORIGIN}: {sample.catlog_name}.{sample.table_name}",
                "route_source": (
                    "sql_and_route_context"
                    if supports_business_factor_routing
                    else "route_context_or_sql"
                    if (is_sharded or requires_source_routing)
                    else "sql_or_physical_table"
                ),
                "physical_name_template": (
                    f"{sample.table_name}" if not is_sharded else f"{sample.table_name}" + "_{route_suffix}"
                ),
                "default_policy_code": DEFAULT_POLICY_CODE,
                "enabled": True,
                "extra": {
                    "sync_origin": SYNC_ORIGIN,
                    "original_catlog_name": sample.catlog_name,
                    "original_table_name": sample.table_name,
                    "source_names": sorted({row.source_name for row in deduped_rows}),
                    "row_count_in_table_config": len(group_rows),
                    "deduped_segment_count": len(deduped_rows),
                    "shard_count_values": sorted({row.shard_count for row in deduped_rows}),
                    "shard_modulus": shard_modulus if supports_business_factor_routing else None,
                    "business_factor_routing": supports_business_factor_routing,
                },
            }
        )

        if supports_business_factor_routing:
            route_factors.append(
                {
                    "logical_table_name": logical_name,
                    "factor_name": BUSINESS_SHARD_FACTOR,
                    "source_type": "sql_predicate_from_context",
                    "source_key": BUSINESS_SHARD_COLUMN_CONTEXT,
                    "required": True,
                    "extractor_config": {
                        "hint": (
                            "Provide the mapper/DAO shard column name in "
                            "route_context.shard_column and include its value as an SQL equality predicate"
                        ),
                    },
                    "enabled": True,
                }
            )
            route_rules.append(
                {
                    "logical_table_name": logical_name,
                    "rule_name": "imported_business_shard_mod",
                    "rule_type": "mod",
                    "expression": f"str(int({BUSINESS_SHARD_FACTOR}) % {shard_modulus})",
                    "output_format": "{value}",
                    "enabled": True,
                }
            )
        elif is_sharded:
            route_factors.append(
                {
                    "logical_table_name": logical_name,
                    "factor_name": DEFAULT_ROUTE_FACTOR,
                    "source_type": "route_context",
                    "source_key": DEFAULT_ROUTE_FACTOR,
                    "required": True,
                    "extractor_config": {
                        "hint": "Provide the concrete table suffix from route_context.route_suffix",
                    },
                    "enabled": True,
                }
            )
            route_rules.append(
                {
                    "logical_table_name": logical_name,
                    "rule_name": "imported_route_suffix_passthrough",
                    "rule_type": "route_context_passthrough",
                    "expression": "str(int(route_suffix))",
                    "output_format": "{value}",
                    "enabled": True,
                }
            )
        elif requires_source_routing:
            route_factors.append(
                {
                    "logical_table_name": logical_name,
                    "factor_name": SOURCE_ROUTE_FACTOR,
                    "source_type": "route_context",
                    "source_key": SOURCE_ROUTE_FACTOR,
                    "required": True,
                    "extractor_config": {
                        "hint": "Provide the source_name from route_context.source_name",
                        "allowed_values": distinct_source_names,
                    },
                    "enabled": True,
                }
            )
            route_rules.append(
                {
                    "logical_table_name": logical_name,
                    "rule_name": "imported_source_name_passthrough",
                    "rule_type": "route_context_passthrough",
                    "expression": "str(source_name)",
                    "output_format": "{value}",
                    "enabled": True,
                }
            )
        else:
            route_rules.append(
                {
                    "logical_table_name": logical_name,
                    "rule_name": "imported_constant_single_table",
                    "rule_type": "constant",
                    "expression": "'0'",
                    "output_format": "{value}",
                    "enabled": True,
                }
            )

        seen_route_values: dict[str, tuple[str, str]] = {}
        for row in sorted(deduped_rows, key=lambda item: (item.begin_index, item.end_index, item.source_name)):
            datasource_code = make_datasource_code(row.source_name)
            if requires_source_routing:
                route_value = row.source_name or "unknown_source"
                physical_name = row.table_name
                conflict = seen_route_values.get(route_value)
                if conflict and conflict != (physical_name, datasource_code):
                    raise ValueError(
                        f"Conflicting source-routed table for {logical_name}: {conflict} vs {(physical_name, datasource_code)}"
                    )
                seen_route_values[route_value] = (physical_name, datasource_code)
                physical_routes.append(
                    {
                        "logical_table_name": logical_name,
                        "route_value": route_value,
                        "physical_table_name": physical_name,
                        "datasource_code": datasource_code,
                        "enabled": True,
                        "extra": {
                            "sync_origin": SYNC_ORIGIN,
                            "original_source_name": row.source_name,
                            "original_catlog_name": row.catlog_name,
                            "begin_index": row.begin_index,
                            "end_index": row.end_index,
                            "shard_count": row.shard_count,
                        },
                    }
                )
                continue

            if not is_sharded:
                route_value = "0"
                physical_name = row.table_name
                conflict = seen_route_values.get(route_value)
                if conflict and conflict != (physical_name, datasource_code):
                    raise ValueError(
                        f"Conflicting single-table route for {logical_name}: {conflict} vs {(physical_name, datasource_code)}"
                    )
                seen_route_values[route_value] = (physical_name, datasource_code)
                physical_routes.append(
                    {
                        "logical_table_name": logical_name,
                        "route_value": route_value,
                        "physical_table_name": physical_name,
                        "datasource_code": datasource_code,
                        "enabled": True,
                        "extra": {
                            "sync_origin": SYNC_ORIGIN,
                            "original_source_name": row.source_name,
                            "original_catlog_name": row.catlog_name,
                            "begin_index": row.begin_index,
                            "end_index": row.end_index,
                            "shard_count": row.shard_count,
                        },
                    }
                )
                continue

            for suffix in range(row.begin_index, row.end_index + 1):
                route_value = str(suffix)
                physical_name = f"{row.table_name}_{suffix}"
                conflict = seen_route_values.get(route_value)
                if conflict and conflict != (physical_name, datasource_code):
                    raise ValueError(
                        f"Conflicting route for {logical_name} and suffix {route_value}: {conflict} vs {(physical_name, datasource_code)}"
                    )
                if conflict:
                    continue
                seen_route_values[route_value] = (physical_name, datasource_code)
                physical_routes.append(
                    {
                        "logical_table_name": logical_name,
                        "route_value": route_value,
                        "physical_table_name": physical_name,
                        "datasource_code": datasource_code,
                        "enabled": True,
                        "extra": {
                            "sync_origin": SYNC_ORIGIN,
                            "original_source_name": row.source_name,
                            "original_catlog_name": row.catlog_name,
                            "begin_index": row.begin_index,
                            "end_index": row.end_index,
                            "shard_count": row.shard_count,
                        },
                    }
                )

    return SyncBundle(
        datasources=sorted(datasource_map.values(), key=lambda item: item["datasource_code"]),
        logical_tables=logical_tables,
        route_factors=route_factors,
        route_rules=route_rules,
        physical_routes=physical_routes,
        skipped_rows=skipped_rows,
    )


def fetch_remote_table_config() -> list[TableConfigRow]:
    connection = pymysql.connect(
        host=os.environ.get("SPY_DB_HOST", "devtest.wb.sql.wb-intra.com"),
        port=int(os.environ.get("SPY_DB_PORT", "13306")),
        user=os.environ.get("SPY_DB_USER", "test_liuxiaofeng"),
        password=os.environ["SPY_DB_PASSWORD"],
        database=os.environ.get("SPY_DB_NAME", "spy"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        read_timeout=30,
        write_timeout=30,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT source_name, catlog_name, table_name, begin_index, end_index, shard_count, update_time
                FROM table_config
                ORDER BY catlog_name, table_name, source_name, begin_index, end_index
                """
            )
            return [
                TableConfigRow(
                    source_name=row["source_name"] or "",
                    catlog_name=row["catlog_name"] or "",
                    table_name=row["table_name"] or "",
                    begin_index=int(row["begin_index"] or 0),
                    end_index=int(row["end_index"] or 0),
                    shard_count=int(row["shard_count"] or 0),
                    update_time=row.get("update_time"),
                )
                for row in cursor.fetchall()
            ]
    finally:
        connection.close()


def ensure_default_policy(session: Session) -> None:
    existing = session.execute(select(PolicySet).where(PolicySet.policy_code == DEFAULT_POLICY_CODE)).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        PolicySet(
            policy_code=DEFAULT_POLICY_CODE,
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
    session.flush()


def delete_previous_import(session: Session) -> None:
    imported_tables = list(
        session.execute(
            select(LogicalTable).where(LogicalTable.extra["sync_origin"].as_string() == SYNC_ORIGIN)
        ).scalars()
    )
    imported_logical_ids = [row.id for row in imported_tables]
    if imported_logical_ids:
        session.query(PhysicalTableRoute).filter(PhysicalTableRoute.logical_table_id.in_(imported_logical_ids)).delete(
            synchronize_session=False
        )
        session.query(RouteFactorDef).filter(RouteFactorDef.logical_table_id.in_(imported_logical_ids)).delete(
            synchronize_session=False
        )
        session.query(RouteRule).filter(RouteRule.logical_table_id.in_(imported_logical_ids)).delete(
            synchronize_session=False
        )
        session.query(LogicalTable).filter(LogicalTable.id.in_(imported_logical_ids)).delete(synchronize_session=False)

    imported_datasources = list(
        session.execute(
            select(DatasourceInstance).where(DatasourceInstance.extra["sync_origin"].as_string() == SYNC_ORIGIN)
        ).scalars()
    )
    imported_datasource_ids = [row.id for row in imported_datasources]
    if imported_datasource_ids:
        session.query(DatasourceInstance).filter(DatasourceInstance.id.in_(imported_datasource_ids)).delete(
            synchronize_session=False
        )


def sync_bundle_to_local(bundle: SyncBundle, settings: Settings | None = None) -> dict[str, int]:
    app_settings = settings or Settings()
    create_metadata_schema(app_settings)
    engine = create_engine(app_settings.meta_db_dsn, pool_pre_ping=True)

    with Session(engine) as session:
        ensure_default_policy(session)
        delete_previous_import(session)

        datasource_objects: dict[str, DatasourceInstance] = {}
        for record in bundle.datasources:
            obj = DatasourceInstance(**record)
            session.add(obj)
            datasource_objects[record["datasource_code"]] = obj
        session.flush()

        logical_objects: dict[str, LogicalTable] = {}
        for record in bundle.logical_tables:
            obj = LogicalTable(**record)
            session.add(obj)
            logical_objects[record["table_name"]] = obj
        session.flush()

        for record in bundle.route_factors:
            logical_table = logical_objects[record["logical_table_name"]]
            session.add(
                RouteFactorDef(
                    logical_table_id=logical_table.id,
                    factor_name=record["factor_name"],
                    source_type=record["source_type"],
                    source_key=record["source_key"],
                    required=record["required"],
                    extractor_config=record["extractor_config"],
                    enabled=record["enabled"],
                )
            )

        for record in bundle.route_rules:
            logical_table = logical_objects[record["logical_table_name"]]
            session.add(
                RouteRule(
                    logical_table_id=logical_table.id,
                    rule_name=record["rule_name"],
                    rule_type=record["rule_type"],
                    expression=record["expression"],
                    output_format=record["output_format"],
                    enabled=record["enabled"],
                )
            )

        for record in bundle.physical_routes:
            logical_table = logical_objects[record["logical_table_name"]]
            datasource = datasource_objects[record["datasource_code"]]
            session.add(
                PhysicalTableRoute(
                    logical_table_id=logical_table.id,
                    route_value=record["route_value"],
                    physical_table_name=record["physical_table_name"],
                    datasource_id=datasource.id,
                    enabled=record["enabled"],
                    extra=record["extra"],
                )
            )

        session.commit()

    return {
        "datasource_count": len(bundle.datasources),
        "logical_table_count": len(bundle.logical_tables),
        "route_factor_count": len(bundle.route_factors),
        "route_rule_count": len(bundle.route_rules),
        "physical_route_count": len(bundle.physical_routes),
        "skipped_row_count": bundle.skipped_rows,
    }


def main() -> None:
    rows = fetch_remote_table_config()
    bundle = build_sync_bundle(rows, build_imported_datasource_target_from_env())
    summary = sync_bundle_to_local(bundle)
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
