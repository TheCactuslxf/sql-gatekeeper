CREATE TABLE IF NOT EXISTS order_2025_06 (
  order_id VARCHAR(64) PRIMARY KEY,
  amount DECIMAL(10,2) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS order_2025_07 (
  order_id VARCHAR(64) PRIMARY KEY,
  amount DECIMAL(10,2) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL
);

INSERT INTO order_2025_06 (order_id, amount, tenant_id) VALUES
  ('A1001', 20.50, 't1')
ON DUPLICATE KEY UPDATE amount = VALUES(amount), tenant_id = VALUES(tenant_id);

INSERT INTO order_2025_07 (order_id, amount, tenant_id) VALUES
  ('A1002', 30.00, 't1')
ON DUPLICATE KEY UPDATE amount = VALUES(amount), tenant_id = VALUES(tenant_id);

