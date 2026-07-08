CREATE TABLE IF NOT EXISTS user_0 (
  uid BIGINT PRIMARY KEY,
  user_name VARCHAR(128) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_1 (
  uid BIGINT PRIMARY KEY,
  user_name VARCHAR(128) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1
);

INSERT INTO user_0 (uid, user_name, status) VALUES
  (10000, 'alice', 1)
ON DUPLICATE KEY UPDATE user_name = VALUES(user_name), status = VALUES(status);

INSERT INTO user_1 (uid, user_name, status) VALUES
  (10001, 'bob', 1)
ON DUPLICATE KEY UPDATE user_name = VALUES(user_name), status = VALUES(status);

