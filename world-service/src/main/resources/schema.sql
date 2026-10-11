CREATE TABLE IF NOT EXISTS world_saves (
  world_id VARCHAR(64) PRIMARY KEY,
  snapshot LONGTEXT NOT NULL,
  revision BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_executions (
  world_id VARCHAR(64) NOT NULL,
  request_id VARCHAR(80) NOT NULL,
  receipt LONGTEXT NOT NULL,
  PRIMARY KEY (world_id, request_id)
);
