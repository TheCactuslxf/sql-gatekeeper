-- SQL Gatekeeper business shard schema for MySQL 8
-- This file contains only table DDL for sample physical shards.
-- It intentionally excludes business seed data.

-- user logical table physical shards
CREATE TABLE IF NOT EXISTS user_0 (
  uid BIGINT PRIMARY KEY,
  user_name VARCHAR(128) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_1 (
  uid BIGINT PRIMARY KEY,
  user_name VARCHAR(128) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- order logical table physical shards
CREATE TABLE IF NOT EXISTS order_2025_06 (
  order_id VARCHAR(64) PRIMARY KEY,
  amount DECIMAL(10,2) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_2025_07 (
  order_id VARCHAR(64) PRIMARY KEY,
  amount DECIMAL(10,2) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Additional physical shards can be created with the same schema:
-- user_{suffix}
-- order_{yyyy_mm}
