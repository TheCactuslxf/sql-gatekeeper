#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"

echo "== health =="
curl -s "$BASE_URL/health"
echo

echo "== check logical SQL =="
curl -s "$BASE_URL/api/v1/sql/check" \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-check-user",
    "operator": "ai-agent",
    "scene": "demo",
    "sql": "select uid, user_name from user where uid = 10001 limit 10",
    "route_context": {}
  }'
echo

echo "== execute approved SQL =="
curl -s "$BASE_URL/api/v1/sql/execute" \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-execute-user",
    "operator": "ai-agent",
    "scene": "demo",
    "sql": "select uid, user_name from user where uid = 10001 limit 1",
    "route_context": {}
  }'
echo

echo "== reject unsafe SQL =="
curl -s "$BASE_URL/api/v1/sql/check" \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-reject-update",
    "operator": "ai-agent",
    "scene": "demo",
    "sql": "update user set status = 0 where uid = 10001",
    "route_context": {}
  }'
echo

echo "== check Redis GET =="
curl -s "$BASE_URL/api/v1/redis/check" \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-redis-check",
    "operator": "ai-agent",
    "scene": "demo",
    "command": "GET",
    "args": ["demo:user:10001"],
    "redis_context": {"catlog_name": "demo"}
  }'
echo

echo "== execute Redis GET =="
curl -s "$BASE_URL/api/v1/redis/execute" \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-redis-execute",
    "operator": "ai-agent",
    "scene": "demo",
    "command": "GET",
    "args": ["demo:user:10001"],
    "redis_context": {"catlog_name": "demo"}
  }'
echo

echo "== reject unsafe Redis command =="
curl -s "$BASE_URL/api/v1/redis/check" \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-redis-reject",
    "operator": "ai-agent",
    "scene": "demo",
    "command": "SET",
    "args": ["demo:user:10001", "alice"],
    "redis_context": {"catlog_name": "demo"}
  }'
echo
