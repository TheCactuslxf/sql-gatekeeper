#!/usr/bin/env sh
set -eu

python -m sql_gatekeeper.bootstrap.meta
python -m sql_gatekeeper.bootstrap.redis_demo

exec "$@"
