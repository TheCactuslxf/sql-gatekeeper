-- SQL Gatekeeper metadata schema for MySQL 8
-- This file is a manual DDL snapshot aligned with the current SQLAlchemy models.

CREATE TABLE IF NOT EXISTS datasource_instance (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  datasource_code VARCHAR(64) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  db_type VARCHAR(32) NOT NULL DEFAULT 'mysql',
  host VARCHAR(255) NOT NULL,
  port INT NOT NULL,
  database_name VARCHAR(128) NOT NULL,
  username VARCHAR(128) NOT NULL,
  password_secret_ref VARCHAR(255) NOT NULL,
  read_only TINYINT(1) NOT NULL DEFAULT 1,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  extra JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_datasource_code (datasource_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS logical_table (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  table_name VARCHAR(128) NOT NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  route_source VARCHAR(32) NOT NULL,
  physical_name_template VARCHAR(255) NOT NULL,
  default_policy_code VARCHAR(64) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  extra JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_logical_table_name (table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS route_factor_def (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  logical_table_id BIGINT NOT NULL,
  factor_name VARCHAR(64) NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  source_key VARCHAR(128) NOT NULL,
  required TINYINT(1) NOT NULL DEFAULT 1,
  extractor_config JSON NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_route_factor_logical_table
    FOREIGN KEY (logical_table_id) REFERENCES logical_table(id),
  UNIQUE KEY uq_route_factor_table_name (logical_table_id, factor_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS route_rule (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  logical_table_id BIGINT NOT NULL,
  rule_name VARCHAR(64) NOT NULL,
  rule_type VARCHAR(32) NOT NULL,
  expression TEXT NOT NULL,
  output_format VARCHAR(128) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_route_rule_logical_table
    FOREIGN KEY (logical_table_id) REFERENCES logical_table(id),
  UNIQUE KEY uq_route_rule_table_name (logical_table_id, rule_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS physical_table_route (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  logical_table_id BIGINT NOT NULL,
  route_value VARCHAR(128) NOT NULL,
  physical_table_name VARCHAR(128) NOT NULL,
  datasource_id BIGINT NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  extra JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_physical_route_logical_table
    FOREIGN KEY (logical_table_id) REFERENCES logical_table(id),
  CONSTRAINT fk_physical_route_datasource
    FOREIGN KEY (datasource_id) REFERENCES datasource_instance(id),
  UNIQUE KEY uq_table_route_value (logical_table_id, route_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS policy_set (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  policy_code VARCHAR(64) NOT NULL,
  allow_sql_types JSON NOT NULL,
  require_limit TINYINT(1) NOT NULL DEFAULT 1,
  max_limit INT NOT NULL DEFAULT 1000,
  large_table_row_threshold INT NOT NULL DEFAULT 100000,
  max_scan_rows INT NOT NULL DEFAULT 10000,
  reject_full_scan_on_large_table TINYINT(1) NOT NULL DEFAULT 1,
  reject_using_temporary TINYINT(1) NOT NULL DEFAULT 1,
  reject_using_filesort TINYINT(1) NOT NULL DEFAULT 1,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_policy_code (policy_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS table_stats_snapshot (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  datasource_id BIGINT NOT NULL,
  physical_table_name VARCHAR(128) NOT NULL,
  row_count BIGINT NOT NULL DEFAULT 0,
  data_length_bytes BIGINT NOT NULL DEFAULT 0,
  index_length_bytes BIGINT NOT NULL DEFAULT 0,
  last_analyzed_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_table_stats_datasource
    FOREIGN KEY (datasource_id) REFERENCES datasource_instance(id),
  UNIQUE KEY uq_stats_table (datasource_id, physical_table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS request_audit_log (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  request_id VARCHAR(64) NOT NULL,
  operator VARCHAR(128) NOT NULL,
  scene VARCHAR(64) NOT NULL DEFAULT '',
  original_sql TEXT NOT NULL,
  rewritten_sql TEXT NOT NULL,
  logical_tables JSON NOT NULL,
  physical_tables JSON NOT NULL,
  datasource_codes JSON NOT NULL,
  decision VARCHAR(32) NOT NULL,
  reason_code VARCHAR(64) NOT NULL,
  reason_detail TEXT NOT NULL,
  execution_ms INT NOT NULL DEFAULT 0,
  explain_summary JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_request_audit_log_request_id (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
