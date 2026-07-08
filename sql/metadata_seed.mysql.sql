-- SQL Gatekeeper metadata seed data for MySQL 8
-- Aligned with src/sql_gatekeeper/bootstrap/meta.py
-- This script initializes only metadata tables.
-- It does not initialize business shard tables.

START TRANSACTION;

INSERT INTO policy_set (
  policy_code,
  allow_sql_types,
  require_limit,
  max_limit,
  large_table_row_threshold,
  max_scan_rows,
  reject_full_scan_on_large_table,
  reject_using_temporary,
  reject_using_filesort,
  enabled
)
VALUES (
  'default_select_guard',
  JSON_ARRAY('select'),
  1,
  1000,
  100000,
  10000,
  1,
  1,
  1,
  1
)
ON DUPLICATE KEY UPDATE
  allow_sql_types = VALUES(allow_sql_types),
  require_limit = VALUES(require_limit),
  max_limit = VALUES(max_limit),
  large_table_row_threshold = VALUES(large_table_row_threshold),
  max_scan_rows = VALUES(max_scan_rows),
  reject_full_scan_on_large_table = VALUES(reject_full_scan_on_large_table),
  reject_using_temporary = VALUES(reject_using_temporary),
  reject_using_filesort = VALUES(reject_using_filesort),
  enabled = VALUES(enabled);

INSERT INTO datasource_instance (
  datasource_code,
  display_name,
  db_type,
  host,
  port,
  database_name,
  username,
  password_secret_ref,
  read_only,
  enabled,
  extra
)
VALUES
  (
    'biz_user_db',
    'Business User DB',
    'mysql',
    '127.0.0.1',
    33062,
    'biz_user',
    'readonly',
    'local:readonly',
    1,
    1,
    JSON_OBJECT()
  ),
  (
    'biz_order_db',
    'Business Order DB',
    'mysql',
    '127.0.0.1',
    33063,
    'biz_order',
    'readonly',
    'local:readonly',
    1,
    1,
    JSON_OBJECT()
  )
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  db_type = VALUES(db_type),
  host = VALUES(host),
  port = VALUES(port),
  database_name = VALUES(database_name),
  username = VALUES(username),
  password_secret_ref = VALUES(password_secret_ref),
  read_only = VALUES(read_only),
  enabled = VALUES(enabled),
  extra = VALUES(extra);

INSERT INTO logical_table (
  table_name,
  description,
  route_source,
  physical_name_template,
  default_policy_code,
  enabled,
  extra
)
VALUES
  (
    'user',
    'Logical user table',
    'sql_or_physical_table',
    'user_{suffix}',
    'default_select_guard',
    1,
    JSON_OBJECT()
  ),
  (
    'order',
    'Logical order table',
    'route_context_or_sql',
    'order_{biz_date}',
    'default_select_guard',
    1,
    JSON_OBJECT()
  )
ON DUPLICATE KEY UPDATE
  description = VALUES(description),
  route_source = VALUES(route_source),
  physical_name_template = VALUES(physical_name_template),
  default_policy_code = VALUES(default_policy_code),
  enabled = VALUES(enabled),
  extra = VALUES(extra);

INSERT INTO route_factor_def (
  logical_table_id,
  factor_name,
  source_type,
  source_key,
  required,
  extractor_config,
  enabled
)
SELECT
  lt.id,
  seed.factor_name,
  seed.source_type,
  seed.source_key,
  1,
  JSON_OBJECT(),
  1
FROM (
  SELECT 'user' AS table_name, 'uid' AS factor_name, 'sql_predicate' AS source_type, 'uid' AS source_key
  UNION ALL
  SELECT 'order', 'biz_date', 'route_context', 'biz_date'
) AS seed
JOIN logical_table lt ON lt.table_name = seed.table_name
ON DUPLICATE KEY UPDATE
  source_type = VALUES(source_type),
  source_key = VALUES(source_key),
  required = VALUES(required),
  extractor_config = VALUES(extractor_config),
  enabled = VALUES(enabled);

INSERT INTO route_rule (
  logical_table_id,
  rule_name,
  rule_type,
  expression,
  output_format,
  enabled
)
SELECT
  lt.id,
  seed.rule_name,
  seed.rule_type,
  seed.expression,
  seed.output_format,
  1
FROM (
  SELECT
    'user' AS table_name,
    'user_mod_2' AS rule_name,
    'mod' AS rule_type,
    'int(uid) % 2' AS expression,
    '{value}' AS output_format
  UNION ALL
  SELECT
    'order',
    'order_month',
    'format',
    'biz_date.replace(''-'', ''_'')',
    '{value}'
) AS seed
JOIN logical_table lt ON lt.table_name = seed.table_name
ON DUPLICATE KEY UPDATE
  rule_type = VALUES(rule_type),
  expression = VALUES(expression),
  output_format = VALUES(output_format),
  enabled = VALUES(enabled);

INSERT INTO physical_table_route (
  logical_table_id,
  route_value,
  physical_table_name,
  datasource_id,
  enabled,
  extra
)
SELECT
  lt.id,
  seed.route_value,
  seed.physical_table_name,
  ds.id,
  1,
  JSON_OBJECT()
FROM (
  SELECT 'user' AS table_name, '0' AS route_value, 'user_0' AS physical_table_name, 'biz_user_db' AS datasource_code
  UNION ALL
  SELECT 'user', '1', 'user_1', 'biz_user_db'
  UNION ALL
  SELECT 'order', '2025_06', 'order_2025_06', 'biz_order_db'
  UNION ALL
  SELECT 'order', '2025_07', 'order_2025_07', 'biz_order_db'
) AS seed
JOIN logical_table lt ON lt.table_name = seed.table_name
JOIN datasource_instance ds ON ds.datasource_code = seed.datasource_code
ON DUPLICATE KEY UPDATE
  physical_table_name = VALUES(physical_table_name),
  datasource_id = VALUES(datasource_id),
  enabled = VALUES(enabled),
  extra = VALUES(extra);

-- table_stats_snapshot:
-- No static seed rows are inserted here.
-- Runtime should populate this table from live information_schema statistics.

-- request_audit_log:
-- No static seed rows are inserted here.
-- Runtime writes audit records only after real SQL requests are checked or executed.

COMMIT;
